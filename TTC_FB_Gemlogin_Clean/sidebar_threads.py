# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel

class SidebarThreads(QWidget):
    thread_selected = Signal(str)  # worker_id

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("DANH SÁCH LUỒNG")
        title.setStyleSheet("font-weight: bold; color: #58A6FF; font-size: 13px; padding-left: 4px;")
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self.on_item_changed)
        layout.addWidget(self.list_widget)

    def rebuild_list(self, worker_count):
        self.list_widget.clear()
        all_item = QListWidgetItem("All - Tổng quan")
        all_item.setData(Qt.UserRole, "all")
        self.list_widget.addItem(all_item)
        for i in range(1, worker_count + 1):
            item = QListWidgetItem(f"Luồng #{i} - Profile {i}")
            item.setData(Qt.UserRole, str(i))
            self.list_widget.addItem(item)
        
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def on_item_changed(self, current, previous):
        if current:
            worker_id = current.data(Qt.UserRole)
            self.thread_selected.emit(worker_id)

    def update_item_text(self, worker_id, profile_id):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item_worker_id = item.data(Qt.UserRole)
            if item_worker_id == "all":
                continue
            if item_worker_id == str(worker_id):
                item.setText(f"Luồng #{worker_id} - Profile {profile_id}")
                break
