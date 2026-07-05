# -*- coding: utf-8 -*-
import datetime
import queue
from collections import deque


ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("done", "failed", "skipped", "reported", "full", "dead_post")


class Job:
    def __init__(self, raw_data, worker_id=None, source="new_fetch"):
        self.raw_data = raw_data
        self.worker_id = worker_id
        self.buff_id = raw_data.get("buff_id")
        self.type = raw_data.get("type")
        self.object_id = raw_data.get("object_id")
        self.source = source
        self.status = "queued"
        self.retry_count = 0
        self.created_at = datetime.datetime.now()
        self.updated_at = datetime.datetime.now()
        self.error_reason = ""

    def update_status(self, new_status, reason=""):
        self.status = new_status
        self.error_reason = reason
        self.updated_at = datetime.datetime.now()


class JobQueue:
    """Thread-safe enough per-worker queue. One worker owns one JobQueue."""

    def __init__(self, worker_id, account_id=None):
        self.worker_id = str(worker_id)
        self.account_id = account_id
        self._queue = queue.Queue()
        self._all_jobs = {}
        self.seen_buff_ids = set()

    def put_job(self, raw_job_data, source="new_fetch"):
        buff_id = raw_job_data.get("buff_id")
        if not buff_id:
            return None

        if buff_id in self.seen_buff_ids:
            return None

        job = Job(raw_job_data, self.worker_id, source)
        self._all_jobs[buff_id] = job
        self.seen_buff_ids.add(buff_id)
        self._queue.put(job)
        return job

    def put_many(self, raw_jobs_list, source="new_fetch"):
        added = []
        for raw_job in raw_jobs_list or []:
            job = self.put_job(raw_job, source)
            if job:
                added.append(job)
        return added

    def get_job(self, timeout=None):
        try:
            job = self._queue.get(block=True, timeout=timeout)
            if job:
                job.update_status("running")
            return job
        except queue.Empty:
            return None

    def requeue_job(self, job, reason="retry"):
        if not job or job.buff_id not in self._all_jobs:
            return False
        tracked = self._all_jobs[job.buff_id]
        tracked.retry_count += 1
        tracked.update_status("queued", reason)
        self._queue.put(tracked)
        return True

    def size(self):
        return self._queue.qsize()

    def is_empty(self):
        return self._queue.empty()

    def clear(self):
        with self._queue.mutex:
            self._queue.queue.clear()
        self._all_jobs.clear()
        self.seen_buff_ids.clear()

    def mark_done(self, job):
        if job and job.buff_id in self._all_jobs:
            self._all_jobs[job.buff_id].update_status("done")

    def mark_failed(self, job, reason=""):
        if job and job.buff_id in self._all_jobs:
            self._all_jobs[job.buff_id].update_status("failed", reason)

    def mark_skipped(self, job, reason=""):
        if job and job.buff_id in self._all_jobs:
            self._all_jobs[job.buff_id].update_status("skipped", reason)

    def mark_reported(self, job_or_buff_id, reason="reported"):
        buff_id = getattr(job_or_buff_id, "buff_id", job_or_buff_id)
        if buff_id in self._all_jobs:
            self._all_jobs[buff_id].update_status("reported", reason)

    def mark_full(self, job_or_buff_id, reason="job_full"):
        buff_id = getattr(job_or_buff_id, "buff_id", job_or_buff_id)
        if buff_id in self._all_jobs:
            self._all_jobs[buff_id].update_status("full", reason)

    def mark_dead_post(self, job_or_buff_id, reason="dead_post"):
        buff_id = getattr(job_or_buff_id, "buff_id", job_or_buff_id)
        if buff_id in self._all_jobs:
            self._all_jobs[buff_id].update_status("dead_post", reason)

    def get_status(self, buff_id):
        job = self._all_jobs.get(buff_id)
        if job:
            return job.status
        if buff_id in self.seen_buff_ids:
            return "seen_without_job"
        return "new"

    def classify_buff_id(self, buff_id):
        status = self.get_status(buff_id)
        if status in ACTIVE_STATUSES:
            return "active"
        if status in TERMINAL_STATUSES:
            return "terminal"
        if status == "seen_without_job":
            return "stale"
        return "new"

    def forget(self, buff_id):
        if not buff_id:
            return
        self.seen_buff_ids.discard(buff_id)
        self._all_jobs.pop(buff_id, None)

    def forget_many(self, buff_ids):
        for buff_id in buff_ids or []:
            self.forget(buff_id)

    def discard_blocked_queued_jobs(self, blocked_job_types, reason="interaction_blocked"):
        blocked = set(blocked_job_types or [])
        if not blocked:
            return []

        skipped = []
        with self._queue.mutex:
            kept = deque()
            while self._queue.queue:
                job = self._queue.queue.popleft()
                if getattr(job, "type", None) in blocked:
                    job.update_status("skipped", reason)
                    skipped.append(job)
                else:
                    kept.append(job)
            self._queue.queue = kept
        return skipped
