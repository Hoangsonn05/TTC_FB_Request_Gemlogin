# -*- coding: utf-8 -*-
import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class StatCard(QFrame):
    def __init__(self, title, value, border_color="#30363D"):
        super().__init__()
        self.setStyleSheet(f"""
            StatCard {{
                background-color: #161B22;
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-size: 11px; color: #8B949E; font-weight: bold;")
        self.lbl_title.setAlignment(Qt.AlignCenter)

        self.lbl_value = QLabel(str(value))
        self.lbl_value.setStyleSheet("font-size: 20px; color: #58A6FF; font-weight: bold;")
        self.lbl_value.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

    def set_value(self, val, color=None):
        self.lbl_value.setText(str(val))
        if color:
            self.lbl_value.setStyleSheet(f"font-size: 20px; color: {color}; font-weight: bold;")

    def set_title(self, title):
        self.lbl_title.setText(str(title))


class DashboardPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.lbl_section = QLabel("TỔNG QUAN HỆ THỐNG BUMX")
        self.lbl_section.setStyleSheet("font-weight: bold; color: #58A6FF; font-size: 12px;")
        layout.addWidget(self.lbl_section)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(8)
        self.card_total = StatCard("TỔNG SỐ LUỒNG", "0", "#30363D")
        self.card_running = StatCard("ĐANG CHẠY", "0", "#238636")
        self.card_idle = StatCard("CHỜ CHẠY", "0", "#30363D")
        self.card_error = StatCard("BỊ LỖI", "0", "#DA3633")
        self.card_coin = StatCard("TỔNG XU TÍCH LŨY", "0", "#E3B341")
        for card in (self.card_total, self.card_running, self.card_idle, self.card_error, self.card_coin):
            cards_layout.addWidget(card)
        layout.addLayout(cards_layout)

        cards_layout2 = QHBoxLayout()
        cards_layout2.setSpacing(8)
        self.card_done = StatCard("JOB THÀNH CÔNG", "0", "#238636")
        self.card_failed = StatCard("JOB THẤT BẠI", "0", "#DA3633")
        self.card_skipped = StatCard("JOB BỎ QUA", "0", "#8F949E")
        self.card_reaction = StatCard("LIKE / REACTION", "0", "#58A6FF")
        self.card_comment = StatCard("COMMENT / MỞ KHÓA", "0", "#BC8CFF")
        for card in (self.card_done, self.card_failed, self.card_skipped, self.card_reaction, self.card_comment):
            cards_layout2.addWidget(card)
        layout.addLayout(cards_layout2)

        lbl_guide = QLabel("Bảng giám sát hệ thống cập nhật realtime theo từng tài khoản.")
        lbl_guide.setStyleSheet("color: #8B949E; font-style: italic; font-size: 11px; padding-left: 2px;")
        layout.addWidget(lbl_guide)
        layout.addStretch(1)

    def update_summary(self, stats_summary):
        self.card_total.setVisible(True)
        self.card_comment.setVisible(True)
        self.lbl_section.setText("TỔNG QUAN HỆ THỐNG BUMX")
        self.card_total.set_title("TỔNG SỐ LUỒNG")
        self.card_running.set_title("ĐANG CHẠY")
        self.card_idle.set_title("CHỜ CHẠY")
        self.card_error.set_title("BỊ LỖI")
        self.card_coin.set_title("TỔNG XU TÍCH LŨY")
        self.card_done.set_title("JOB THÀNH CÔNG")
        self.card_failed.set_title("JOB THẤT BẠI")
        self.card_skipped.set_title("JOB BỎ QUA")
        self.card_reaction.set_title("LIKE / REACTION")
        self.card_comment.set_title("COMMENT / MỞ KHÓA")

        self.card_total.set_value(stats_summary.get("total_workers", 0))
        self.card_running.set_value(stats_summary.get("running_workers", 0), "#3FB950")
        self.card_idle.set_value(stats_summary.get("idle_workers", 0), "#8B949E")
        self.card_error.set_value(stats_summary.get("error_workers", 0), "#F85149")
        self.card_done.set_value(stats_summary.get("total_done_all", 0), "#3FB950")
        self.card_failed.set_value(stats_summary.get("total_failed_all", 0), "#F85149")
        self.card_skipped.set_value(stats_summary.get("total_skipped_all", 0), "#8B949E")
        self.card_reaction.set_value(stats_summary.get("total_reaction_done_all", 0), "#58A6FF")
        self.card_coin.set_value(stats_summary.get("total_coin_all", 0), "#F2C744")
        total_cmt = stats_summary.get("total_comment_done_all", 0)
        unlock_cmt = stats_summary.get("total_unlock_comment_done_all", 0)
        self.card_comment.set_value(f"{total_cmt} ({unlock_cmt} khóa)", "#D2A8FF")

    def update_worker_summary(self, worker_id, stats=None, worker_cfg=None, metadata=None):
        stats = stats or {}
        worker_cfg = worker_cfg or {}
        metadata = metadata or {}

        status = metadata.get("status") or stats.get("status", "idle")
        health = stats.get("health_status", "healthy")
        self.lbl_section.setText(f"TỔNG QUAN WORKER #{worker_id}")
        self.card_total.setVisible(False)
        self.card_comment.setVisible(False)
        self.card_running.set_title("PROFILE ID")
        self.card_idle.set_title("STATUS")
        self.card_error.set_title("HEALTH")
        self.card_coin.set_title("QUEUE SIZE")
        self.card_done.set_title("DONE")
        self.card_failed.set_title("FAILED")
        self.card_skipped.set_title("SKIPPED / REPORTED")
        self.card_reaction.set_title("REACTION / COMMENT")

        self.card_running.set_value(worker_cfg.get("profile_id", ""), "#58A6FF")
        self.card_idle.set_value(status, "#3FB950" if status == "running" else "#8B949E")
        self.card_error.set_value(health, "#3FB950" if health == "healthy" else "#F85149")
        self.card_coin.set_value(stats.get("queue_size", 0), "#F2C744")
        self.card_done.set_value(stats.get("total_done", 0), "#3FB950")
        self.card_failed.set_value(stats.get("total_failed", 0), "#F85149")
        self.card_skipped.set_value(
            f"{stats.get('total_skipped', 0)} / {stats.get('total_reported', 0)}",
            "#D29922",
        )
        self.card_reaction.set_value(
            f"{stats.get('total_reaction_done', 0)} / {stats.get('total_comment_done', 0)}",
            "#58A6FF",
        )


class JobHistoryPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.row_by_key = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Thời Gian", "Luồng", "Profile ID", "Buff ID", "Loại Job",
            "Trạng Thái", "Thời Lượng", "Kết Quả Chi Tiết",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        for col in range(7):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 110)
        self.table.setColumnWidth(6, 70)
        layout.addWidget(self.table)

    def make_key(self, worker_id, buff_id):
        return f"{str(worker_id or '')}:{str(buff_id or '')}"

    def normalize_status(self, status, reason="", submit_message=""):
        status = str(status or "").strip().lower()
        combined = f"{str(reason or '').lower()} {str(submit_message or '').lower()}"
        known = {
            "done", "failed", "skipped", "reported", "recovery",
            "blocked", "full", "dead_post", "unknown",
        }
        if status in known:
            return status
        if "stale_duplicate_pending" in combined or "blocked_pending_mission" in combined or "reported" in combined:
            return "reported"
        if "recovery" in combined:
            return "recovery"
        if "job_full" in combined or "full" in combined:
            return "full"
        if "dead_post" in combined or "post die" in combined or "not live" in combined:
            return "dead_post"
        return "unknown"

    def add_job_row(self, event, max_rows=1000, scroll=True):
        timestamp = event.get("_timestamp") or datetime.datetime.now().strftime("%H:%M:%S")
        w_id = str(event.get("worker_id") or "")
        profile_id = str(event.get("profile_id") or "")
        buff_id = str(event.get("buff_id") or "")
        job_type = str(event.get("job_type") or "")
        duration = f"{float(event.get('duration_sec', 0.0) or 0.0):.1f}s"
        reason = str(event.get("reason", "") or "")
        submit_msg = str(event.get("submit_message", "") or "")
        status = self.normalize_status(event.get("status"), reason, submit_msg)

        key = self.make_key(w_id, buff_id)
        row = self.row_by_key.get(key)
        if row is None:
            if self.table.rowCount() >= max_rows:
                self.table.removeRow(0)
                self.row_by_key = {k: r - 1 for k, r in self.row_by_key.items() if r > 0}
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.row_by_key[key] = row

        time_item = QTableWidgetItem(timestamp)
        worker_item = QTableWidgetItem(f"Worker {w_id}")
        profile_item = QTableWidgetItem(profile_id)
        buff_item = QTableWidgetItem(buff_id)
        j_type_str = "Like" if job_type == "like_facebook" else "Comment" if job_type == "like_poster" else job_type
        type_item = QTableWidgetItem(j_type_str)

        status_emoji = {
            "done": "Done 🟢",
            "failed": "Failed 🔴",
            "skipped": "Skipped 🟡",
            "reported": "Reported 🟣",
            "recovery": "Recovery 🔵",
            "blocked": "Blocked 🔴",
            "full": "Full 🟡",
            "dead_post": "Dead/Post Die 🟡",
            "unknown": "Unknown ⚪",
        }.get(status, "Unknown ⚪")
        status_item = QTableWidgetItem(status_emoji)
        status_color = {
            "done": "#3FB950",
            "failed": "#F85149",
            "skipped": "#D29922",
            "reported": "#A371F7",
            "recovery": "#58A6FF",
            "blocked": "#F85149",
            "full": "#D29922",
            "dead_post": "#D29922",
            "unknown": "#8B949E",
        }.get(status, "#8B949E")
        status_item.setForeground(QColor(status_color))

        dur_item = QTableWidgetItem(duration)
        detail_str = submit_msg
        if reason:
            detail_str += f" ({reason})"
        detail_item = QTableWidgetItem(detail_str)

        for item in (time_item, worker_item, profile_item, buff_item, type_item, status_item, dur_item):
            item.setTextAlignment(Qt.AlignCenter)
        detail_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.table.setItem(row, 0, time_item)
        self.table.setItem(row, 1, worker_item)
        self.table.setItem(row, 2, profile_item)
        self.table.setItem(row, 3, buff_item)
        self.table.setItem(row, 4, type_item)
        self.table.setItem(row, 5, status_item)
        self.table.setItem(row, 6, dur_item)
        self.table.setItem(row, 7, detail_item)

        if scroll:
            self.table.scrollToBottom()

    def clear_history(self):
        self.table.setRowCount(0)
        self.row_by_key.clear()

    def render_records(self, records, scope="all", max_rows=1000):
        scrollbar = self.table.verticalScrollBar()
        should_scroll = scrollbar.value() >= max(0, scrollbar.maximum() - 4)
        self.table.setUpdatesEnabled(False)
        self.clear_history()
        scope = str(scope)
        try:
            for record in records:
                if scope != "all" and str(record.worker_id) != scope:
                    continue
                event = {
                    "_timestamp": record.timestamp_end.strftime("%H:%M:%S"),
                    "worker_id": record.worker_id,
                    "profile_id": record.profile_id,
                    "buff_id": record.buff_id,
                    "job_type": record.job_type,
                    "status": record.status,
                    "duration_sec": record.duration_sec,
                    "reason": record.reason,
                    "submit_message": record.submit_message,
                }
                self.add_job_row(event, max_rows=max_rows, scroll=False)
        finally:
            self.table.setUpdatesEnabled(True)
        if should_scroll:
            self.table.scrollToBottom()
