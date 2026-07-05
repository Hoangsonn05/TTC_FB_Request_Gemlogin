# -*- coding: utf-8 -*-
import datetime
from collections import deque

class JobHistoryRecord:
    def __init__(self, worker_id, profile_id, buff_id, job_type, status, 
                 reaction_type=None, reason="", submit_message="", earned_coin=0, duration_sec=0):
        self.timestamp_start = datetime.datetime.now() - datetime.timedelta(seconds=duration_sec)
        self.timestamp_end = datetime.datetime.now()
        self.worker_id = str(worker_id)
        self.profile_id = str(profile_id) if profile_id else ""
        self.buff_id = str(buff_id) if buff_id else ""
        self.job_type = str(job_type)
        self.reaction_type = str(reaction_type) if reaction_type else ""
        self.status = str(status)  # done / failed / skipped / reported
        self.reason = str(reason)
        self.submit_message = str(submit_message)
        self.earned_coin = int(earned_coin)
        self.duration_sec = float(duration_sec)


class JobHistoryManager:
    """
    Quản lý lịch sử job gọn nhẹ trong RAM.
    Giới hạn tối đa 1000 dòng gần nhất để tránh phình RAM.
    """
    def __init__(self, max_records=1000):
        self.max_records = int(max_records)
        self._records = deque(maxlen=self.max_records)
        self._index = {}

    def make_key(self, worker_id, buff_id):
        return (str(worker_id or ""), str(buff_id or ""))

    def upsert_record(self, record):
        key = self.make_key(record.worker_id, record.buff_id)
        existing = self._index.get(key)
        if existing is not None:
            existing.timestamp_end = record.timestamp_end
            existing.profile_id = record.profile_id
            existing.job_type = record.job_type
            existing.reaction_type = record.reaction_type
            existing.status = record.status
            existing.reason = record.reason
            existing.submit_message = record.submit_message
            existing.earned_coin = record.earned_coin
            existing.duration_sec = record.duration_sec
            return existing

        if len(self._records) >= self.max_records:
            old = self._records.popleft()
            self._index.pop(self.make_key(old.worker_id, old.buff_id), None)
        self._records.append(record)
        self._index[key] = record
        return record

    def add_record(self, record):
        return self.upsert_record(record)

    def get_records(self):
        return list(self._records)

    def clear(self):
        self._records.clear()
        self._index.clear()
