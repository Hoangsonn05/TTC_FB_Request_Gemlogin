# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QSpinBox, QCheckBox, QPushButton, QScrollArea
)
from PySide6.QtCore import Qt

from ttc_job_types import ALL_JOB_TYPES

TTC_JOB_TYPE_LABELS = {
    "ttc_like_post_vip_cheo": "Like Post VIP Chéo",
    "ttc_like_post_vip_re":   "Like Post VIP Rẻ",
    "ttc_reaction_vip_cheo":  "Cảm Xúc VIP Chéo",
    "ttc_reaction_vip_re":    "Cảm Xúc VIP Rẻ",
    "ttc_comment":            "Comment",
    "ttc_follow":             "Follow",
    "ttc_like_page":          "Like Page",
}


class ThreadConfigPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.loaded_worker_id = None
        self._job_type_checkboxes = {}  # job_type -> QCheckBox
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)

        # 1. Browser Config
        browser_group = QGroupBox("Browser Cấu Hình")
        bg_layout = QGridLayout(browser_group)
        bg_layout.setSpacing(6)
        bg_layout.setContentsMargins(8, 12, 8, 8)

        self.chk_enabled = QCheckBox("Bật Luồng Này")
        self.chk_use_gemlogin = QCheckBox("Dùng GemLogin")
        self.chk_headless = QCheckBox("Chạy Ẩn (Headless)")
        self.chk_headless.setToolTip(
            "Khi dùng GemLogin, headless luôn bắt buộc = True\n"
            "(browser-context fetch cần session/cookie của profile, không cần hiển thị cửa sổ)"
        )
        self.chk_auto_close = QCheckBox("Tự Đóng Profile")
        self.chk_use_cookie = QCheckBox("Dùng Cookie")

        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["gemlogin", "local_chrome"])

        self.txt_gemlogin_url = QLineEdit()
        self.txt_profile_id = QLineEdit()
        self.txt_cookie = QLineEdit()
        self.txt_cookie.setEchoMode(QLineEdit.Password)

        bg_layout.addWidget(self.chk_enabled, 0, 0)
        bg_layout.addWidget(self.chk_use_gemlogin, 0, 1)
        bg_layout.addWidget(self.chk_headless, 1, 0)
        bg_layout.addWidget(self.chk_auto_close, 1, 1)
        bg_layout.addWidget(QLabel("Chế độ:"), 2, 0)
        bg_layout.addWidget(self.cmb_mode, 2, 1)
        bg_layout.addWidget(QLabel("GemLogin URL:"), 3, 0)
        bg_layout.addWidget(self.txt_gemlogin_url, 3, 1)
        bg_layout.addWidget(QLabel("Profile ID:"), 4, 0)
        bg_layout.addWidget(self.txt_profile_id, 4, 1)
        bg_layout.addWidget(self.chk_use_cookie, 5, 0)
        bg_layout.addWidget(QLabel("Cookie:"), 6, 0)
        bg_layout.addWidget(self.txt_cookie, 6, 1)

        # Kết nối signal: khi toggle use_gemlogin thì tự động lock headless
        self.chk_use_gemlogin.toggled.connect(self._on_use_gemlogin_toggled)
        # Set trạng thái ban đầu
        self._on_use_gemlogin_toggled(self.chk_use_gemlogin.isChecked())

        self.cmb_action_executor = QComboBox()
        self.cmb_action_executor.addItems([
            "facebook_graphql_context", "dry_run", "unsupported", "browser_context"
        ])
        self.cmb_action_executor.setToolTip(
            "facebook_graphql_context: thực hiện Facebook action qua GraphQL trong browser context (không cần provider URL);\n"
            "dry_run: mô phỏng, không claim;\n"
            "unsupported: không action, không claim."
        )
        self.chk_action_verify_after = QCheckBox("Verify sau action")
        self.chk_action_fail_closed = QCheckBox("Fail closed nếu chưa verified")
        self.spin_action_timeout_ms = QSpinBox()
        self.spin_action_timeout_ms.setRange(1000, 120000)
        self.spin_action_timeout_ms.setSingleStep(1000)
        self.spin_action_max_retry = QSpinBox()
        self.spin_action_max_retry.setRange(0, 10)

        bg_layout.addWidget(QLabel("Action Executor:"), 7, 0)
        bg_layout.addWidget(self.cmb_action_executor, 7, 1)
        bg_layout.addWidget(self.chk_action_verify_after, 8, 0)
        bg_layout.addWidget(self.chk_action_fail_closed, 8, 1)
        bg_layout.addWidget(QLabel("Action timeout (ms):"), 9, 0)
        bg_layout.addWidget(self.spin_action_timeout_ms, 9, 1)
        bg_layout.addWidget(QLabel("Max action retry:"), 10, 0)
        bg_layout.addWidget(self.spin_action_max_retry, 10, 1)

        container_layout.addWidget(browser_group)

        # 1b. Resource Blocking
        resource_group = QGroupBox("Resource Blocking")
        res_layout = QGridLayout(resource_group)
        res_layout.setSpacing(6)
        res_layout.setContentsMargins(8, 12, 8, 8)
        self.chk_resource_blocking_enabled = QCheckBox("Bật chặn tài nguyên nặng")
        self.chk_block_images = QCheckBox("Chặn ảnh")
        self.chk_block_media = QCheckBox("Chặn media")
        self.chk_block_fonts = QCheckBox("Chặn font")
        self.chk_block_stylesheets = QCheckBox("Chặn CSS")
        self.chk_block_stylesheets.setToolTip("Có thể làm hỏng layout, mặc định nên tắt.")
        res_layout.addWidget(self.chk_resource_blocking_enabled, 0, 0, 1, 2)
        res_layout.addWidget(self.chk_block_images, 1, 0)
        res_layout.addWidget(self.chk_block_media, 1, 1)
        res_layout.addWidget(self.chk_block_fonts, 2, 0)
        res_layout.addWidget(self.chk_block_stylesheets, 2, 1)
        container_layout.addWidget(resource_group)

        # 2. Account Config TTC
        account_group = QGroupBox("Tài Khoản TTC")
        ag_layout = QGridLayout(account_group)
        ag_layout.setSpacing(6)
        ag_layout.setContentsMargins(8, 12, 8, 8)

        self.txt_token = QLineEdit()
        self.txt_token.setEchoMode(QLineEdit.Password)
        self.txt_token.setPlaceholderText("TTC Token")
        self.btn_show_token = QPushButton("Hiện")
        self.btn_show_token.setMaximumWidth(50)
        self.btn_show_token.clicked.connect(self.toggle_token_visibility)

        self.txt_ttc_uid = QLineEdit()
        self.txt_ttc_uid.setPlaceholderText("UID Facebook")

        ag_layout.addWidget(QLabel("TTC Token:"), 0, 0)
        ag_layout.addWidget(self.txt_token, 0, 1)
        ag_layout.addWidget(self.btn_show_token, 0, 2)
        ag_layout.addWidget(QLabel("TTC UID (Facebook UID):"), 1, 0)
        ag_layout.addWidget(self.txt_ttc_uid, 1, 1, 1, 2)
        container_layout.addWidget(account_group)

        # 3. Job Type Selection — Checkbox nhiều lựa chọn
        job_group = QGroupBox("Loại Nhiệm Vụ TTC")
        jg_layout = QGridLayout(job_group)
        jg_layout.setSpacing(6)
        jg_layout.setContentsMargins(8, 12, 8, 8)

        self._job_type_checkboxes = {}
        for i, jt in enumerate(ALL_JOB_TYPES):
            chk = QCheckBox(TTC_JOB_TYPE_LABELS.get(jt, jt))
            chk.setChecked(True)
            self._job_type_checkboxes[jt] = chk
            jg_layout.addWidget(chk, i // 2, i % 2)

        self.cmb_reaction_filter = QComboBox()
        self.cmb_reaction_filter.addItems(["all", "LIKE", "LOVE", "CARE", "HAHA", "WOW", "SAD", "ANGRY"])

        self.spin_max_jobs = QSpinBox()
        self.spin_max_jobs.setRange(0, 100000)

        row = (len(ALL_JOB_TYPES) + 1) // 2
        jg_layout.addWidget(QLabel("Lọc Reaction:"), row, 0)
        jg_layout.addWidget(self.cmb_reaction_filter, row, 1)
        jg_layout.addWidget(QLabel("Giới hạn Job (0=không giới hạn):"), row + 1, 0)
        jg_layout.addWidget(self.spin_max_jobs, row + 1, 1)
        container_layout.addWidget(job_group)

        # 4. Duplicate check
        dup_group = QGroupBox("Kiểm Tra Trùng Lặp")
        dup_layout = QGridLayout(dup_group)
        dup_layout.setSpacing(6)
        dup_layout.setContentsMargins(8, 12, 8, 8)

        self.chk_duplicate_check = QCheckBox("Bỏ qua job đã tương tác (chống trùng)")
        self.cmb_duplicate_mode = QComboBox()
        self.cmb_duplicate_mode.addItems(["same_action", "post_any_action"])

        dup_layout.addWidget(self.chk_duplicate_check, 0, 0, 1, 2)
        dup_layout.addWidget(QLabel("Mode trùng:"), 1, 0)
        dup_layout.addWidget(self.cmb_duplicate_mode, 1, 1)
        container_layout.addWidget(dup_group)

        # 5. Reaction Delay
        reaction_delay_group = QGroupBox("⚡ Delay Reaction/Like Post (giây)")
        rd_layout = QGridLayout(reaction_delay_group)
        rd_layout.setSpacing(6)
        rd_layout.setContentsMargins(8, 12, 8, 8)

        self.spin_reaction_min_delay = QSpinBox()
        self.spin_reaction_min_delay.setRange(0, 3600)
        self.spin_reaction_max_delay = QSpinBox()
        self.spin_reaction_max_delay.setRange(0, 3600)
        self.spin_reaction_pre_claim_min_delay = QSpinBox()
        self.spin_reaction_pre_claim_min_delay.setRange(0, 3600)
        self.spin_reaction_pre_claim_max_delay = QSpinBox()
        self.spin_reaction_pre_claim_max_delay.setRange(0, 3600)

        rd_layout.addWidget(QLabel("Min Delay:"), 0, 0)
        rd_layout.addWidget(self.spin_reaction_min_delay, 0, 1)
        rd_layout.addWidget(QLabel("Max Delay:"), 1, 0)
        rd_layout.addWidget(self.spin_reaction_max_delay, 1, 1)
        rd_layout.addWidget(QLabel("Chờ tối thiểu trước nhận xu Reaction:"), 2, 0)
        rd_layout.addWidget(self.spin_reaction_pre_claim_min_delay, 2, 1)
        rd_layout.addWidget(QLabel("Chờ tối đa trước nhận xu Reaction:"), 3, 0)
        rd_layout.addWidget(self.spin_reaction_pre_claim_max_delay, 3, 1)
        container_layout.addWidget(reaction_delay_group)

        # 6. Comment Delay
        comment_delay_group = QGroupBox("💬 Delay Comment (giây)")
        cd_layout = QGridLayout(comment_delay_group)
        cd_layout.setSpacing(6)
        cd_layout.setContentsMargins(8, 12, 8, 8)

        self.spin_comment_min_delay = QSpinBox()
        self.spin_comment_min_delay.setRange(0, 3600)
        self.spin_comment_max_delay = QSpinBox()
        self.spin_comment_max_delay.setRange(0, 3600)

        cd_layout.addWidget(QLabel("Min Delay:"), 0, 0)
        cd_layout.addWidget(self.spin_comment_min_delay, 0, 1)
        cd_layout.addWidget(QLabel("Max Delay:"), 1, 0)
        cd_layout.addWidget(self.spin_comment_max_delay, 1, 1)
        container_layout.addWidget(comment_delay_group)

        # 7. Follow / Like Page Delay
        other_delay_group = QGroupBox("👤 Delay Follow / Like Page (giây)")
        od_layout = QGridLayout(other_delay_group)
        od_layout.setSpacing(6)
        od_layout.setContentsMargins(8, 12, 8, 8)

        self.spin_follow_min_delay = QSpinBox()
        self.spin_follow_min_delay.setRange(0, 3600)
        self.spin_follow_max_delay = QSpinBox()
        self.spin_follow_max_delay.setRange(0, 3600)
        self.spin_page_like_min_delay = QSpinBox()
        self.spin_page_like_min_delay.setRange(0, 3600)
        self.spin_page_like_max_delay = QSpinBox()
        self.spin_page_like_max_delay.setRange(0, 3600)

        od_layout.addWidget(QLabel("Follow Min:"), 0, 0)
        od_layout.addWidget(self.spin_follow_min_delay, 0, 1)
        od_layout.addWidget(QLabel("Follow Max:"), 1, 0)
        od_layout.addWidget(self.spin_follow_max_delay, 1, 1)
        od_layout.addWidget(QLabel("Like Page Min:"), 2, 0)
        od_layout.addWidget(self.spin_page_like_min_delay, 2, 1)
        od_layout.addWidget(QLabel("Like Page Max:"), 3, 0)
        od_layout.addWidget(self.spin_page_like_max_delay, 3, 1)
        container_layout.addWidget(other_delay_group)

        # 8. Other timing
        other_timing_group = QGroupBox("⏱ Cài Đặt Thời Gian Khác")
        ot_layout = QGridLayout(other_timing_group)
        ot_layout.setSpacing(6)
        ot_layout.setContentsMargins(8, 12, 8, 8)

        self.spin_wait_no_job = QSpinBox()
        self.spin_wait_no_job.setRange(1, 3600)
        self.spin_api_retry = QSpinBox()
        self.spin_api_retry.setRange(1, 3600)
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(1, 3600)
        self.spin_block_cooldown = QSpinBox()
        self.spin_block_cooldown.setRange(1, 1440)

        ot_layout.addWidget(QLabel("Khi hết job chờ (s):"), 0, 0)
        ot_layout.addWidget(self.spin_wait_no_job, 0, 1)
        ot_layout.addWidget(QLabel("Lỗi API thử lại (s):"), 1, 0)
        ot_layout.addWidget(self.spin_api_retry, 1, 1)
        ot_layout.addWidget(QLabel("Timeout Browser (s):"), 2, 0)
        ot_layout.addWidget(self.spin_timeout, 2, 1)
        ot_layout.addWidget(QLabel("Block Cooldown (phút):"), 3, 0)
        ot_layout.addWidget(self.spin_block_cooldown, 3, 1)
        container_layout.addWidget(other_timing_group)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def toggle_token_visibility(self):
        if self.txt_token.echoMode() == QLineEdit.Password:
            self.txt_token.setEchoMode(QLineEdit.Normal)
            self.btn_show_token.setText("Ẩn")
        else:
            self.txt_token.setEchoMode(QLineEdit.Password)
            self.btn_show_token.setText("Hiện")

    def _on_use_gemlogin_toggled(self, checked: bool):
        """Khi dùng GemLogin, headless luôn phải True — lock checkbox."""
        if checked:
            self.chk_headless.setChecked(True)
            self.chk_headless.setEnabled(False)
        else:
            self.chk_headless.setEnabled(True)

    def load_config(self, cfg, worker_id=None):
        if not cfg:
            return
        self.loaded_worker_id = str(worker_id or cfg.get("worker_id") or "")
        self.chk_enabled.setChecked(bool(cfg.get("enabled", True)))
        self.chk_use_gemlogin.setChecked(bool(cfg.get("use_gemlogin", True)))
        use_gemlogin = bool(cfg.get("use_gemlogin", True))
        # GemLogin bắt buộc headless=True
        headless_val = True if use_gemlogin else bool(cfg.get("headless", False))
        self.chk_headless.setChecked(headless_val)
        self.chk_auto_close.setChecked(bool(cfg.get("auto_close_profile", True)))
        self.chk_use_cookie.setChecked(bool(cfg.get("use_cookie", False)))

        self.cmb_mode.setCurrentText(str(cfg.get("mode", "gemlogin")))
        self.txt_gemlogin_url.setText(str(cfg.get("gemlogin_url", "http://localhost:1010")))
        self.txt_profile_id.setText(str(cfg.get("profile_id", "")))
        self.txt_cookie.setText(str(cfg.get("cookie", "")))

        action_cfg = cfg.get("action_executor") if isinstance(cfg.get("action_executor"), dict) else {}
        action_executor = str(action_cfg.get("name") or cfg.get("facebook_action_executor", "facebook_graphql_context"))
        idx = self.cmb_action_executor.findText(action_executor)
        self.cmb_action_executor.setCurrentIndex(idx if idx >= 0 else 0)
        self.chk_action_verify_after.setChecked(bool(action_cfg.get("verify_after_action", True)))
        self.chk_action_fail_closed.setChecked(bool(action_cfg.get("fail_closed", True)))
        # provider_enabled / provider_url không còn dùng, bỏ qua khi load
        self.spin_action_timeout_ms.setValue(int(action_cfg.get("timeout_ms", 15000)))
        self.spin_action_max_retry.setValue(int(action_cfg.get("max_action_retry", 0)))

        self.chk_resource_blocking_enabled.setChecked(bool(cfg.get("resource_blocking_enabled", True)))
        self.chk_block_images.setChecked(bool(cfg.get("block_images", True)))
        self.chk_block_media.setChecked(bool(cfg.get("block_media", True)))
        self.chk_block_fonts.setChecked(bool(cfg.get("block_fonts", True)))
        self.chk_block_stylesheets.setChecked(bool(cfg.get("block_stylesheets", False)))

        # TTC credentials — migration alias bumx_token -> ttc_token
        ttc_token = str(cfg.get("ttc_token") or cfg.get("bumx_token") or cfg.get("auth") or "")
        self.txt_token.setText(ttc_token)
        self.txt_ttc_uid.setText(str(cfg.get("ttc_uid") or ""))

        # Job types checkboxes
        enabled_types = cfg.get("enabled_job_types") or []
        if not enabled_types:
            enabled_types = list(ALL_JOB_TYPES)
        for jt, chk in self._job_type_checkboxes.items():
            chk.setChecked(jt in enabled_types)

        self.cmb_reaction_filter.setCurrentText(str(cfg.get("reaction_filter", "all")))
        self.spin_max_jobs.setValue(int(cfg.get("max_jobs", 0)))

        self.chk_duplicate_check.setChecked(bool(cfg.get("duplicate_check_enabled", True)))
        self.cmb_duplicate_mode.setCurrentText(str(cfg.get("duplicate_check_mode", "same_action")))

        self.spin_reaction_min_delay.setValue(int(cfg.get("reaction_min_delay_after_job", 30)))
        self.spin_reaction_max_delay.setValue(int(cfg.get("reaction_max_delay_after_job", 45)))
        self.spin_reaction_pre_claim_min_delay.setValue(int(cfg.get("reaction_pre_claim_min_delay", 3)))
        self.spin_reaction_pre_claim_max_delay.setValue(int(cfg.get("reaction_pre_claim_max_delay", 3)))
        self.spin_comment_min_delay.setValue(int(cfg.get("comment_min_delay_after_job", 60)))
        self.spin_comment_max_delay.setValue(int(cfg.get("comment_max_delay_after_job", 90)))
        self.spin_follow_min_delay.setValue(int(cfg.get("follow_min_delay_after_job", 30)))
        self.spin_follow_max_delay.setValue(int(cfg.get("follow_max_delay_after_job", 45)))
        self.spin_page_like_min_delay.setValue(int(cfg.get("page_like_min_delay_after_job", 30)))
        self.spin_page_like_max_delay.setValue(int(cfg.get("page_like_max_delay_after_job", 45)))

        self.spin_wait_no_job.setValue(int(cfg.get("wait_no_job_delay", 30)))
        self.spin_api_retry.setValue(int(cfg.get("api_error_retry_delay", 20)))
        self.spin_timeout.setValue(int(cfg.get("timeout", 60)))
        self.spin_block_cooldown.setValue(int(cfg.get("interaction_block_cooldown_minutes", 60)))

    def save_config(self, cfg):
        target_worker_id = str(cfg.get("worker_id") or "")
        if self.loaded_worker_id and target_worker_id and self.loaded_worker_id != target_worker_id:
            return cfg

        # Swap nếu min > max
        def _swap(mn, mx, s_mn, s_mx):
            v_mn = s_mn.value()
            v_mx = s_mx.value()
            if v_mn > v_mx:
                v_mn, v_mx = v_mx, v_mn
                s_mn.setValue(v_mn)
                s_mx.setValue(v_mx)
            return v_mn, v_mx

        r_min, r_max = _swap(None, None, self.spin_reaction_min_delay, self.spin_reaction_max_delay)
        pc_min, pc_max = _swap(None, None, self.spin_reaction_pre_claim_min_delay, self.spin_reaction_pre_claim_max_delay)
        c_min, c_max = _swap(None, None, self.spin_comment_min_delay, self.spin_comment_max_delay)
        f_min, f_max = _swap(None, None, self.spin_follow_min_delay, self.spin_follow_max_delay)
        p_min, p_max = _swap(None, None, self.spin_page_like_min_delay, self.spin_page_like_max_delay)

        cfg["enabled"] = self.chk_enabled.isChecked()
        cfg["use_gemlogin"] = self.chk_use_gemlogin.isChecked()
        # Nếu dùng GemLogin thì luôn ép headless=True, không cho save headless=False
        cfg["headless"] = True if self.chk_use_gemlogin.isChecked() else self.chk_headless.isChecked()
        cfg["auto_close_profile"] = self.chk_auto_close.isChecked()
        cfg["use_cookie"] = self.chk_use_cookie.isChecked()

        cfg["mode"] = self.cmb_mode.currentText()
        cfg["gemlogin_url"] = self.txt_gemlogin_url.text().strip()
        cfg["profile_id"] = self.txt_profile_id.text().strip()
        cfg["gemlogin_profile_id"] = self.txt_profile_id.text().strip()
        cfg["cookie"] = self.txt_cookie.text().strip() if self.chk_use_cookie.isChecked() else ""

        executor_name = self.cmb_action_executor.currentText()
        cfg["facebook_action_executor"] = executor_name
        cfg["action_executor"] = {
            "name": executor_name,
            "verify_after_action": self.chk_action_verify_after.isChecked(),
            "fail_closed": self.chk_action_fail_closed.isChecked(),
            "timeout_ms": self.spin_action_timeout_ms.value(),
            "max_action_retry": self.spin_action_max_retry.value(),
            # provider_enabled và provider_url không còn dùng — không lưu
        }
        cfg["resource_blocking_enabled"] = self.chk_resource_blocking_enabled.isChecked()
        cfg["block_images"] = self.chk_block_images.isChecked()
        cfg["block_media"] = self.chk_block_media.isChecked()
        cfg["block_fonts"] = self.chk_block_fonts.isChecked()
        cfg["block_stylesheets"] = self.chk_block_stylesheets.isChecked()
        cfg.pop("facebook_post_layout", None)

        # TTC credentials — lưu dưới key TTC, xóa key Bumx cũ
        cfg["ttc_token"] = self.txt_token.text().strip()
        cfg["ttc_uid"] = self.txt_ttc_uid.text().strip()
        cfg.pop("bumx_token", None)
        cfg.pop("auth", None)

        # Job types
        enabled_types = [jt for jt, chk in self._job_type_checkboxes.items() if chk.isChecked()]
        cfg["enabled_job_types"] = enabled_types

        cfg["reaction_filter"] = self.cmb_reaction_filter.currentText()
        cfg["max_jobs"] = self.spin_max_jobs.value()

        cfg["duplicate_check_enabled"] = self.chk_duplicate_check.isChecked()
        cfg["duplicate_check_mode"] = self.cmb_duplicate_mode.currentText()
        cfg["duplicate_history_file"] = str(cfg.get("duplicate_history_file") or "interaction_history.json")
        cfg["duplicate_history_max_records"] = int(cfg.get("duplicate_history_max_records") or 3000)

        cfg["reaction_min_delay_after_job"] = r_min
        cfg["reaction_max_delay_after_job"] = r_max
        cfg["reaction_pre_claim_min_delay"] = pc_min
        cfg["reaction_pre_claim_max_delay"] = pc_max
        cfg["comment_min_delay_after_job"] = c_min
        cfg["comment_max_delay_after_job"] = c_max
        cfg["follow_min_delay_after_job"] = f_min
        cfg["follow_max_delay_after_job"] = f_max
        cfg["page_like_min_delay_after_job"] = p_min
        cfg["page_like_max_delay_after_job"] = p_max

        cfg["wait_no_job_delay"] = self.spin_wait_no_job.value()
        cfg["api_error_retry_delay"] = self.spin_api_retry.value()
        cfg["timeout"] = self.spin_timeout.value()
        cfg["interaction_block_cooldown_minutes"] = self.spin_block_cooldown.value()
        return cfg
