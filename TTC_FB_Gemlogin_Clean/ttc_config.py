# -*- coding: utf-8 -*-
"""
ttc_config.py — Load/Save multi-config cho TTC.

Thay thế load_multi_config và save_multi_config từ api_bumx.
Schema mới: dùng ttc_token, ttc_uid, enabled_job_types.
"""

import json
import os

from ttc_job_types import ALL_JOB_TYPES


def normalize_action_executor_config(config: dict) -> dict:
    """Chuẩn hóa action_executor config, tương thích config cũ không có action_executor key.

    Gọi function này trong quá trình load config để đảm bảo luôn có đủ field.
    provider_enabled và provider_url đã bị loại bỏ — không dùng external provider URL.
    Default executor là facebook_graphql_context (browser-context GraphQL).

    Args:
        config: dict worker config (chứa hoặc không chứa action_executor).

    Returns:
        config đã được normalize in-place và trả về.
    """
    legacy_name = str(config.get("facebook_action_executor") or "")

    # Migration: nâng cấp executor cũ không còn phù hợp lên facebook_graphql_context
    _upgrade_map = {"unsupported": "facebook_graphql_context", "": "facebook_graphql_context"}
    legacy_name = _upgrade_map.get(legacy_name, legacy_name)

    action_executor = config.get("action_executor")
    if not isinstance(action_executor, dict):
        action_executor = {}

    # Migrate tên executor cũ trong nested config
    existing_name = str(action_executor.get("name") or legacy_name)
    existing_name = _upgrade_map.get(existing_name, existing_name)

    action_executor["name"] = existing_name
    action_executor.setdefault("verify_after_action", True)
    action_executor.setdefault("fail_closed", True)
    action_executor.setdefault("timeout_ms", 15000)
    action_executor.setdefault("max_action_retry", 0)
    # provider_enabled và provider_url không còn dùng — ignore nếu có trong config cũ
    action_executor.pop("provider_enabled", None)
    action_executor.pop("provider_url", None)

    config["action_executor"] = action_executor
    config["facebook_action_executor"] = str(action_executor.get("name") or "facebook_graphql_context")

    return config

TTC_WORKER_VALID_KEYS = [
    "worker_id", "enabled", "name", "mode", "use_gemlogin",
    "profile_id", "gemlogin_profile_id",
    "ttc_token", "ttc_uid",
    "enabled_job_types", "reaction_filter", "max_jobs",
    "reaction_min_delay_after_job", "reaction_max_delay_after_job",
    "reaction_pre_claim_min_delay", "reaction_pre_claim_max_delay",
    "comment_min_delay_after_job", "comment_max_delay_after_job",
    "follow_min_delay_after_job", "follow_max_delay_after_job",
    "page_like_min_delay_after_job", "page_like_max_delay_after_job",
    "wait_no_job_delay", "api_error_retry_delay", "timeout",
    "interaction_block_cooldown_minutes",
    "headless", "auto_close_profile",
    "use_cookie", "cookie",
    "duplicate_check_enabled", "duplicate_check_mode",
    "duplicate_history_file", "duplicate_history_max_records",
    "gemlogin_url",
    "facebook_action_executor", "action_executor",
    "resource_blocking_enabled", "block_images", "block_media", "block_fonts", "block_stylesheets",
]


def load_multi_config(config_path="config.json") -> dict:
    """Đọc cấu hình đa luồng TTC."""
    if not os.path.exists(config_path):
        return {"global": {"worker_count": 1, "gemlogin_url": "http://localhost:1010"}, "workers": []}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "workers" not in data:
            data = {
                "global": {
                    "worker_count": int(data.get("worker_count") or 1),
                    "gemlogin_url": data.get("gemlogin_url") or "http://localhost:1010",
                },
                "workers": [],
            }
        # Migration: bumx_token -> ttc_token
        for w in data.get("workers", []):
            if not w.get("ttc_token") and w.get("bumx_token"):
                w["ttc_token"] = w["bumx_token"]
            if not w.get("ttc_token") and w.get("auth"):
                w["ttc_token"] = w["auth"]
            # Đảm bảo enabled_job_types hợp lệ
            if "reaction_pre_claim_min_delay" not in w:
                w["reaction_pre_claim_min_delay"] = 3
            if "reaction_pre_claim_max_delay" not in w:
                w["reaction_pre_claim_max_delay"] = 3
            if "facebook_action_executor" not in w:
                w["facebook_action_executor"] = "facebook_graphql_context"
            normalize_action_executor_config(w)
            if "resource_blocking_enabled" not in w:
                w["resource_blocking_enabled"] = True
            jt = w.get("enabled_job_types") or []
            w["enabled_job_types"] = [t for t in jt if t in ALL_JOB_TYPES] or list(ALL_JOB_TYPES)
        return data
    except Exception as e:
        print(f"[Config] Lỗi load config TTC: {e}")
        return {"global": {"worker_count": 1, "gemlogin_url": "http://localhost:1010"}, "workers": []}


def save_multi_config(config_data: dict, config_path="config.json") -> None:
    """Lưu cấu hình đa luồng TTC, schema sạch."""
    to_save = {
        "global": config_data.get("global", {"worker_count": 1, "gemlogin_url": "http://localhost:1010"}),
        "workers": [],
    }
    for w in config_data.get("workers", []):
        clean_w = {}
        for k in TTC_WORKER_VALID_KEYS:
            if k in w:
                clean_w[k] = w[k]
        normalize_action_executor_config(clean_w)

        # Không lưu cookie nếu use_cookie=false
        if not clean_w.get("use_cookie", False):
            clean_w.pop("cookie", None)
        # Xóa key Bumx cũ khỏi schema mới
        for old_key in ("bumx_token", "auth", "job_type", "bumx_api_lang",
                        "max_comment_unlock_jobs", "submit_comment_type",
                        "report_blocked_pending_missions", "report_duplicate_job",
                        "pending_loop_recovery_threshold", "auto_comment_unlock_reaction"):
            clean_w.pop(old_key, None)
        to_save["workers"].append(clean_w)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)
    print(f"[Config] Saved TTC config to {config_path}")
