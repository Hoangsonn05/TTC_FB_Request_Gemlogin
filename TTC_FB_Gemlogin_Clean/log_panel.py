# -*- coding: utf-8 -*-
from collections import deque
from datetime import datetime

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView
)

from theme import get_log_font, LOG_COLORS, FALLBACK_ICONS, resolve_level, strip_existing_log_prefix


class LogPanel(QWidget):
    def __init__(self, max_rows=3000):
        super().__init__()
        self.max_rows = max_rows
        self.trim_margin = 200
        self.current_scope = "all"
        self.log_entries = deque(maxlen=max_rows)
        self.status_entries = {}
        self.status_rows = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        title_bar = QHBoxLayout()
        title = QLabel("NHẬT KÝ HOẠT ĐỘNG REALTIME")
        title.setStyleSheet("font-weight: bold; color: #58A6FF; font-size: 13px; padding-left: 4px;")
        title_bar.addWidget(title)
        layout.addLayout(title_bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["", "Thời Gian", "Luồng", "Nội Dung"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

        self.table.setColumnWidth(0, 34)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 90)
        self.table.setFont(get_log_font())

        layout.addWidget(self.table)

    def append_log(self, worker_id, message, level="info"):
        if not message:
            return

        self.append_log_batch([(worker_id, message, level)])

    def append_log_batch(self, raw_entries):
        if not raw_entries:
            return

        entries = [
            self._make_entry(worker_id, message, level)
            for worker_id, message, level in raw_entries
            if message
        ]
        if not entries:
            return

        for entry in entries:
            self.log_entries.append(entry)

        visible_entries = [
            entry for entry in entries
            if self._entry_in_scope(entry, self.current_scope)
        ]
        if not visible_entries:
            return

        should_scroll = self._should_auto_scroll()
        self.table.setUpdatesEnabled(False)
        try:
            self._remove_status_rows()
            for entry in visible_entries:
                self._append_entry_row(entry, trim=False, scroll=False)
            self._trim_visible_rows()
            self._append_status_rows()
        finally:
            self.table.setUpdatesEnabled(True)

        if should_scroll:
            self.table.scrollToBottom()

    def update_status(self, worker_id, message, level="waiting"):
        if not message:
            return

        self.update_status_state(worker_id, message, level)
        self.render_status_rows()

    def update_status_state(self, worker_id, message, level="waiting"):
        if not message:
            return

        entry = self._make_entry(worker_id, message, level)
        worker_key = entry["worker_id"] or "system"
        self.status_entries[worker_key] = entry

        if self._is_status_done(entry["message"]):
            self.status_entries.pop(worker_key, None)

    def render_status_rows(self):
        should_scroll = self._should_auto_scroll()
        self.table.setUpdatesEnabled(False)
        try:
            self._remove_status_rows()
            self._append_status_rows()
        finally:
            self.table.setUpdatesEnabled(True)

        if should_scroll:
            self.table.scrollToBottom()

    def render_scope(self, scope="all"):
        self.current_scope = str(scope)
        should_scroll = self._should_auto_scroll()
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.status_rows.clear()

        try:
            for entry in self.log_entries:
                if self._entry_in_scope(entry, self.current_scope):
                    self._append_entry_row(entry, trim=False, scroll=False)
            self._trim_visible_rows()
            self._append_status_rows()
        finally:
            self.table.setUpdatesEnabled(True)

        if should_scroll:
            self.table.scrollToBottom()

    def clear_log(self):
        self.log_entries.clear()
        self.status_entries.clear()
        self.status_rows.clear()
        self.table.setRowCount(0)

    def clear_scope(self, scope="all"):
        scope = str(scope)
        if scope == "all":
            self.clear_log()
            return

        self.log_entries = deque(
            (entry for entry in self.log_entries if str(entry.get("worker_id", "")) != scope),
            maxlen=self.max_rows
        )
        self.status_entries.pop(scope, None)
        self.status_rows.pop(scope, None)
        self.render_scope(scope)

    def _entry_in_scope(self, entry, scope):
        scope = str(scope)
        if scope == "all":
            return True
        return str(entry.get("worker_id", "")) == scope

    def _make_entry(self, worker_id, message, level):
        timestamp, clean_line = strip_existing_log_prefix(message)
        timestamp = timestamp or datetime.now().strftime("%H:%M:%S")
        resolved = level if level in LOG_COLORS and level != "info" else resolve_level(clean_line, level)
        return {
            "timestamp": timestamp,
            "worker_id": str(worker_id) if worker_id else "",
            "message": clean_line,
            "level": resolved,
        }

    def _append_entry_row(self, entry, trim=True, scroll=True):
        if trim:
            self._trim_visible_rows()

        row = self.table.rowCount()
        self.table.insertRow(row)
        self._set_row_items(row, entry)
        if scroll:
            self.table.scrollToBottom()
        return row

    def _set_row_items(self, row, entry):
        resolved = entry.get("level", "info")
        worker_id = entry.get("worker_id", "")

        icon_item = QTableWidgetItem(FALLBACK_ICONS.get(resolved, "INFO"))
        time_item = QTableWidgetItem(f"[{entry.get('timestamp', '')}]")
        worker_item = QTableWidgetItem(f"Worker {worker_id}" if worker_id else "Hệ Thống")
        msg_item = QTableWidgetItem(str(entry.get("message", "")))

        color = QColor(LOG_COLORS.get(resolved, LOG_COLORS["info"]))
        for item in (icon_item, time_item, worker_item, msg_item):
            item.setForeground(color)

        self.table.setItem(row, 0, icon_item)
        self.table.setItem(row, 1, time_item)
        self.table.setItem(row, 2, worker_item)
        self.table.setItem(row, 3, msg_item)

    def _is_status_done(self, message):
        text = str(message)
        return "[Done]" in text or "Countdown stopped" in text

    def _append_status_rows(self):
        self.status_rows.clear()
        for worker_key, entry in self.status_entries.items():
            if self._entry_in_scope(entry, self.current_scope):
                row = self._append_entry_row(entry, trim=False, scroll=False)
                self.status_rows[worker_key] = row

    def _remove_status_rows(self):
        for row in sorted(self.status_rows.values(), reverse=True):
            if 0 <= row < self.table.rowCount():
                self.table.removeRow(row)
        self.status_rows.clear()

    def _trim_visible_rows(self):
        overflow = self.table.rowCount() - self.max_rows
        if overflow <= self.trim_margin:
            return

        remove_count = max(overflow, self.trim_margin)
        for _ in range(min(remove_count, self.table.rowCount())):
            self.table.removeRow(0)

    def _should_auto_scroll(self):
        scrollbar = self.table.verticalScrollBar()
        return scrollbar.value() >= max(0, scrollbar.maximum() - 4)
