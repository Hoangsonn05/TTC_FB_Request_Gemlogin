# -*- coding: utf-8 -*-
from dataclasses import dataclass
from enum import Enum


class FacebookContentType(str, Enum):
    STANDARD_POST = "STANDARD_POST"
    REEL = "REEL"
    PHOTO_VIEWER = "PHOTO_VIEWER"
    VIDEO = "VIDEO"
    POST_DIALOG = "POST_DIALOG"
    PROFILE = "PROFILE"
    PAGE = "PAGE"
    UNKNOWN = "UNKNOWN"


@dataclass
class TargetCheckResult:
    ok: bool
    reason: str
    target_type: str
    requested_url: str
    final_url: str
    evidence: str = ""
    retryable: bool = False


DEAD_TARGET_REASONS = {
    "POST_DELETED_OR_UNAVAILABLE",
    "REEL_DELETED_OR_UNAVAILABLE",
}


def _url_lower(page, requested_url=""):
    try:
        return str(getattr(page, "url", "") or requested_url or "").lower()
    except Exception:
        return str(requested_url or "").lower()


def _visible_count(locator):
    try:
        count = locator.count()
    except Exception:
        return 0
    visible = 0
    for i in range(count):
        try:
            if locator.nth(i).is_visible():
                visible += 1
        except Exception:
            continue
    return visible


def _has_visible_video(page):
    try:
        videos = page.locator("video")
        for i in range(videos.count()):
            video = videos.nth(i)
            if video.is_visible() and video.bounding_box():
                return True
    except Exception:
        return False
    return False


def _has_reel_action_rail(page):
    try:
        return bool(page.evaluate("""
            () => {
                const visible = (el) => {
                    const s = window.getComputedStyle(el);
                    if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) return null;
                    const r = el.getBoundingClientRect();
                    if (r.width < 8 || r.height < 8) return null;
                    if (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) return null;
                    return r;
                };
                const videos = Array.from(document.querySelectorAll('video'))
                    .map(v => ({ v, r: visible(v) }))
                    .filter(x => x.r)
                    .sort((a, b) => (b.r.width * b.r.height) - (a.r.width * a.r.height));
                if (!videos.length) return false;
                const vr = videos[0].r;
                const controls = Array.from(document.querySelectorAll('button,[role="button"]'))
                    .map(el => ({ el, r: visible(el), text: `${el.getAttribute('aria-label') || ''} ${el.textContent || ''}`.toLowerCase() }))
                    .filter(x => x.r)
                    .filter(x => {
                        const cx = x.r.left + x.r.width / 2;
                        const cy = x.r.top + x.r.height / 2;
                        return cx >= vr.right - 30 && cx <= Math.min(innerWidth - 8, vr.right + 260)
                            && cy >= vr.top - 80 && cy <= Math.min(innerHeight, vr.bottom + 180);
                    });
                const hasComment = controls.some(x => /comment|binh luan|bình luận/.test(x.text));
                const hasShare = controls.some(x => /share|chia se|chia sẻ/.test(x.text));
                const hasReact = controls.some(x => /like|thich|thích|react/.test(x.text) || x.el.getAttribute('aria-pressed') !== null);
                return controls.length >= 3 && (hasReact || (hasComment && hasShare));
            }
        """))
    except Exception:
        return False


def detect_facebook_content_type(page, requested_url=""):
    final_url = _url_lower(page, requested_url)
    if "/reel/" in final_url or "/reels/" in final_url:
        return FacebookContentType.REEL
    if "fb.watch/" in final_url and _has_reel_action_rail(page):
        return FacebookContentType.REEL
    if "/share/r/" in final_url and _has_reel_action_rail(page):
        return FacebookContentType.REEL
    if "/photo/" in final_url or "photo.php" in final_url:
        return FacebookContentType.PHOTO_VIEWER
    if "watch" in final_url or "/videos/" in final_url:
        if _has_reel_action_rail(page):
            return FacebookContentType.REEL
        return FacebookContentType.VIDEO
    try:
        dialogs = page.locator('[role="dialog"]')
        for i in range(dialogs.count()):
            dlg = dialogs.nth(i)
            if dlg.is_visible():
                if dlg.locator("video").count() and _has_reel_action_rail(page):
                    return FacebookContentType.REEL
                return FacebookContentType.POST_DIALOG
    except Exception:
        pass
    if _has_reel_action_rail(page):
        return FacebookContentType.REEL
    return FacebookContentType.STANDARD_POST


def classify_bad_facebook_url(final_url):
    url = str(final_url or "").lower()
    if "login" in url:
        return "LOGIN_REQUIRED"
    if "checkpoint" in url or "disabled" in url or "suspended" in url:
        return "CHECKPOINT_OR_LOCKED"
    if "unavailable" in url or "removed" in url:
        return "POST_DELETED_OR_UNAVAILABLE"
    if "recover" in url:
        return "LOGIN_REQUIRED"
    return ""


def check_facebook_target_live_result(page, link, target_type, timeout_ms=8000):
    final_url = str(getattr(page, "url", "") or "")
    bad = classify_bad_facebook_url(final_url)
    if bad:
        return TargetCheckResult(False, bad, target_type, link, final_url, evidence=f"url={final_url}")

    content_type = detect_facebook_content_type(page, link)
    if content_type == FacebookContentType.REEL:
        try:
            unavailable_text = page.get_by_text(
                "content unavailable|video unavailable|không khả dụng|khong kha dung|đã bị gỡ|da bi go",
                exact=False,
            )
            if unavailable_text.first.is_visible(timeout=500):
                return TargetCheckResult(False, "REEL_DELETED_OR_UNAVAILABLE", "REEL", link, final_url, "unavailable text")
        except Exception:
            pass
        if _has_visible_video(page):
            return TargetCheckResult(True, "OK", "REEL", link, final_url, evidence="visible video/reel rail")
        return TargetCheckResult(False, "LIVE_CHECK_TIMEOUT", "REEL", link, final_url, "reel url without visible video", True)

    if target_type == "profile":
        selectors = ["[data-pagelet='ProfileTilesFeed_0']", "h1", "[data-pagelet='ProfileAppSection_0']"]
        expected = "PROFILE"
    elif target_type == "page":
        selectors = ["[data-pagelet='ProfileTilesFeed_0']", "h1", "[role='main']"]
        expected = "PAGE"
    else:
        selectors = ["article", "[data-pagelet='FeedUnit']", "[role='article']", "div[data-ad-preview='message']"]
        expected = "STANDARD_POST"

    for sel in selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=max(300, timeout_ms // len(selectors))):
                return TargetCheckResult(True, "OK", expected, link, final_url, evidence=sel)
        except Exception:
            continue

    reason = "POST_DELETED_OR_UNAVAILABLE" if target_type == "post" else "LIVE_CHECK_TIMEOUT"
    return TargetCheckResult(False, reason, expected, link, final_url, "expected selectors not visible", reason == "LIVE_CHECK_TIMEOUT")
