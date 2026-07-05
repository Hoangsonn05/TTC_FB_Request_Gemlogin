# -*- coding: utf-8 -*-
import sys
import datetime
import hashlib
import time
from copy import deepcopy
from collections import deque
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget,
    QMessageBox, QLabel, QSpinBox, QPushButton, QApplication
)
from PySide6.QtCore import Qt, Slot, QTimer

from theme import STYLE_SHEET
from sidebar_threads import SidebarThreads
from thread_config_panel import ThreadConfigPanel
from log_panel import LogPanel
from monitor_panel import MonitorPanel
from gui_worker import TTCWorkerThread, BumxWorkerThread
from ttc_config import load_multi_config, save_multi_config

CONFIG_PATH = Path(__file__).with_name("config.json")

# Alias tương thích
TTCMainWindow = None  # Sẽ được gán sau khi class định nghĩa xong

class BumxMainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.config_data = {}
        self.current_view_scope = "all"
        self.current_worker_id = None
        self.workers_metadata = {}  # worker_id -> dict chứa metadata runtime chi tiết
        self.workers_stats = {}     # worker_id -> dict chứa stats runtime realtime
        self.start_queue = []       # Hàng đợi khởi chạy tuần tự các luồng
        self.start_timer = None     # Timer điều phối khởi chạy tuần tự
        self.pending_log_queue = deque()
        self.pending_status = {}
        self.pending_stats = {}
        self.log_throttle_active = False
        self.dropped_low_priority_logs = 0
        self.last_log_flush_duration_ms = 0.0
        self.last_stats_flush_duration_ms = 0.0
        self.log_flush_batch_size = 150
        self.last_watchdog_warning_at = 0.0
        self.last_log_throttle_notice_at = 0.0

        self.setWindowTitle("TTC Automation GUI - PySide6")
        self.resize(860, 560)
        self.setMinimumSize(760, 480)

        self.init_ui()
        self.init_ui_pipelines()
        self.load_all_configs()

    def init_ui(self):
        self.setStyleSheet(STYLE_SHEET)
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Control Bar
        control_bar = QHBoxLayout()
        control_bar.setSpacing(6)

        control_bar.addWidget(QLabel("Số luồng:"))
        self.spin_worker_count = QSpinBox()
        self.spin_worker_count.setRange(1, 32)
        self.spin_worker_count.setMaximumWidth(60)
        control_bar.addWidget(self.spin_worker_count)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self.apply_workers)
        self.btn_save = QPushButton("Save Config")
        self.btn_save.clicked.connect(self.save_all)
        self.btn_reload = QPushButton("Reload")
        self.btn_reload.clicked.connect(self.load_all_configs)
        
        self.btn_start = QPushButton("Start Selected")
        self.btn_start.clicked.connect(self.start_selected)
        self.btn_stop = QPushButton("Stop Selected")
        self.btn_stop.clicked.connect(self.stop_selected)

        self.btn_start_all = QPushButton("Start All")
        self.btn_start_all.clicked.connect(self.start_all)
        self.btn_stop_all = QPushButton("Stop All")
        self.btn_stop_all.clicked.connect(self.stop_all)

        self.btn_clear = QPushButton("Clear Log")
        self.btn_clear.clicked.connect(self.clear_log)

        for btn in (self.btn_apply, self.btn_save, self.btn_reload, self.btn_start, 
                    self.btn_stop, self.btn_start_all, self.btn_stop_all, self.btn_clear):
            control_bar.addWidget(btn)

        control_bar.addStretch(1)
        root.addLayout(control_bar)

        # Splitter chính
        self.main_splitter = QSplitter(Qt.Vertical)
        root.addWidget(self.main_splitter)

        # Splitter trên (Sidebar + Khu cấu hình & giám sát)
        top_splitter = QSplitter(Qt.Horizontal)
        
        self.sidebar = SidebarThreads()
        self.sidebar.thread_selected.connect(self.on_thread_selected)
        top_splitter.addWidget(self.sidebar)

        # Khu giữa chỉ giữ monitor và cấu hình luồng.
        self.center_tabs = QTabWidget()
        
        
        self.monitor_panel = MonitorPanel()
        self.center_tabs.addTab(self.monitor_panel, "Giám Sát Chi Tiết")
        
        
        self.config_panel = ThreadConfigPanel()
        self.center_tabs.addTab(self.config_panel, "Config luồng")

        top_splitter.addWidget(self.center_tabs)

        top_splitter.setSizes([200, 640])
        self.main_splitter.addWidget(top_splitter)

        # Log Panel dưới
        self.log_panel = LogPanel()
        self.main_splitter.addWidget(self.log_panel)

        self.main_splitter.setSizes([340, 200])

    def init_ui_pipelines(self):
        self.stats_flush_timer = QTimer(self)
        self.stats_flush_timer.setInterval(300)
        self.stats_flush_timer.timeout.connect(self.flush_pending_stats)
        self.stats_flush_timer.start()

        self.status_flush_timer = QTimer(self)
        self.status_flush_timer.setInterval(500)
        self.status_flush_timer.timeout.connect(self.flush_pending_status)
        self.status_flush_timer.start()

        self.log_flush_timer = QTimer(self)
        self.log_flush_timer.setInterval(400)
        self.log_flush_timer.timeout.connect(self.flush_pending_logs)
        self.log_flush_timer.start()

        self.ui_watchdog_timer = QTimer(self)
        self.ui_watchdog_timer.setInterval(2000)
        self.ui_watchdog_timer.timeout.connect(self.ui_watchdog_tick)
        self.ui_watchdog_timer.start()

    def load_all_configs(self):
        if self.has_active_workers():
            QMessageBox.warning(self, "Cảnh báo", "Không thể reload cấu hình khi đang có luồng hoạt động!")
            self.log_panel.append_log(None, "Chặn reload cấu hình: có luồng đang hoạt động.", "warning")
            return

        try:
            self.config_data = load_multi_config(str(CONFIG_PATH))
        except Exception:
            self.config_data = {}

        if "workers" not in self.config_data:
            self.config_data = {
                "global": {
                    "worker_count": int(self.config_data.get("worker_count") or 1),
                    "gemlogin_url": self.config_data.get("gemlogin_url") or "http://localhost:1010"
                },
                "workers": []
            }
        
        worker_count = self.config_data.get("global", {}).get("worker_count", 1)
        self.spin_worker_count.setValue(worker_count)

        workers_list = self.config_data.get("workers", [])
        while len(workers_list) < worker_count:
            w_id = len(workers_list) + 1
            workers_list.append({
                "worker_id": str(w_id),
                "name": f"Worker {w_id}",
                "profile_id": str(w_id),
                "bumx_token": ""
            })
        self.config_data["workers"] = workers_list

        # Đồng bộ hóa metadata
        self.workers_metadata.clear()
        for w in workers_list:
            w_id = str(w.get("worker_id"))
            self.workers_metadata[w_id] = {
                "status": "idle",
                "thread": None,
                "stop_event": None,
                "started_at": None,
                "stopped_at": None,
                "last_error": None,
                "config_snapshot": None
            }

        self.sidebar.rebuild_list(worker_count)
        self.monitor_panel.rebuild(worker_count, workers_list)
        self.on_thread_selected(self.current_view_scope)
        self.log_panel.append_log(None, "Đã tải cấu hình từ config.json.", "config")

    def on_thread_selected(self, worker_id):
        self.save_current_worker_to_mem()
        worker_id = str(worker_id)
        self.current_view_scope = worker_id

        if worker_id == "all":
            self.current_worker_id = None
            self.config_panel.loaded_worker_id = None
            self.config_panel.setEnabled(False)
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.monitor_panel.highlight_worker("all")
            self.render_current_scope()
            return

        self.current_worker_id = worker_id
        w_cfg = self.get_worker_cfg(worker_id)
        if w_cfg:
            self.config_panel.load_config(w_cfg, worker_id=worker_id)

        # Bảo vệ config: Nếu luồng đang chạy, khóa panel cấu hình
        status = self.get_worker_status(worker_id)
        self.config_panel.setEnabled(status in ("idle", "stopped", "error"))
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.monitor_panel.highlight_worker(worker_id)
        self.render_current_scope()

    def save_current_worker_to_mem(self):
        # Chỉ lưu khi panel đang ở trạng thái kích hoạt để tránh lưu đè dữ liệu rỗng
        if self.current_worker_id and self.config_panel.isEnabled():
            if str(getattr(self.config_panel, "loaded_worker_id", "") or "") != str(self.current_worker_id):
                self.log_panel.append_log(
                    self.current_worker_id,
                    "Skip save: config panel is not loaded for this worker.",
                    "warning",
                )
                return
            w_cfg = self.get_worker_cfg(self.current_worker_id)
            if w_cfg:
                self.config_panel.save_config(w_cfg)
                self.sidebar.update_item_text(self.current_worker_id, w_cfg.get("profile_id", self.current_worker_id))

    def get_worker_cfg(self, worker_id):
        for w in self.config_data.get("workers", []):
            if str(w.get("worker_id")) == str(worker_id):
                return w
        return None

    def _token_hash(self, token):
        token = str(token or "").strip()
        if not token:
            return ""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:8]

    def _worker_token(self, worker_cfg):
        """Lấy TTC token từ config worker (migration alias bumx_token -> ttc_token)."""
        return str(
            worker_cfg.get("ttc_token") or worker_cfg.get("bumx_token") or worker_cfg.get("auth") or ""
        ).strip()

    def _worker_uid(self, worker_cfg):
        return str(worker_cfg.get("ttc_uid") or "").strip()

    def _worker_identity_text(self, worker_cfg):
        token_hash = self._token_hash(self._worker_token(worker_cfg)) or 'none'
        uid = self._worker_uid(worker_cfg) or 'none'
        return (
            f"profile_id={worker_cfg.get('profile_id', '')} "
            f"token_hash={token_hash} "
            f"ttc_uid={uid}"
        )

    def validate_unique_ttc_accounts(self, workers_to_start):
        """Kiểm tra không cho hai worker dùng cùng TTC token hoặc cùng TTC UID."""
        token_owner = {}
        uid_owner = {}

        for w in workers_to_start:
            w_id = str(w.get("worker_id"))
            token = self._worker_token(w)
            uid = self._worker_uid(w)

            if token:
                th = self._token_hash(token)
                if th in token_owner:
                    QMessageBox.warning(
                        self, "Trùng TTC Token",
                        f"Worker #{token_owner[th]} và Worker #{w_id} đang dùng cùng TTC token.\n"
                        "Vui lòng dùng mỗi worker một tài khoản TTC riêng."
                    )
                    return False
                token_owner[th] = w_id

            if uid:
                if uid in uid_owner:
                    QMessageBox.warning(
                        self, "Trùng TTC UID",
                        f"Worker #{uid_owner[uid]} và Worker #{w_id} đang dùng cùng TTC UID '{uid}'.\n"
                        "Vui lòng dùng mỗi worker một Facebook UID riêng."
                    )
                    return False
                uid_owner[uid] = w_id

        # Kiểm tra với workers đang chạy
        for active_id, meta in self.workers_metadata.items():
            if self.get_worker_status(active_id) not in ("starting", "running", "stopping"):
                continue
            active_cfg = meta.get("config_snapshot") or self.get_worker_cfg(active_id) or {}
            a_token_hash = self._token_hash(self._worker_token(active_cfg))
            a_uid = self._worker_uid(active_cfg)

            for w in workers_to_start:
                w_id = str(w.get("worker_id"))
                if w_id == str(active_id):
                    continue
                if a_token_hash and a_token_hash == self._token_hash(self._worker_token(w)):
                    QMessageBox.warning(
                        self, "Trùng TTC Token",
                        f"Worker #{active_id} đang chạy và Worker #{w_id} dùng cùng TTC token."
                    )
                    return False
                if a_uid and a_uid == self._worker_uid(w):
                    QMessageBox.warning(
                        self, "Trùng TTC UID",
                        f"Worker #{active_id} đang chạy và Worker #{w_id} dùng cùng TTC UID."
                    )
                    return False
        return True

    # Alias tương thích
    def validate_unique_bumx_tokens(self, workers_to_start):
        return self.validate_unique_ttc_accounts(workers_to_start)

    def render_current_scope(self):
        scope = str(self.current_view_scope)
        self.log_panel.render_scope(scope)

    def refresh_dashboard_for_scope(self):
        return

    def apply_workers(self):
        if self.has_active_workers():
            QMessageBox.warning(self, "Cảnh báo", "Không thể thay đổi số luồng khi đang có luồng hoạt động!")
            self.log_panel.append_log(None, "Chặn thay đổi số luồng: có luồng đang hoạt động.", "warning")
            return

        self.save_current_worker_to_mem()
        new_count = self.spin_worker_count.value()
        self.config_data["global"]["worker_count"] = new_count
        
        workers_list = self.config_data.get("workers", [])
        while len(workers_list) < new_count:
            w_id = len(workers_list) + 1
            workers_list.append({
                "worker_id": str(w_id),
                "name": f"Worker {w_id}",
                "profile_id": str(w_id),
                "ttc_token": "",
                "ttc_uid": ""
            })
        self.config_data["workers"] = workers_list

        # Giữ nguyên trạng thái của các worker đang chạy
        for w in workers_list:
            w_id = str(w.get("worker_id"))
            if w_id not in self.workers_metadata:
                self.workers_metadata[w_id] = {
                    "status": "idle",
                    "thread": None,
                    "stop_event": None,
                    "started_at": None,
                    "stopped_at": None,
                    "last_error": None,
                    "config_snapshot": None
                }

        self.sidebar.rebuild_list(new_count)
        self.monitor_panel.rebuild(new_count, workers_list)
        
        # Đồng bộ lại giao diện monitor của các luồng hiện tại
        for w_id, meta in self.workers_metadata.items():
            self.monitor_panel.update_row(w_id, meta["status"], error=meta["last_error"])

        self.log_panel.append_log(None, f"Đã cập nhật danh sách luồng lên {new_count} luồng.", "info")

    def save_all(self):
        self.save_current_worker_to_mem()
        try:
            save_multi_config(self.config_data, str(CONFIG_PATH))
            QMessageBox.information(self, "Thành Công", "Đã lưu toàn bộ cấu hình thành công!")
            self.log_panel.append_log(None, "Đã lưu cấu hình xuống config.json.", "config")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể lưu cấu hình: {e}")

    def start_selected(self):
        if self.current_view_scope == "all" or not self.current_worker_id:
            return
        self.save_current_worker_to_mem()
        w_id = self.current_worker_id
        
        status = self.get_worker_status(w_id)
        if status in ("starting", "running", "stopping"):
            QMessageBox.warning(self, "Cảnh báo", f"Luồng #{w_id} đang hoạt động ở trạng thái {status.upper()}!")
            return

        w_cfg = self.get_worker_cfg(w_id)
        if not w_cfg:
            return

        ttc_token = str(w_cfg.get("ttc_token") or w_cfg.get("bumx_token") or "").strip()
        if not ttc_token:
            QMessageBox.warning(self, "Cảnh báo", f"Luồng #{w_id} chưa cấu hình TTC Token!")
            return

        if not str(w_cfg.get("ttc_uid") or "").strip():
            QMessageBox.warning(self, "Cảnh báo", f"Luồng #{w_id} chưa cấu hình TTC UID (Facebook UID)!")
            return

        enabled_types = w_cfg.get("enabled_job_types") or []
        if not enabled_types:
            QMessageBox.warning(self, "Cảnh báo", f"Luồng #{w_id} chưa chọn loại nhiệm vụ nào!")
            return

        if not self.validate_unique_ttc_accounts([w_cfg]):
            return

        self.start_single_worker(w_id, w_cfg)

    def start_single_worker(self, w_id, w_cfg):
        try:
            # Tạo bản sao cấu hình độc lập để chạy nền
            config_snapshot = deepcopy(w_cfg)

            thread = TTCWorkerThread(w_id, config_snapshot)
            thread.log_signal.connect(self.on_worker_log)
            thread.status_signal.connect(self.on_worker_status_update)
            thread.stats_signal.connect(self.on_worker_stats_update)
            thread.started_signal.connect(self.on_worker_started)
            thread.error_signal.connect(self.on_worker_error)
            thread.finished_signal.connect(self.on_worker_finished)
            thread.finished.connect(thread.deleteLater)
            
            self.workers_metadata[w_id] = {
                "status": "starting",
                "thread": thread,
                "stop_event": thread.stop_event,
                "started_at": datetime.datetime.now(),
                "stopped_at": None,
                "last_error": None,
                "config_snapshot": config_snapshot
            }
            
            self.update_worker_status(w_id, "starting")
            self.log_panel.append_log(
                w_id,
                f"Worker #{w_id} identity: {self._worker_identity_text(config_snapshot)}",
                "start",
            )
            self.log_panel.append_log(w_id, f"Worker #{w_id} starting...", "start")
            
            thread.start()
        except Exception as e:
            self.update_worker_status(w_id, "error", error=str(e))
            self.log_panel.append_log(w_id, f"Lỗi khởi tạo luồng #{w_id}: {e}", "error")

    def stop_selected(self):
        if self.current_view_scope == "all" or not self.current_worker_id:
            return
        w_id = self.current_worker_id
        status = self.get_worker_status(w_id)
        if status in ("idle", "stopped", "error"):
            QMessageBox.information(self, "Thông báo", f"Luồng #{w_id} đang ở trạng thái dừng hoặc không hoạt động.")
            return

        self.stop_single_worker(w_id)

    def stop_single_worker(self, w_id):
        status = self.get_worker_status(w_id)
        if status in ("idle", "stopped", "error"):
            return

        self.update_worker_status(w_id, "stopping")
        self.log_panel.append_log(w_id, f"Đang gửi tín hiệu dừng Worker #{w_id}", "stop")
        
        meta = self.workers_metadata.get(w_id)
        if meta and meta["thread"]:
            meta["thread"].stop()

    def start_all(self):
        self.save_current_worker_to_mem()
        
        # 1. Kiểm tra trùng Profile ID GemLogin trước
        gemlogin_profiles = {}
        for w in self.config_data.get("workers", []):
            if not w.get("enabled", True):
                continue
            if not w.get("bumx_token"):
                continue
            w_id = str(w.get("worker_id"))
            
            if w.get("mode") == "gemlogin" or w.get("use_gemlogin"):
                pid = w.get("profile_id")
                if pid:
                    if pid in gemlogin_profiles:
                        QMessageBox.warning(
                            self, 
                            "Trùng Profile GemLogin", 
                            f"Lỗi: Luồng #{w_id} và Luồng #{gemlogin_profiles[pid]} dùng chung Profile ID '{pid}'!\nHủy lệnh Start All."
                        )
                        return
                    gemlogin_profiles[pid] = w_id

        # 2. Thu thập danh sách luồng cần chạy
        self.start_queue = []
        for w in self.config_data.get("workers", []):
            w_id = str(w.get("worker_id"))
            if not w.get("enabled", True):
                continue
            ttc_tok = str(w.get("ttc_token") or w.get("bumx_token") or "").strip()
            if not ttc_tok:
                continue
            
            status = self.get_worker_status(w_id)
            if status in ("starting", "running", "stopping"):
                continue
                
            self.start_queue.append((w_id, w))

        if not self.start_queue:
            QMessageBox.information(self, "Thông báo", "Không có luồng mới nào đủ điều kiện khởi chạy (hãy kiểm tra Enabled hoặc Token).")
            return

        # 3. Khởi chạy tuần tự tránh tắc nghẽn API/GemLogin bằng QTimer
        if not self.validate_unique_ttc_accounts([w for _, w in self.start_queue]):
            self.start_queue = []
            return

        self.log_panel.append_log(None, "Bắt đầu khởi chạy tuần tự các luồng cách nhau 5 giây...", "start")
        self.start_timer = QTimer()
        self.start_timer.timeout.connect(self.process_start_queue)
        self.start_timer.start(5000)

    def process_start_queue(self):
        if not self.start_queue:
            self.start_timer.stop()
            self.start_timer = None
            self.log_panel.append_log(None, "Hoàn tất xử lý hàng đợi khởi chạy luồng.", "start")
            return

        w_id, w_cfg = self.start_queue.pop(0)
        self.start_single_worker(w_id, w_cfg)

    def stop_all(self):
        # Dừng timer khởi chạy tuần tự nếu đang hoạt động
        if self.start_timer:
            self.start_timer.stop()
            self.start_timer = None
            self.start_queue = []
            self.log_panel.append_log(None, "Đã hủy hàng đợi khởi chạy tuần tự.", "stop")
        else:
            self.start_queue = []

        stopping_count = 0
        for w_id in self.workers_metadata.keys():
            status = self.get_worker_status(w_id)
            if status in ("starting", "running"):
                self.stop_single_worker(w_id)
                stopping_count += 1

        if stopping_count == 0:
            self.log_panel.append_log(None, "Không có luồng nào đang chạy để dừng.", "info")

    def clear_log(self):
        self.log_panel.clear_scope(self.current_view_scope)

    # --- Worker Signal Slots ---

    @Slot(str, str, str)
    def on_worker_log(self, worker_id, message, level):
        self.queue_log(worker_id, message, level)

    @Slot(str)
    def on_worker_started(self, worker_id):
        w_id = str(worker_id)
        self.update_worker_status(w_id, "running")
        self.log_panel.append_log(w_id, f"Worker #{w_id} running...", "start")

    @Slot(str, str)
    def on_worker_error(self, worker_id, err_msg):
        w_id = str(worker_id)
        self.update_worker_status(w_id, "error", error=err_msg)
        self.log_panel.append_log(w_id, f"Worker #{w_id} gặp lỗi: {err_msg.splitlines()[0]}", "error")

    @Slot(str)
    def on_worker_finished(self, worker_id):
        w_id = str(worker_id)
        status = self.get_worker_status(w_id)
        new_status = "error" if status == "error" else "stopped"
        
        self.update_worker_status(w_id, new_status)
        self.pending_status.pop(w_id, None)
        self.log_panel.update_status_state(w_id, "Countdown stopped.", "stop")
        self.log_panel.render_status_rows()
        
        meta = self.workers_metadata.get(w_id)
        if meta:
            meta["stopped_at"] = datetime.datetime.now()
            meta["thread"] = None

        self.log_panel.append_log(w_id, f"Worker #{w_id} đã dừng hoàn toàn.", "stop")

    @Slot(str, str, str)
    def on_worker_status_update(self, worker_id, message, level):
        w_id = str(worker_id)
        self.pending_status[w_id] = (message, level)

    @Slot(str, dict)
    def on_worker_stats_update(self, worker_id, stats):
        w_id = str(worker_id)
        self.pending_stats[w_id] = dict(stats)

    @Slot(str, dict)
    def on_worker_job_event(self, worker_id, event):
        return

    def queue_log(self, worker_id, message, level="info"):
        if not message:
            return

        level = str(level or "info")
        if self._should_drop_low_priority_log(level, message):
            self.dropped_low_priority_logs += 1
            return

        self.pending_log_queue.append((worker_id, message, level))

    def flush_pending_logs(self):
        started = time.perf_counter()
        now = time.monotonic()
        if self.dropped_low_priority_logs and now - self.last_log_throttle_notice_at >= 5:
            dropped = self.dropped_low_priority_logs
            self.dropped_low_priority_logs = 0
            self.last_log_throttle_notice_at = now
            self.pending_log_queue.appendleft((
                None,
                f"UI log throttling active, dropped {dropped} low-priority logs.",
                "warning",
            ))

        if not self.pending_log_queue:
            self.last_log_flush_duration_ms = (time.perf_counter() - started) * 1000
            return

        batch = []
        max_items = max(25, self.log_flush_batch_size)
        while self.pending_log_queue and len(batch) < max_items:
            batch.append(self.pending_log_queue.popleft())

        self.log_panel.append_log_batch(batch)
        self.last_log_flush_duration_ms = (time.perf_counter() - started) * 1000

    def flush_pending_status(self):
        if not self.pending_status:
            return

        updates = self.pending_status
        self.pending_status = {}
        for w_id, (message, level) in updates.items():
            self.log_panel.update_status_state(w_id, message, level)
            self.monitor_panel.update_row(w_id, self.get_worker_status(w_id), progress=message)
        self.log_panel.render_status_rows()

    def flush_pending_stats(self):
        started = time.perf_counter()
        if not self.pending_stats:
            self.last_stats_flush_duration_ms = (time.perf_counter() - started) * 1000
            return

        updates = self.pending_stats
        self.pending_stats = {}
        for w_id, stats in updates.items():
            self.workers_stats[w_id] = stats
            self.monitor_panel.update_stats(w_id, stats)

        self.last_stats_flush_duration_ms = (time.perf_counter() - started) * 1000

    def ui_watchdog_tick(self):
        pending_logs = len(self.pending_log_queue)
        slow_flush = self.last_log_flush_duration_ms > 120
        overloaded = pending_logs > 2000 or slow_flush

        if overloaded:
            self.log_throttle_active = True
            self.log_flush_batch_size = max(50, self.log_flush_batch_size // 2)
        elif pending_logs < 500 and self.last_log_flush_duration_ms < 60:
            self.log_throttle_active = False
            self.log_flush_batch_size = min(150, self.log_flush_batch_size + 25)

        now = time.monotonic()
        if overloaded and now - self.last_watchdog_warning_at > 30:
            self.last_watchdog_warning_at = now
            self.queue_log(
                None,
                (
                    "UI watchdog: log pipeline busy "
                    f"(pending={pending_logs}, log_flush={self.last_log_flush_duration_ms:.1f}ms, "
                    f"stats_flush={self.last_stats_flush_duration_ms:.1f}ms, rows={self.log_panel.table.rowCount()})."
                ),
                "warning",
            )

    def _should_drop_low_priority_log(self, level, message):
        if not self.log_throttle_active and len(self.pending_log_queue) <= 5000:
            return False

        keep_levels = {
            "error", "warning", "success", "blocked", "auth", "token",
            "stop", "start", "config",
        }
        if level in keep_levels:
            return False

        text = str(message).lower()
        if any(key in text for key in ("error", "warning", "auth", "blocked", "failed", "thất bại")):
            return False

        return level in {"info", "debug", "wait", "waiting", "api", "browser", "facebook", "livecheck"}

    def update_global_summary(self):
        return

    # --- Trạng thái Helpers ---

    def get_worker_status(self, w_id):
        w_id = str(w_id)
        if w_id not in self.workers_metadata:
            return "idle"
        return self.workers_metadata[w_id]["status"]

    def has_active_workers(self):
        for w_id in self.workers_metadata:
            if self.get_worker_status(w_id) in ("starting", "running", "stopping"):
                return True
        return False

    def update_worker_status(self, w_id, status, error=None):
        w_id = str(w_id)
        if w_id not in self.workers_metadata:
            self.workers_metadata[w_id] = {
                "status": "idle",
                "thread": None,
                "stop_event": None,
                "started_at": None,
                "stopped_at": None,
                "last_error": None,
                "config_snapshot": None
            }
        
        self.workers_metadata[w_id]["status"] = status
        if error is not None:
            self.workers_metadata[w_id]["last_error"] = error

        # Cập nhật trực tiếp lên bảng Monitor
        self.monitor_panel.update_row(w_id, status, error=error)

        # Nếu là luồng hiện tại đang được xem, cập nhật trạng thái bật/tắt của panel cấu hình
        if self.current_worker_id == w_id:
            self.config_panel.setEnabled(status in ("idle", "stopped", "error"))
        self.refresh_dashboard_for_scope()

    def closeEvent(self, event):
        for timer_name in (
            "stats_flush_timer", "status_flush_timer", "log_flush_timer", "ui_watchdog_timer"
        ):
            timer = getattr(self, timer_name, None)
            if timer:
                timer.stop()
        self.flush_pending_stats()
        self.flush_pending_status()
        self.flush_pending_logs()
        self.stop_all()
        # Chờ các thread dừng hẳn trước khi đóng hoàn toàn ứng dụng
        for meta in self.workers_metadata.values():
            if meta["thread"] and meta["thread"].isRunning():
                meta["thread"].wait(2000)
        super().closeEvent(event)


# Alias public
TTCMainWindow = BumxMainWindow


def main():
    app = QApplication(sys.argv)
    window = BumxMainWindow()
    window.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())


