# -*- coding: utf-8 -*-
"""
ttc_runtime.py â€” Interface run_worker_config cho gui_worker.

gui_worker.py import:
    from ttc_runtime import run_worker_config

KhÃ´ng phá»¥ thuá»™c vÃ o api_bumx.
"""

import datetime
import random
import time

from ttc_api import TTCClient, TTCAuthError, TTCNoJobAvailable, TTCResponseError
from ttc_dispatcher import TTCDispatcher
from ttc_job_types import (
    ALL_JOB_TYPES, ACTION_GROUP_MAP, get_action_group, normalize_delay_range,
)
from job_queue import JobQueue
from chrome_auto import AUTO_CHROME
from facebook_guard import (
    InteractionBlockedError,
    detect_interaction_block,
    format_interaction_block_message,
)
from interaction_history import InteractionHistory, normalize_object_id
from facebook_action_result import FacebookActionResult, is_action_claimable
from action_executors import ActionContext, get_action_executor
from resource_policy import ResourcePolicy
from facebook_target_state import (
    DEAD_TARGET_REASONS,
    TargetCheckResult,
    check_facebook_target_live_result,
)


# =====================================================================
# Config normalize
# =====================================================================

DEFAULT_TTC_CONFIG = {
    "mode": "gemlogin",
    "use_gemlogin": True,
    "ttc_token": "",
    "ttc_uid": "",
    "profile_id": "",
    "gemlogin_url": "http://localhost:1010",
    "enabled_job_types": ALL_JOB_TYPES,
    "reaction_filter": "all",
    "max_jobs": 0,
    "reaction_min_delay_after_job": 30,
    "reaction_max_delay_after_job": 45,
    "reaction_pre_claim_min_delay": 3,
    "reaction_pre_claim_max_delay": 3,
    "comment_min_delay_after_job": 60,
    "comment_max_delay_after_job": 90,
    "follow_min_delay_after_job": 30,
    "follow_max_delay_after_job": 45,
    "page_like_min_delay_after_job": 30,
    "page_like_max_delay_after_job": 45,
    "wait_no_job_delay": 30,
    "api_error_retry_delay": 20,
    "timeout": 60,
    "interaction_block_cooldown_minutes": 60,
    "headless": True,   # GemLogin cần headless=True để sử dụng browser-context fetch
    "auto_close_profile": True,
    "use_cookie": False,
    "cookie": "",
    "duplicate_check_enabled": True,
    "duplicate_check_mode": "same_action",
    "duplicate_history_file": "interaction_history.json",
    "duplicate_history_max_records": 3000,
    "gemlogin_profile_id": "",
    "min_queue_size": 1,
    "max_queue_size": 3,
    "max_browser_restarts": 3,
    "browser_heartbeat_interval": 30,
    "facebook_action_executor": "facebook_graphql_context",
    "action_executor": {
        "name": "facebook_graphql_context",
        "verify_after_action": True,
        "fail_closed": True,
        "timeout_ms": 15000,
        "max_action_retry": 0,
    },
    "resource_blocking_enabled": True,
    "block_images": True,
    "block_media": True,
    "block_fonts": True,
    "block_stylesheets": False,
}


def normalize_ttc_config(raw: dict) -> dict:
    cfg = dict(DEFAULT_TTC_CONFIG)
    cfg.update(raw or {})

    # Migration alias: bumx_token -> ttc_token
    if not cfg.get("ttc_token") and cfg.get("bumx_token"):
        cfg["ttc_token"] = cfg["bumx_token"]
    if not cfg.get("ttc_token") and cfg.get("auth"):
        cfg["ttc_token"] = cfg["auth"]

    # profile_id alias
    if not cfg.get("profile_id") and cfg.get("gemlogin_profile_id"):
        cfg["profile_id"] = cfg["gemlogin_profile_id"]
    if cfg.get("profile_id"):
        cfg["gemlogin_profile_id"] = cfg["profile_id"]

    # mode + ép headless nếu dùng GemLogin
    if cfg.get("use_gemlogin"):
        cfg["mode"] = "gemlogin"
        cfg["headless"] = True  # GemLogin bắt buộc headless=True cho browser-context fetch
    else:
        cfg["mode"] = cfg.get("mode", "gemlogin")

    # enabled_job_types
    jt = cfg.get("enabled_job_types") or []
    cfg["enabled_job_types"] = [t for t in jt if t in ALL_JOB_TYPES] or list(ALL_JOB_TYPES)

    # delays
    for prefix in ("reaction", "comment", "follow", "page_like"):
        mn_key = f"{prefix}_min_delay_after_job"
        mx_key = f"{prefix}_max_delay_after_job"
        mn, mx = normalize_delay_range(cfg.get(mn_key, 30), cfg.get(mx_key, 45))
        cfg[mn_key] = mn
        cfg[mx_key] = mx

    mn, mx = normalize_delay_range(
        cfg.get("reaction_pre_claim_min_delay", 3),
        cfg.get("reaction_pre_claim_max_delay", 3),
    )
    cfg["reaction_pre_claim_min_delay"] = mn
    cfg["reaction_pre_claim_max_delay"] = mx

    cfg["timeout"] = max(10, int(cfg.get("timeout") or 60))
    cfg["max_jobs"] = max(0, int(cfg.get("max_jobs") or 0))
    cfg["interaction_block_cooldown_minutes"] = max(1, int(cfg.get("interaction_block_cooldown_minutes") or 60))
    # Đồng bộ hóa với ttc_config.py
    legacy_name = str(cfg.get("facebook_action_executor") or "")
    _upgrade_map = {"unsupported": "facebook_graphql_context", "": "facebook_graphql_context"}
    legacy_name = _upgrade_map.get(legacy_name, legacy_name)

    action_executor = cfg.get("action_executor")
    if not isinstance(action_executor, dict):
        action_executor = {}

    existing_name = str(action_executor.get("name") or legacy_name)
    existing_name = _upgrade_map.get(existing_name, existing_name)

    action_executor["name"] = existing_name
    action_executor.setdefault("verify_after_action", True)
    action_executor.setdefault("fail_closed", True)
    action_executor.setdefault("timeout_ms", 15000)
    action_executor.setdefault("max_action_retry", 0)
    action_executor.pop("provider_enabled", None)
    action_executor.pop("provider_url", None)

    cfg["action_executor"] = action_executor
    cfg["facebook_action_executor"] = str(action_executor.get("name") or "facebook_graphql_context")
    return cfg


def _pick_delay(cfg: dict, action_group: str) -> int:
    prefix_map = {
        "reaction": "reaction",
        "comment": "comment",
        "follow": "follow",
        "page_like": "page_like",
    }
    prefix = prefix_map.get(action_group, "reaction")
    mn = int(cfg.get(f"{prefix}_min_delay_after_job", 30))
    mx = int(cfg.get(f"{prefix}_max_delay_after_job", 45))
    if mn > mx:
        mn, mx = mx, mn
    return random.randint(mn, mx)


def _pick_pre_claim_delay(cfg: dict) -> int:
    mn = int(cfg.get("reaction_pre_claim_min_delay", 3))
    mx = int(cfg.get("reaction_pre_claim_max_delay", 3))
    if mn > mx:
        mn, mx = mx, mn
    return random.randint(mn, mx)


def _should_apply_reaction_pre_claim_delay(action_group: str, action_result: FacebookActionResult) -> bool:
    return str(action_group or "") == "reaction" and is_action_claimable(action_result)


def _display_idpost(job_raw_data: dict) -> str:
    idpost = str((job_raw_data or {}).get("idpost") or "").strip()
    return idpost or "idpost=unknown"


def _format_success_log(job_type: str, job_raw_data: dict, earned: int, balance) -> str:
    return f"✅ {job_type} | {_display_idpost(job_raw_data)} | +{int(earned or 0)} xu | Số dư: {balance} xu"


TARGET_REASON_MESSAGES = {
    "POST_DELETED_OR_UNAVAILABLE": "Bài viết đã bị xóa hoặc không còn khả dụng.",
    "REEL_DELETED_OR_UNAVAILABLE": "Reel đã bị xóa hoặc không còn khả dụng.",
    "PRIVACY_OR_PERMISSION_DENIED": "Profile Facebook không có quyền xem nội dung này.",
    "LOGIN_REQUIRED": "Profile Facebook đã mất phiên đăng nhập.",
    "CHECKPOINT_OR_LOCKED": "Tài khoản Facebook đang checkpoint hoặc bị khóa.",
    "NAVIGATION_TIMEOUT": "Mở target quá thời gian chờ.",
    "NAVIGATION_CONFLICT": "Navigation đang bị xung đột, sẽ retry current job.",
    "NAVIGATION_ABORTED": "Navigation bị hủy giữa chừng.",
    "LIVE_CHECK_TIMEOUT": "Target đã mở nhưng chưa render đủ tín hiệu.",
    "ACTION_CONTROL_NOT_FOUND": "Target vẫn hoạt động nhưng không tìm thấy nút Like/Reaction phù hợp.",
    "UNSUPPORTED_REEL_LAYOUT": "Reel đang dùng layout chưa được hỗ trợ.",
    "REACTION_PICKER_NOT_FOUND": "Đã tìm thấy nút Like Reel nhưng không mở được bảng cảm xúc.",
    "REACTION_OPTION_NOT_FOUND": "Không tìm thấy cảm xúc trong bảng cảm xúc Reel.",
    "REACTION_TYPE_NOT_VERIFIED": "Đã chọn cảm xúc nhưng chưa xác minh được đúng loại.",
    "FACEBOOK_INTERACTION_BLOCKED": "Facebook đang chặn thao tác Reaction.",
    "STOP_REQUESTED": "Worker đã nhận lệnh dừng.",
    "BROWSER_OR_PAGE_CLOSED": "Trang hoặc trình duyệt đã đóng.",
    "ACTION_EXECUTOR_UNSUPPORTED": "Chưa cấu hình executor thực hiện action.",
    "DRY_RUN_NOT_CLAIMABLE": "Dry-run chỉ mô phỏng, không được nhận xu.",
    "BROWSER_CONTEXT_UNAVAILABLE": "Không có page context Playwright hợp lệ.",
    "PAGE_CLOSED": "Page Playwright đã đóng.",
    "PAGE_CONTEXT_ACTION_NOT_CONFIGURED": "Browser-context executor chưa có provider action hợp lệ.",
    "PAGE_CONTEXT_ACTION_FAILED": "Action trong browser context thất bại.",
    "ACTION_NOT_VERIFIED": "Thao tác chưa được xác minh.",
    "ACTION_VERIFIED": "Thao tác đã được xác minh.",
    "CLAIM_GUARD_BLOCKED_UNVERIFIED_ACTION": "Chặn nhận xu vì action chưa verified.",
}


def _target_reason_message(reason: str) -> str:
    return TARGET_REASON_MESSAGES.get(str(reason or ""), f"Target lá»—i: {reason or 'UNKNOWN_TARGET_ERROR'}")


def _short_evidence(value: str, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _log_action_result(logger, worker_id: str, result: FacebookActionResult) -> None:
    target = str(getattr(result, "target_type", "") or "UNKNOWN")
    reaction = str(getattr(result, "requested_reaction", "") or "")
    evidence = _short_evidence(getattr(result, "evidence", "") or "")
    suffix = f" | evidence={evidence}" if evidence else ""
    logger.log(
        worker_id,
        (
            f"[{target}] Action result: success={getattr(result, 'success', None)} "
            f"| verified={getattr(result, 'verified', None)} "
            f"| clicked={getattr(result, 'clicked', None)} "
            f"| reaction={reaction} | reason={getattr(result, 'reason', '')}{suffix}"
        ),
        "info",
    )


def _claim_verified_job(ttc, job_raw_data: dict, action_result: FacebookActionResult):
    if not is_action_claimable(action_result):
        return {
            "success": False,
            "message": "CLAIM_GUARD_BLOCKED_UNVERIFIED_ACTION",
            "earned_coin": 0,
            "balance": None,
            "reason": "CLAIM_GUARD_BLOCKED_UNVERIFIED_ACTION",
            "retryable": False,
        }
    return ttc.claim_reward(job_raw_data)


CLAIM_RETRYABLE_REASONS = {
    "NOT_OBSERVED_YET",
    "HTTP_ERROR",
    "NETWORK_TIMEOUT",
    "RATE_LIMITED",
    "INVALID_RESPONSE",
}


def _should_retry_claim(claim_result: dict, attempt: int, max_attempts: int, stop_event) -> bool:
    if stop_event is not None and stop_event.is_set():
        return False
    if attempt >= max_attempts:
        return False
    reason = str((claim_result or {}).get("reason") or "")
    return bool((claim_result or {}).get("retryable")) and reason in CLAIM_RETRYABLE_REASONS


# =====================================================================
# Initial stats
# =====================================================================

def _initial_stats(worker_id: str, profile_id: str) -> dict:
    return {
        "worker_id": worker_id,
        "profile_id": profile_id,
        "status": "running",
        "health_status": "healthy",
        "queue_size": 0,
        "current_job_id": "",
        "current_job_buff_id": "",
        "current_job_type": "",
        "total_picked": 0,
        "total_done": 0,
        "total_failed": 0,
        "total_skipped": 0,
        "total_no_job_count": 0,
        "total_like_post_done": 0,
        "total_reaction_done": 0,
        "total_comment_done": 0,
        "total_follow_done": 0,
        "total_page_like_done": 0,
        "total_coin": 0,
        "account_balance": 0,
        "elapsed_time": "00:00:00",
        "restart_count": 0,
        "blocked_display": "None",
        "interaction_blocked": {},
        "last_message": "",
        "last_error": "",
        "last_recovery_reason": "",
        "consecutive_api_errors": 0,
        "started_at": datetime.datetime.now(),
        "total_api_error_count": 0,
        "total_pending_mission_count": 0,
        "total_reported": 0,
        "navigation_conflict_streak": 0,
        "navigation_retry_count": 0,
        "navigation_circuit_open": False,
    }


# =====================================================================
# Browser heartbeat & recovery
# =====================================================================

def _browser_alive(browser_obj) -> bool:
    try:
        if browser_obj is None:
            return False
        _ = browser_obj.page.url
        return True
    except Exception:
        return False


def _try_recover_browser(browser_obj, cfg: dict, logger, worker_id: str, stats: dict) -> bool:
    """Thử khôi phục browser. Trả về True nếu thành công."""
    logger.log(worker_id, "Browser không phản hồi, đang khởi động lại...", "warning")
    try:
        browser_obj.close()
    except Exception:
        pass
    try:
        new_browser = _start_browser(cfg)
        # Gán lại các attribute của browser_obj
        for attr in ("playwright", "browser", "context", "page", "_gemlogin_client"):
            setattr(browser_obj, attr, getattr(new_browser, attr, None))
        stats["restart_count"] = stats.get("restart_count", 0) + 1
        stats["health_status"] = "recovering"
        stats["last_recovery_reason"] = "Browser recovered after heartbeat failure"
        logger.log(worker_id, "Browser đã được khôi phục thành công.", "info")
        return True
    except Exception as e:
        stats["health_status"] = "failed"
        stats["last_error"] = f"Browser recovery tháº¥t báº¡i: {e}"
        logger.log(worker_id, f"Browser recovery tháº¥t báº¡i: {e}", "error")
        return False


def _start_browser(cfg: dict) -> AUTO_CHROME:
    browser = AUTO_CHROME(
        headless=bool(cfg.get("headless", False)),
        mode=cfg.get("mode", "gemlogin"),
        profile_id=str(cfg.get("profile_id") or ""),
        gemlogin_url=str(cfg.get("gemlogin_url") or "http://localhost:1010"),
        use_cookie=bool(cfg.get("use_cookie", False)),
        auto_close_profile=bool(cfg.get("auto_close_profile", True)),
        resource_policy=ResourcePolicy.from_config(cfg),
    )
    browser.setup_driver()
    cookie = str(cfg.get("cookie") or "")
    browser.chrome_login_cookie(cookie)
    return browser


# =====================================================================
# Live check target
# =====================================================================

def check_facebook_target_live(page, link: str, target_type: str, timeout_ms: int = 8000) -> bool:
    """Kiá»ƒm tra link Facebook cÃ²n hoáº¡t Ä‘á»™ng khÃ´ng.

    target_type: 'post' | 'profile' | 'page'
    Tráº£ vá» False náº¿u redirect login, checkpoint, unavailable.
    """
    try:
        url = page.url or ""
        if not url:
            return False

        # Kiá»ƒm tra redirect login / checkpoint
        bad_patterns = [
            "login", "checkpoint", "disabled", "suspended",
            "unavailable", "removed", "violat",
        ]
        url_lower = url.lower()
        for p in bad_patterns:
            if p in url_lower:
                return False

        if target_type == "post":
            # TÃ­n hiá»‡u bÃ i viáº¿t: article, video, action row
            selectors = [
                "article",
                "[data-pagelet='FeedUnit']",
                "[role='article']",
                "div[data-ad-preview='message']",
            ]
            for sel in selectors:
                try:
                    if page.locator(sel).first.is_visible(timeout=timeout_ms // len(selectors)):
                        return True
                except Exception:
                    pass
            return False

        elif target_type == "profile":
            # TÃ­n hiá»‡u profile header
            selectors = [
                "[data-pagelet='ProfileTilesFeed_0']",
                "h1",
                "[data-pagelet='ProfileAppSection_0']",
            ]
            for sel in selectors:
                try:
                    if page.locator(sel).first.is_visible(timeout=timeout_ms // len(selectors)):
                        return True
                except Exception:
                    pass
            return False

        elif target_type == "page":
            # TÃ­n hiá»‡u page header
            selectors = [
                "[data-pagelet='ProfileTilesFeed_0']",
                "h1",
                "[role='main']",
            ]
            for sel in selectors:
                try:
                    if page.locator(sel).first.is_visible(timeout=timeout_ms // len(selectors)):
                        return True
                except Exception:
                    pass
            return False

        return True  # fallback
    except Exception:
        return False


def check_facebook_target_live_state(page, link: str, target_type: str, timeout_ms: int = 8000) -> TargetCheckResult:
    try:
        return check_facebook_target_live_result(page, link, target_type, timeout_ms=timeout_ms)
    except Exception as exc:
        final_url = str(getattr(page, "url", "") or "")
        return TargetCheckResult(
            False,
            "UNKNOWN_TARGET_ERROR",
            target_type,
            link,
            final_url,
            evidence=str(exc),
            retryable=False,
        )


def _target_type_for_job(job: dict) -> str:
    action_group = job.get("action_group", "")
    if action_group == "follow":
        return "profile"
    if action_group == "page_like":
        return "page"
    return "post"


# =====================================================================
# Main runtime interface
# =====================================================================

def run_worker_config(worker_config: dict, worker_id, stop_event, logger):
    """Entry point Ä‘Æ°á»£c gui_worker gá»i.

    TÆ°Æ¡ng thÃ­ch 100% vá»›i BumxWorkerThread.run() hiá»‡n táº¡i:
        run_worker_config(self.config, self.worker_id, self.stop_event, self.logger)
    """
    worker_id = str(worker_id)
    cfg = normalize_ttc_config(worker_config)

    # Validate tá»‘i thiá»ƒu
    ttc_token = str(cfg.get("ttc_token") or "").strip()
    ttc_uid = str(cfg.get("ttc_uid") or "").strip()
    profile_id = str(cfg.get("profile_id") or "").strip()

    if not ttc_token:
        raise ValueError(f"[Worker #{worker_id}] Thiáº¿u ttc_token trong config.")
    if not ttc_uid:
        raise ValueError(f"[Worker #{worker_id}] Thiáº¿u ttc_uid trong config.")
    if cfg.get("mode") == "gemlogin" and not profile_id:
        raise ValueError(f"[Worker #{worker_id}] Mode GemLogin cáº§n profile_id.")

    stats = _initial_stats(worker_id, profile_id)

    def _emit():
        logger.update_stats(worker_id, stats)

    # -------- TTC Auth --------
    ttc = TTCClient(worker_id=worker_id, log_fn=lambda msg, lvl="api": logger.log(worker_id, msg, lvl))
    try:
        ttc.authenticate(ttc_token)
    except TTCAuthError as e:
        logger.log(worker_id, f"Đăng nhập TTC thất bại: {e}", "error")
        raise

    info = ttc.get_account_info()
    stats["account_balance"] = info.get("balance", 0)
    _emit()

    try:
        ttc.configure_facebook_uid(ttc_uid)
    except Exception as e:
        logger.log(worker_id, f"Đặt UID TTC thất bại: {e} - Dừng worker.", "error")
        raise

    # -------- Browser --------
    logger.log(worker_id, "Đang khởi động browser...", "browser")
    browser = _start_browser(cfg)
    logger.log(worker_id, "Browser sẵn sàng.", "browser")

    # -------- Queue + Dispatcher --------
    job_queue = JobQueue(worker_id=worker_id)
    dispatcher = TTCDispatcher(
        ttc_client=ttc,
        job_queue=job_queue,
        config=cfg,
        worker_id=worker_id,
        stop_event=stop_event,
        logger=logger,
    )
    dispatcher.stats = stats

    # -------- History --------
    history = InteractionHistory.get(
        path=cfg.get("duplicate_history_file", "interaction_history.json"),
        max_records=int(cfg.get("duplicate_history_max_records", 3000)),
    )
    dup_check = bool(cfg.get("duplicate_check_enabled", True))
    dup_mode = str(cfg.get("duplicate_check_mode", "same_action"))

    max_jobs = int(cfg.get("max_jobs") or 0)
    max_restarts = int(cfg.get("max_browser_restarts", 3))
    heartbeat_interval = int(cfg.get("browser_heartbeat_interval", 30))
    last_heartbeat = time.time()

    # -------- Worker loop --------
    try:
        while not stop_event.is_set():
            # Browser heartbeat
            now = time.time()
            if now - last_heartbeat >= heartbeat_interval:
                last_heartbeat = now
                if not _browser_alive(browser):
                    if stats["restart_count"] >= max_restarts:
                        logger.log(worker_id, f"Đã vượt giới hạn restart browser ({max_restarts}). Dừng worker.", "error")
                        stats["health_status"] = "failed"
                        stats["status"] = "error"
                        _emit()
                        break
                    if not _try_recover_browser(browser, cfg, logger, worker_id, stats):
                        break
                    _emit()

            # Dispatcher fetch
            if job_queue.size() < dispatcher.min_queue_size:
                try:
                    dispatcher.fetch_once()
                except TTCAuthError as e:
                    logger.log(worker_id, f"Auth TTC háº¿t háº¡n: {e}", "error")
                    stats["status"] = "error"
                    stats["health_status"] = "failed"
                    _emit()
                    break
                except Exception as e:
                    logger.log(worker_id, f"Lá»—i dispatcher: {e}", "error")
                    time.sleep(2)

            if stop_event.is_set():
                break

            # Láº¥y job tá»« queue
            job = job_queue.get_job(timeout=1)
            if job is None:
                continue

            if stop_event.is_set():
                job_queue.mark_failed(job, "stopped")
                break

            job_type = job.type or ""
            action_group = get_action_group(job_type)
            link = job.raw_data.get("link", "")
            object_id = job.raw_data.get("object_id", "")
            idpost = job.raw_data.get("idpost", "")

            stats["total_picked"] += 1
            stats["current_job_id"] = job.buff_id or ""
            stats["current_job_buff_id"] = job.buff_id or ""
            stats["current_job_type"] = job_type
            _emit()

            # Duplicate check
            if dup_check and profile_id and object_id:
                normalized_obj = normalize_object_id(object_id)
                if history.has_interacted(profile_id, normalized_obj, action_group, dup_mode):
                    logger.log(worker_id, f"Skip job trùng: {job_type} | {object_id}", "info")
                    job_queue.mark_skipped(job, "duplicate")
                    stats["total_skipped"] += 1
                    _emit()
                    continue

            # Live check
            target_type = _target_type_for_job(job.raw_data)
            navigation_ok = False
            nav_attempt = 0
            while not stop_event.is_set():
                nav_attempt += 1
                if not hasattr(browser, "navigate_to_target"):
                    logger.log(worker_id, "Browser không hỗ trợ navigate_to_target; dừng worker để tránh nested goto.", "error")
                    stats["status"] = "error"
                    stats["health_status"] = "failed"
                    job_queue.requeue_job(job, "navigation_owner_missing")
                    _emit()
                    stop_event.set()
                    break

                nav = browser.navigate_to_target(
                    link,
                    target_type=target_type,
                    stop_event=stop_event,
                    timeout_ms=cfg["timeout"] * 1000,
                    caller="ttc_runtime.live_check",
                    settle_ms=10000,
                )

                if nav.ok:
                    stats["navigation_conflict_streak"] = 0
                    stats["navigation_circuit_open"] = False
                    navigation_ok = True
                    break

                stats["last_error"] = nav.reason
                _emit()
                if nav.reason == "STOP_REQUESTED":
                    job_queue.mark_failed(job, "stopped")
                    break

                if nav.reason == "NAVIGATION_CONFLICT":
                    stats["navigation_conflict_streak"] = stats.get("navigation_conflict_streak", 0) + 1
                    stats["navigation_retry_count"] = stats.get("navigation_retry_count", 0) + 1
                    if stats["navigation_conflict_streak"] == 1:
                        logger.log(
                            worker_id,
                            f"Navigation conflict: retry current job once | nav_id={nav.navigation_id} | caller={nav.caller} | final={nav.final_url}",
                            "warning",
                        )
                    else:
                        logger.log(worker_id, f"Navigation conflict streak={stats['navigation_conflict_streak']}; mở circuit/recovery.", "warning")

                    if stats["navigation_conflict_streak"] >= 2:
                        stats["navigation_circuit_open"] = True
                        stats["health_status"] = "recovering"
                        _emit()
                        if stats["restart_count"] >= max_restarts or not _try_recover_browser(browser, cfg, logger, worker_id, stats):
                            stats["status"] = "error"
                            stats["health_status"] = "failed"
                            job_queue.requeue_job(job, "navigation_conflict_recovery_failed")
                            _emit()
                            stop_event.set()
                            break
                        stats["navigation_conflict_streak"] = 0
                        stats["navigation_circuit_open"] = False
                        _emit()

                    if nav_attempt <= 1 and job.retry_count <= 0:
                        if job_queue.requeue_job(job, "navigation_conflict_retry"):
                            dispatcher.countdown_sleep(random.randint(3, 5), "Navigation conflict backoff")
                        break

                    job_queue.mark_failed(job, "NAVIGATION_CONFLICT")
                    stats["total_failed"] += 1
                    _emit()
                    break

                if nav.retryable and nav_attempt <= 1:
                    logger.log(worker_id, f"Navigation retry: {nav.reason} | final={nav.final_url}", "warning")
                    dispatcher.countdown_sleep(random.randint(3, 5), f"Retry navigation {nav.reason}")
                    continue

                logger.log(worker_id, f"Navigation failed: {nav.reason} | error={nav.error}", "error")
                job_queue.mark_failed(job, nav.reason)
                stats["total_failed"] += 1
                _emit()
                break

            if not navigation_ok:
                if stop_event.is_set():
                    break
                continue

            target_state = check_facebook_target_live_state(browser.page, link, target_type)
            if not target_state.ok:
                msg = _target_reason_message(target_state.reason)
                logger.log(worker_id, f"{msg} | {link} | final={target_state.final_url}", "warning")
                if target_state.reason in DEAD_TARGET_REASONS:
                    job_queue.mark_dead_post(job, target_state.reason)
                else:
                    job_queue.mark_failed(job, target_state.reason)
                stats["total_failed"] += 1
                _emit()
                continue

            if stop_event.is_set():
                job_queue.mark_failed(job, "stopped")
                break

            # Thực hiện action qua executor sạch.
            # Baseline này không còn chứa logic click UI cũ. Executor mặc định là unsupported/dry_run,
            # vì vậy runtime sẽ không claim nếu action chưa được xác minh.
            fb_result = FacebookActionResult(False, False, False, action_group, target_state.target_type)
            try:
                if action_group == "comment" and not job.raw_data.get("comment_text", ""):
                    logger.log(worker_id, "Comment text rỗng, skip job.", "warning")
                    job_queue.mark_skipped(job, "empty_comment")
                    stats["total_skipped"] += 1
                    _emit()
                    continue
                action_executor_cfg = cfg.get("action_executor") if isinstance(cfg.get("action_executor"), dict) else {}
                executor_name = str(action_executor_cfg.get("name") or cfg.get("facebook_action_executor") or "unsupported")
                executor = get_action_executor(executor_name)
                action_context = ActionContext(
                    worker_id=worker_id,
                    profile_id=str(profile_id or cfg.get("profile_id") or cfg.get("gemlogin_profile_id") or ""),
                    uid=str(cfg.get("ttc_uid") or ""),
                    thread_name=str(cfg.get("name") or worker_id),
                    action_group=action_group,
                    target_type=target_state.target_type,
                    link=link,
                    config=cfg,
                    logger=logger,
                )
                fb_result = executor.execute(job=job, page=browser.page, context=action_context)
            except InteractionBlockedError as e:
                logger.log(worker_id, format_interaction_block_message({"action_type": e.action_type, "message": e.message}), "blocked")
                blocked = stats.setdefault("interaction_blocked", {})
                blocked[action_group] = time.time()
                stats["blocked_display"] = ", ".join(k.upper() for k, v in blocked.items() if v)
                job_queue.mark_skipped(job, "interaction_blocked")
                stats["total_skipped"] += 1
                _emit()
                continue
            except Exception as e:
                logger.log(worker_id, f"Lỗi action executor: {e}", "error")
                job_queue.mark_failed(job, f"executor_exception: {e}")
                stats["total_failed"] += 1
                _emit()
                continue

            # PhÃ¡t hiá»‡n block sau action
            if browser.page:
                block_info = detect_interaction_block(browser.page, action_group)
                if block_info.get("blocked"):
                    msg = format_interaction_block_message(block_info)
                    logger.log(worker_id, msg, "blocked")
                    blocked = stats.setdefault("interaction_blocked", {})
                    blocked[action_group] = time.time()
                    stats["blocked_display"] = ", ".join(k.upper() for k, v in blocked.items() if v)
                    job_queue.mark_skipped(job, "interaction_blocked_detected")
                    stats["total_skipped"] += 1
                    _emit()
                    continue

            _log_action_result(logger, worker_id, fb_result)

            if not is_action_claimable(fb_result):
                reason = fb_result.reason or browser.last_action_error or "ACTION_NOT_VERIFIED"
                msg = _target_reason_message(reason)
                evidence = f" | {fb_result.evidence}" if fb_result.evidence else ""
                logger.log(worker_id, f"{msg}{evidence}", "error")
                logger.log(worker_id, "[TTC] Không nhận xu vì thao tác Facebook chưa được xác minh.", "warning")
                job_queue.mark_failed(job, reason)
                stats["total_failed"] += 1
                _emit()
                continue

            if stop_event.is_set():
                job_queue.mark_failed(job, "stopped_before_claim")
                break

            if _should_apply_reaction_pre_claim_delay(action_group, fb_result):
                if fb_result.target_type == "REEL" and fb_result.requested_reaction:
                    logger.log(worker_id, f"[REEL] Đã xác minh cảm xúc {fb_result.active_reaction or fb_result.requested_reaction} đang hoạt động.", "info")
                pre_claim_delay = _pick_pre_claim_delay(cfg)
                logger.log(worker_id, f"[TTC] Chờ {pre_claim_delay} giây trước khi nhận xu.", "info")
                dispatcher.countdown_sleep(pre_claim_delay, "Chờ trước khi nhận xu Reaction")
                if stop_event.is_set():
                    job_queue.mark_failed(job, "STOP_REQUESTED")
                    stats["total_failed"] += 1
                    _emit()
                    break

            # Claim xu
            claim_result = {"success": False, "message": "", "earned_coin": 0, "balance": None, "reason": "CLAIM_STATE_UNKNOWN", "retryable": False}
            claim_attempts = 2
            for attempt in range(1, claim_attempts + 1):
                try:
                    claim_result = _claim_verified_job(ttc, job.raw_data, fb_result)
                    if claim_result.get("success"):
                        break
                    if not _should_retry_claim(claim_result, attempt, claim_attempts, stop_event):
                        break
                    wait_retry = 3
                    logger.log(
                        worker_id,
                        f"[TTC] Chưa xác nhận thao tác: {claim_result.get('message', '')}",
                        "warning",
                    )
                    logger.log(
                        worker_id,
                        f"[TTC] Chờ {wait_retry} giây trước khi thử nhận xu lại.",
                        "warning",
                    )
                    logger.log(worker_id, "[TTC] Không thao tác Facebook lần hai khi retry claim.", "warning")
                    dispatcher.countdown_sleep(wait_retry, "Retry claim TTC")
                except TTCAuthError as e:
                    logger.log(worker_id, f"Auth háº¿t háº¡n khi claim: {e}", "error")
                    stats["status"] = "error"
                    stats["health_status"] = "failed"
                    _emit()
                    raise
                except Exception as e:
                    logger.log(worker_id, f"Claim láº§n {attempt} lá»—i: {e}", "warning")
                    if attempt < claim_attempts:
                        dispatcher.countdown_sleep(3, "Retry claim TTC")
                        if stop_event.is_set():
                            break
                    else:
                        logger.log(worker_id, f"Claim_unknown: Facebook thành công nhưng TTC claim lỗi. Không cộng xu.", "warning")
                        stats["total_failed"] += 1
                        job_queue.mark_failed(job, "claim_failed")
                        _emit()

            if not claim_result.get("success"):
                reason = claim_result.get("reason", "")
                message = claim_result.get("message", "")
                evidence = claim_result.get("evidence", "")
                if reason == "UNKNOWN_RESPONSE":
                    logger.log(worker_id, f"TTC phản hồi chưa xác định: {evidence or message} | reason={reason}", "warning")
                else:
                    logger.log(worker_id, f"TTC chưa xác nhận job: {message} | reason={reason}", "warning")
                stats["total_failed"] += 1
                job_queue.mark_failed(job, reason or "claim_not_success")
                _emit()
                continue

            # Claim thÃ nh cÃ´ng
            earned = int(claim_result.get("earned_coin") or 0)
            balance = claim_result.get("balance")
            if balance is not None:
                stats["account_balance"] = balance
            else:
                stats["account_balance"] = stats.get("account_balance", 0) + earned

            stats["total_coin"] = stats.get("total_coin", 0) + earned
            stats["total_done"] += 1

            # Cáº­p nháº­t counter theo loáº¡i
            type_counter_map = {
                "reaction": "total_reaction_done",
                "comment": "total_comment_done",
                "follow": "total_follow_done",
                "page_like": "total_page_like_done",
            }
            counter_key = type_counter_map.get(action_group)
            if counter_key:
                stats[counter_key] = stats.get(counter_key, 0) + 1
            if job_type in ("ttc_like_post_vip_cheo", "ttc_like_post_vip_re"):
                stats["total_like_post_done"] = stats.get("total_like_post_done", 0) + 1

            job_queue.mark_done(job)

            # Ghi history
            if dup_check and profile_id and object_id:
                normalized_obj = normalize_object_id(object_id)
                reaction_type = job.raw_data.get("reaction_type") if action_group == "reaction" else None
                history.mark_interacted(profile_id, normalized_obj, action_group, reaction_type)

            logger.log(
                worker_id,
                _format_success_log(job_type, job.raw_data, earned, stats["account_balance"]),
                "success",
            )
            stats["current_job_id"] = ""
            stats["current_job_buff_id"] = ""
            stats["current_job_type"] = ""
            _emit()

            # Kiá»ƒm tra giá»›i háº¡n job
            if max_jobs > 0 and stats["total_done"] >= max_jobs:
                logger.log(worker_id, f"Đã đạt giới hạn {max_jobs} job. Dừng worker.", "info")
                break

            # Cooldown block check â€” reset náº¿u háº¿t thá»i gian
            cooldown_secs = cfg["interaction_block_cooldown_minutes"] * 60
            for group in list(stats.get("interaction_blocked", {}).keys()):
                blocked_at = stats["interaction_blocked"][group]
                if blocked_at and (time.time() - blocked_at) >= cooldown_secs:
                    del stats["interaction_blocked"][group]
                    logger.log(worker_id, f"Cooldown {group} đã hết. Tiếp tục loại này.", "info")

            stats["blocked_display"] = (
                ", ".join(k.upper() for k, v in stats.get("interaction_blocked", {}).items() if v)
                or "None"
            )

            # Delay sau job
            delay_secs = _pick_delay(cfg, action_group)
            dispatcher.countdown_sleep(delay_secs, f"Delay sau {action_group}")

    finally:
        # Cleanup
        stats["status"] = "stopped"
        stats["current_job_id"] = ""
        stats["current_job_buff_id"] = ""
        stats["current_job_type"] = ""
        _emit()
        try:
            browser.close()
        except Exception:
            pass
        try:
            ttc.close()
        except Exception:
            pass
        try:
            history.flush()
        except Exception:
            pass

