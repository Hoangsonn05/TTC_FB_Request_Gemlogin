# -*- coding: utf-8 -*-
"""Lightweight Facebook interaction block detection.

This module only detects and reports Facebook limits. It does not retry,
restart, switch account/profile, or attempt to bypass the block.
"""


class InteractionBlockedError(Exception):
    """Raised when Facebook blocks or limits an interaction action."""

    def __init__(
        self,
        action_type="unknown",
        reason="facebook_interaction_limit",
        message="",
        buff_id=None,
        worker_id=None,
    ):
        self.action_type = str(action_type or "unknown")
        self.reason = str(reason or "facebook_interaction_limit")
        self.message = _shorten(message)
        self.fb_message = self.message
        self.buff_id = buff_id
        self.worker_id = worker_id
        super().__init__(
            f"[FacebookBlock] action={self.action_type} | {self.reason} | {self.message}"
        )


def format_interaction_block_message(block):
    action = str(block.get("action_type") or "unknown")
    fb_msg = str(block.get("message") or "").strip()
    if action == "reaction":
        prefix = "Facebook đang chặn tương tác REACTION"
    elif action in ("comment", "unlock_comment"):
        prefix = "Facebook đang chặn tương tác COMMENT"
    else:
        prefix = "Facebook đang chặn tương tác"
    if fb_msg:
        return f"{prefix}. Thông báo Facebook: {fb_msg}"
    return f"{prefix}. Không lấy được nội dung popup."


_BLOCK_PATTERNS = [
    ("Giờ bạn chưa dùng được tính năng này", None),
    ("Để bảo vệ cộng đồng khỏi spam", None),
    ("chúng tôi giới hạn tần suất", None),
    ("bạn có thể thử lại sau", None),
    ("hãy cho chúng tôi biết", None),
    ("You can’t use this feature right now", None),
    ("You can't use this feature right now", None),
    ("You’re temporarily blocked", None),
    ("You're temporarily blocked", None),
    ("We limit how often you can post", "reaction"),
    ("We limit how often you can comment", "comment"),
    ("Try again later", None),
    ("Action blocked", None),
    ("Temporarily blocked", None),
]

_DIALOG_SELECTORS = [
    "[role='dialog']",
    "[role='alertdialog']",
    "div[data-visualcompletion='dialog']",
    "div[aria-modal='true']",
]


def detect_interaction_block(page, action_type="unknown", timeout_ms=1200):
    """Return block metadata for the current page action.

    Intended call sites are immediately after reaction/comment actions, or when
    an action raises. The function keeps the check short and focused on visible
    Facebook dialogs/text instead of continuously scanning the DOM.
    """
    result = {
        "blocked": False,
        "action_type": action_type or "unknown",
        "message": "",
        "reason": "",
    }
    if page is None:
        return result

    try:
        direct = _find_visible_pattern(page, timeout_ms)
        if direct:
            matched, override_type = direct
            return _blocked_result(action_type, matched, override_type)

        dialog_text = _get_dialog_text(page, timeout_ms)
        if not dialog_text:
            return result

        matched, override_type = _match_block_text(dialog_text)
        if matched:
            result = _blocked_result(action_type, matched, override_type)
    except Exception:
        return {
            "blocked": False,
            "action_type": action_type or "unknown",
            "message": "",
            "reason": "",
        }
    return result


def _blocked_result(action_type, message, override_type=None):
    return {
        "blocked": True,
        "action_type": action_type or "unknown",
        "message": _shorten(message),
        "reason": "facebook_interaction_limit",
    }


def _find_visible_pattern(page, timeout_ms):
    per_check = max(100, int(timeout_ms / max(len(_BLOCK_PATTERNS), 1)))
    for pattern, override_type in _BLOCK_PATTERNS:
        try:
            locator = page.get_by_text(pattern, exact=False).first
            if locator.is_visible(timeout=per_check):
                return pattern, override_type
        except Exception:
            continue
    return None


def _get_dialog_text(page, timeout_ms):
    for selector in _DIALOG_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=timeout_ms):
                text = locator.inner_text(timeout=timeout_ms)
                if text and text.strip():
                    return text.strip()
        except Exception:
            continue
    return ""


def _match_block_text(text):
    text_lower = str(text or "").lower()
    for pattern, override_type in _BLOCK_PATTERNS:
        if pattern.lower() in text_lower:
            return pattern, override_type
    return "", None


def _shorten(value, limit=120):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
