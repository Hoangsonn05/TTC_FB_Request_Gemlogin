# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

HEALTH_DISPLAY = {
    "healthy": ("Healthy", "#3FB950"),
    "warning": ("Warning", "#D29922"),
    "recovering": ("Recovering", "#58A6FF"),
    "failed": ("Failed", "#F85149"),
    "blocked": ("Blocked", "#F85149"),
}


class MonitorPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_worker_id = "all"
        self.worker_rows = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.table = QTableWidget(0, 16)
        self.table.setHorizontalHeaderLabels([
            "Worker", "Profile ID", "Status", "Queue", "Job ID / Type",
            "Done", "Failed", "Skipped", "Reaction", "Xu Kiếm", "Số Dư TTC",
            "Runtime", "Blocked", "Health", "Restart", "Last Message / Error"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        for col in range(15):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(15, QHeaderView.Stretch)

        widths = [80, 80, 90, 50, 90, 50, 50, 60, 65, 75, 85, 70, 75, 85, 55]
        for col, width in enumerate(widths):
            self.table.setColumnWidth(col, width)

        layout.addWidget(self.table)

    def rebuild(self, worker_count, workers_data):
        self.table.setRowCount(0)
        self.worker_rows.clear()
        for i in range(1, worker_count + 1):
            row = self.table.rowCount()
            self.table.insertRow(row)

            w_id = str(i)
            self.worker_rows[w_id] = row
            profile_id = ""
            name = f"Worker {w_id}"
            for w in workers_data:
                if str(w.get("worker_id")) == w_id:
                    profile_id = w.get("profile_id", "")
                    name = w.get("name", f"Worker {w_id}")
                    break

            values = [
                name, profile_id, "Idle", "0", "None", "0", "0", "0", "0",
                "0", "", "00:00:00", "None", "Healthy", "0", "Ready"
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, w_id)
                if col == 15:
                    item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
        self.highlight_worker(self.selected_worker_id)

    def update_row(self, worker_id, status, progress="", error=""):
        w_id_str = str(worker_id)
        r = self._find_worker_row(w_id_str)
        if r is None:
            return

        status_text, status_color = self._status_display(status)
        self.table.item(r, 2).setText(status_text)
        self.table.item(r, 2).setForeground(QColor(status_color))

        if progress:
            self.table.item(r, 15).setText(progress)
        if error:
            short_err = error.split("\n")[0]
            self.table.item(r, 15).setText(f"Error: {short_err}")
            self.table.item(r, 15).setForeground(QColor("#F85149"))
            self.table.item(r, 15).setToolTip(error)

    def update_stats(self, worker_id, stats):
        w_id_str = str(worker_id)
        r = self._find_worker_row(w_id_str)
        if r is None:
            return

        status = stats.get("status", "idle")
        status_text, status_color = self._status_display(status)
        self.table.item(r, 2).setText(status_text)
        self.table.item(r, 2).setForeground(QColor(status_color))

        self.table.item(r, 3).setText(str(stats.get("queue_size", 0)))

        curr_job = "None"
        job_id = stats.get("current_job_id") or stats.get("current_job_buff_id")
        job_type = stats.get("current_job_type", "")
        if job_id:
            # Rút gọn job_type TTC cho hiển thị
            short_map = {
                "ttc_like_post_vip_cheo": "Like↑Chéo",
                "ttc_like_post_vip_re": "Like↑Rẻ",
                "ttc_reaction_vip_cheo": "CX↑Chéo",
                "ttc_reaction_vip_re": "CX↑Rẻ",
                "ttc_comment": "CMT",
                "ttc_follow": "Follow",
                "ttc_like_page": "Page",
            }
            j_short = short_map.get(job_type, job_type[:8] if job_type else "?")
            curr_job = f"[{j_short}] {str(job_id)[-12:]}"
        self.table.item(r, 4).setText(curr_job)

        self.table.item(r, 5).setText(str(stats.get("total_done", 0)))
        self.table.item(r, 6).setText(str(stats.get("total_failed", 0)))
        self.table.item(r, 7).setText(str(stats.get("total_skipped", 0)))
        # Cột 8: tổng reaction/like_post done
        total_reaction = (
            stats.get("total_reaction_done", 0)
            + stats.get("total_like_post_done", 0)
        )
        self.table.item(r, 8).setText(str(total_reaction))

        self.table.item(r, 9).setText(str(stats.get("earned_coin", stats.get("total_coin", 0))))
        self.table.item(r, 10).setText(str(stats.get("account_balance", "")))
        self.table.item(r, 11).setText(stats.get("elapsed_time", "00:00:00"))

        blocked_text = stats.get("blocked_display", "None")
        self.table.item(r, 12).setText(blocked_text)
        self.table.item(r, 12).setForeground(
            QColor("#F85149" if blocked_text in ("Reaction", "Comment", "Both") else "#8B949E")
        )

        health = stats.get("health_status", "healthy")
        health_text, health_color = HEALTH_DISPLAY.get(health, ("Healthy", "#3FB950"))
        self.table.item(r, 13).setText(health_text)
        self.table.item(r, 13).setForeground(QColor(health_color))

        restart_count = stats.get("restart_count", 0)
        self.table.item(r, 14).setText(str(restart_count))
        self.table.item(r, 14).setForeground(
            QColor("#D29922" if restart_count > 0 else "#8B949E")
        )

        last_err = stats.get("last_error")
        last_msg = stats.get("last_message")
        if status == "error" and last_err:
            short_err = last_err.split("\n")[0]
            self.table.item(r, 15).setText(f"Error: {short_err}")
            self.table.item(r, 15).setForeground(QColor("#F85149"))
            self.table.item(r, 15).setToolTip(last_err)
        elif health == "recovering" and stats.get("last_recovery_reason"):
            reason = stats.get("last_recovery_reason", "")
            self.table.item(r, 15).setText(reason)
            self.table.item(r, 15).setForeground(QColor("#58A6FF"))
            self.table.item(r, 15).setToolTip(reason)
        elif last_msg:
            self.table.item(r, 15).setText(last_msg)
            self.table.item(r, 15).setForeground(QColor("#8B949E"))
            self.table.item(r, 15).setToolTip("")

    def highlight_worker(self, worker_id):
        self.selected_worker_id = str(worker_id)
        highlight = QColor("#1F2937")
        normal = QColor("#0D1117")
        for r in range(self.table.rowCount()):
            row_worker_id = self._row_worker_id(r)
            bg = highlight if self.selected_worker_id != "all" and row_worker_id == self.selected_worker_id else normal
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item:
                    item.setBackground(bg)

    def _row_worker_id(self, row):
        item = self.table.item(row, 0)
        if not item:
            return ""
        item_worker_id = item.data(Qt.UserRole)
        if item_worker_id:
            return str(item_worker_id)
        text = item.text()
        parts = text.split()
        return parts[-1] if parts else ""

    def _find_worker_row(self, worker_id):
        worker_id = str(worker_id)
        row = self.worker_rows.get(worker_id)
        if row is not None and 0 <= row < self.table.rowCount():
            return row

        for r in range(self.table.rowCount()):
            if self._row_worker_id(r) == worker_id:
                self.worker_rows[worker_id] = r
                return r
        return None

    def _status_display(self, status):
        return {
            "idle": ("Idle", "#8B949E"),
            "starting": ("Starting", "#58A6FF"),
            "running": ("Running", "#3FB950"),
            "stopping": ("Stopping", "#D29922"),
            "stopped": ("Stopped", "#F85149"),
            "error": ("Error", "#F85149"),
            "blocked": ("Blocked", "#F85149"),
        }.get(status, ("Idle", "#8B949E"))
