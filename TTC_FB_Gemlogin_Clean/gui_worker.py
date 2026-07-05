# -*- coding: utf-8 -*-
import sys
import threading
import traceback
from copy import deepcopy

from PySide6.QtCore import QThread, Signal

from ttc_runtime import run_worker_config


class WorkerLogger:
    """Bridge ttc_runtime logs back to the GUI thread via Qt signals."""

    def __init__(self, thread_worker, worker_id):
        self.thread_worker = thread_worker
        self.worker_id = worker_id

    def log(self, worker_id, message, level="info"):
        self.thread_worker.log_signal.emit(str(worker_id), message, level)

    def status(self, worker_id, message, level="waiting"):
        self.thread_worker.status_signal.emit(str(worker_id), message, level)

    def update_stats(self, worker_id, stats):
        self.thread_worker.stats_signal.emit(str(worker_id), stats)

    def add_job_event(self, worker_id, event):
        self.thread_worker.job_event_signal.emit(str(worker_id), event)

    # Compatibility methods — để executor dùng standard logger style không crash
    def info(self, message):
        self.log(self.worker_id, message, "info")

    def warning(self, message):
        self.log(self.worker_id, message, "warning")

    def error(self, message):
        self.log(self.worker_id, message, "error")

    def debug(self, message):
        self.log(self.worker_id, message, "debug")


# Alias tương thích — GUI vẫn dùng tên TTCWorkerThread
class TTCWorkerThread(QThread):
    log_signal = Signal(str, str, str)       # worker_id, message, level
    status_signal = Signal(str, str, str)    # worker_id, message, level
    stats_signal = Signal(str, dict)         # worker_id, stats_dict
    job_event_signal = Signal(str, dict)     # worker_id, job_event_dict
    started_signal = Signal(str)             # worker_id
    error_signal = Signal(str, str)          # worker_id, error_message
    finished_signal = Signal(str)            # worker_id

    def __init__(self, worker_id, config):
        super().__init__()
        self.worker_id = str(worker_id)
        self.config = deepcopy(config)
        self.stop_event = threading.Event()
        self.logger = WorkerLogger(self, self.worker_id)

    def run(self):
        self.started_signal.emit(self.worker_id)
        try:
            run_worker_config(self.config, self.worker_id, self.stop_event, self.logger)
        except Exception as e:
            err_msg = f"{e}\n{traceback.format_exc()}"
            self.error_signal.emit(self.worker_id, err_msg)
        finally:
            self.finished_signal.emit(self.worker_id)

    def stop(self):
        self.stop_event.set()


# Backward-compat alias
BumxWorkerThread = TTCWorkerThread
