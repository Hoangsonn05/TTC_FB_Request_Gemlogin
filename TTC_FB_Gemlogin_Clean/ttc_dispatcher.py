# -*- coding: utf-8 -*-
"""
ttc_dispatcher.py — TTCDispatcher: quản lý fetch job TTC vào JobQueue.

Tái sử dụng JobQueue hiện có của Bumx.
Loại bỏ toàn bộ logic mission/pending/report Bumx.

Cơ chế:
- Round-robin giữa các enabled_job_types.
- Chỉ fetch khi queue < min_queue_size.
- Không nạp vượt max_queue_size.
- Job trùng job_key trong phiên không được nạp lại (JobQueue.seen_buff_ids đảm nhiệm).
- Countdown kiểm tra stop_event mỗi giây.
- Fetch hết job → TTCNoJobAvailable, không tăng consecutive_api_errors.
- API error thật mới tăng consecutive_api_errors.
"""

import datetime
import time

from ttc_api import TTCClient, TTCNoJobAvailable, TTCAuthError, TTCRateLimitError, TTCResponseError
from ttc_job_types import ACTION_GROUP_MAP, ACTION_GROUPS_BLOCKED_BY, ALL_JOB_TYPES

MAX_CONSECUTIVE_API_ERRORS = 5


class TTCDispatcher:
    """Dispatcher lấy job TTC và đẩy vào JobQueue của worker.

    Mỗi worker có một TTCDispatcher riêng biệt.
    """

    def __init__(
        self,
        ttc_client: TTCClient,
        job_queue,
        config: dict,
        worker_id,
        stop_event,
        logger,
    ):
        """
        Args:
            ttc_client: Instance TTCClient đã authenticate.
            job_queue: Instance JobQueue của worker này.
            config: Config dict đã normalize.
            worker_id: ID worker.
            stop_event: threading.Event để dừng.
            logger: WorkerLogger từ gui_worker.
        """
        self.ttc = ttc_client
        self.queue = job_queue
        self.config = config
        self.worker_id = str(worker_id)
        self.stop_event = stop_event
        self.logger = logger
        self.stats = None  # Reference từ runtime, được gán sau

        # Danh sách job types được bật
        raw_types = config.get("enabled_job_types") or []
        self.enabled_job_types = [t for t in raw_types if t in ALL_JOB_TYPES]
        if not self.enabled_job_types:
            # Fallback: nếu config cũ không có enabled_job_types
            self.enabled_job_types = list(ALL_JOB_TYPES)

        # Round-robin index
        self._rr_index = 0

        # Config thời gian
        self.wait_no_job_delay = max(5, int(config.get("wait_no_job_delay", 30) or 30))
        self.api_error_retry_delay = max(5, int(config.get("api_error_retry_delay", 20) or 20))
        self.interaction_block_cooldown_seconds = max(
            60,
            int(config.get("interaction_block_cooldown_minutes", 60) or 60) * 60,
        )

        # Queue size limits
        self.min_queue_size = max(1, int(config.get("min_queue_size", 1) or 1))
        self.max_queue_size = max(2, int(config.get("max_queue_size", 3) or 3))

        # Consecutive API error tracking
        self.max_consecutive_api_errors = MAX_CONSECUTIVE_API_ERRORS

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    def log(self, message: str, level: str = "api"):
        if self.stats:
            self.stats["last_message"] = message
            self.stats["queue_size"] = self.queue.size()
            self.stats["elapsed_time"] = str(
                datetime.datetime.now() - self.stats.get("started_at", datetime.datetime.now())
            ).split(".")[0]
        if self.logger:
            self.logger.log(self.worker_id, message, level)
        else:
            print(f"[TTC Worker #{self.worker_id}] {message}")

    def update_runtime_stats(self):
        if self.stats and self.logger:
            self.stats["queue_size"] = self.queue.size()
            self.stats["elapsed_time"] = str(
                datetime.datetime.now() - self.stats.get("started_at", datetime.datetime.now())
            ).split(".")[0]
            self.logger.update_stats(self.worker_id, self.stats)

    # ------------------------------------------------------------------
    # Block detection helpers
    # ------------------------------------------------------------------

    def _is_action_group_blocked(self, action_group: str) -> bool:
        """Kiểm tra một action_group có đang bị block không."""
        if not self.stats:
            return False
        return bool(self.stats.get("interaction_blocked", {}).get(action_group))

    def _is_job_type_blocked(self, job_type: str) -> bool:
        """Kiểm tra job_type có thuộc action_group đang bị block không."""
        group = ACTION_GROUP_MAP.get(job_type, "")
        return self._is_action_group_blocked(group)

    def _get_available_job_types(self) -> list:
        """Lấy danh sách job_type hiện không bị block."""
        return [t for t in self.enabled_job_types if not self._is_job_type_blocked(t)]

    def _all_blocked(self) -> bool:
        """True nếu tất cả job_type đã cấu hình đều bị block."""
        return len(self._get_available_job_types()) == 0

    def _get_blocked_groups_display(self) -> str:
        """Tạo chuỗi hiển thị các group đang bị block."""
        if not self.stats:
            return "None"
        blocked = self.stats.get("interaction_blocked", {})
        groups = [g.upper() for g, v in blocked.items() if v]
        if not groups:
            return "None"
        return ", ".join(groups)

    # ------------------------------------------------------------------
    # Round-robin fetch
    # ------------------------------------------------------------------

    def _next_job_type(self, available: list) -> str | None:
        """Lấy job_type tiếp theo theo round-robin từ danh sách available."""
        if not available:
            return None
        self._rr_index = self._rr_index % len(available)
        job_type = available[self._rr_index]
        self._rr_index = (self._rr_index + 1) % len(available)
        return job_type

    # ------------------------------------------------------------------
    # fetch_once() — được gọi từ vòng lặp worker
    # ------------------------------------------------------------------

    def fetch_once(self):
        """Nạp thêm job vào queue nếu cần.

        Logic:
        1. Kiểm tra stop_event.
        2. Kiểm tra queue size.
        3. Kiểm tra block status.
        4. Round-robin fetch.
        5. Xử lý TTCNoJobAvailable (countdown sleep).
        6. Xử lý API error thật (tăng consecutive_api_errors).
        """
        if self.stop_event.is_set():
            return

        self.update_runtime_stats()
        current_size = self.queue.size()

        # Queue đã đủ
        if current_size >= self.max_queue_size:
            return
        if current_size >= self.min_queue_size:
            return

        # Kiểm tra nếu tất cả job type đều bị block
        available = self._get_available_job_types()
        if not available:
            blocked_disp = self._get_blocked_groups_display()
            if self.stats:
                self.stats["status"] = "blocked"
                self.stats["health_status"] = "blocked"
                self.stats["blocked_display"] = blocked_disp
                self.stats["last_message"] = f"Tất cả loại job đang bị block: {blocked_disp}"
                self.update_runtime_stats()
            self.log(
                f"Tất cả loại tương tác đang cấu hình đều bị chặn ({blocked_disp}). "
                f"Cooldown {self.interaction_block_cooldown_seconds}s.",
                "blocked",
            )
            self.countdown_sleep(self.interaction_block_cooldown_seconds, "Tương tác bị chặn")
            return

        # Log nếu một số group bị block
        if len(available) < len(self.enabled_job_types):
            blocked_disp = self._get_blocked_groups_display()
            self.log(
                f"Một số loại tương tác đang bị chặn ({blocked_disp}), "
                f"sẽ chỉ fetch các loại còn lại.",
                "warning",
            )

        # Round-robin: chọn job_type tiếp theo
        job_type = self._next_job_type(available)
        if not job_type:
            return

        self.log(f"Đang fetch job: {job_type}...", "api")

        try:
            jobs = self.ttc.fetch_jobs(job_type)
        except TTCNoJobAvailable as e:
            # Không phải lỗi → reset consecutive_api_errors
            if self.stats:
                self.stats["total_no_job_count"] = self.stats.get("total_no_job_count", 0) + 1
                self.stats["consecutive_api_errors"] = 0
                if self.stats.get("health_status") == "warning":
                    self.stats["health_status"] = "healthy"
                self.update_runtime_stats()
            countdown = e.countdown or self.wait_no_job_delay
            self.log(f"Không có job {job_type}: {e.ttc_message or str(e)}", "wait")
            self.countdown_sleep(countdown, f"Chờ job {job_type}")
            return

        except TTCAuthError as e:
            # Auth error nghiêm trọng → dừng worker
            self.log(f"Phiên TTC hết hạn: {e}", "error")
            if self.stats:
                self.stats["status"] = "error"
                self.stats["health_status"] = "failed"
                self.stats["last_error"] = str(e)
                self.update_runtime_stats()
            raise  # Re-raise để runtime xử lý

        except TTCRateLimitError as e:
            self.log(f"TTC rate limit: {e}", "warning")
            if self.stats:
                self.stats["consecutive_api_errors"] = (
                    self.stats.get("consecutive_api_errors", 0) + 1
                )
                self.update_runtime_stats()
            self.countdown_sleep(self.api_error_retry_delay * 2, "Rate limit, thử lại sau")
            return

        except (TTCResponseError, Exception) as e:
            self.log(f"Lỗi API khi fetch {job_type}: {e}", "error")
            self._handle_api_error(str(e))
            self.countdown_sleep(self.api_error_retry_delay, "Thử kết nối lại sau")
            return

        # Fetch thành công
        if self.stats:
            self.stats["consecutive_api_errors"] = 0
            if self.stats.get("health_status") in ("warning", "recovering"):
                self.stats["health_status"] = "healthy"

        if not jobs:
            # fetch_jobs trả list rỗng sau normalize (dữ liệu lỗi)
            raise TTCNoJobAvailable(f"[TTC] Jobs list rỗng sau normalize: {job_type}", 0)

        # Đưa vào queue (JobQueue tự dedup theo buff_id/job_key)
        added = self.queue.put_many(jobs, source="new_fetch")
        if added:
            self.log(
                f"Đã nạp {len(added)}/{len(jobs)} job {job_type} vào queue. "
                f"Queue hiện có: {self.queue.size()}",
                "api",
            )
            self.update_runtime_stats()
        else:
            self.log(
                f"Fetch {job_type} về {len(jobs)} job nhưng tất cả đã seen (trùng trong phiên).",
                "api",
            )
            # Không tăng error vì fetch thành công, chỉ không có job mới
            self.countdown_sleep(self.wait_no_job_delay, f"Chờ job mới {job_type}")

    # ------------------------------------------------------------------
    # API error handling
    # ------------------------------------------------------------------

    def _handle_api_error(self, error_str: str = ""):
        if not self.stats:
            return
        self.stats["consecutive_api_errors"] = (
            self.stats.get("consecutive_api_errors", 0) + 1
        )
        count = self.stats["consecutive_api_errors"]
        if count >= self.max_consecutive_api_errors:
            self.stats["health_status"] = "failed"
            self.stats["status"] = "error"
            self.stats["last_error"] = error_str or f"API lỗi liên tiếp {count} lần"
            self.log(
                f"API TTC lỗi liên tiếp {count} lần. Worker chuyển sang trạng thái lỗi.",
                "error",
            )
        else:
            self.stats["health_status"] = "warning"
            if error_str:
                self.stats["last_error"] = error_str
            self.log(
                f"Cảnh báo API: lỗi liên tiếp {count}/{self.max_consecutive_api_errors}.",
                "warning",
            )
        self.update_runtime_stats()

    # ------------------------------------------------------------------
    # countdown_sleep — có thể dừng bằng stop_event
    # ------------------------------------------------------------------

    def countdown_sleep(self, seconds: int, reason: str = ""):
        """Sleep với countdown, dừng ngay khi stop_event được set."""
        seconds = max(0, int(seconds))
        for i in range(seconds, 0, -1):
            if self.stop_event.is_set():
                break
            if self.logger:
                self.logger.status(
                    self.worker_id,
                    f"{reason}: [{i}s]" if reason else f"[{i}s]",
                    "waiting",
                )
            time.sleep(1)
        if self.logger and not self.stop_event.is_set():
            self.logger.status(self.worker_id, "Sẵn sàng", "info")
