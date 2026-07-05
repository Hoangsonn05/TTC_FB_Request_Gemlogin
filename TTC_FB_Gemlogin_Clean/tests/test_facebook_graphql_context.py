# -*- coding: utf-8 -*-
"""Tests cho FacebookGraphQLContextExecutor.

Bao gồm:
- fail khi page None/closed
- fail khi thiếu token
- fail khi action_group follow/page_like chưa implement
- reaction mapping LIKE/LOVE/CARE/HAHA/WOW/SAD/ANGRY
- comment empty fail
- claim gate vẫn không claim khi verified=False
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from action_executors.facebook_graphql_context import (
    FacebookGraphQLContextExecutor,
    REACTION_TYPE_MAP,
    REACTION_ACTION_GROUPS,
    COMMENT_ACTION_GROUPS,
    FOLLOW_ACTION_GROUPS,
    PAGE_LIKE_ACTION_GROUPS,
    _is_facebook_domain,
    _parse_graphql_response,
)
from action_executors.base import ActionContext
from facebook_action_result import FacebookActionResult, is_action_claimable


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_job(action_group="ttc_like_post_vip_cheo", reaction_type="LIKE",
               comment_text="hello", target_url="https://www.facebook.com/123", target_id="123"):
    return {
        "job_id": "job_001",
        "action_group": action_group,
        "reaction_type": reaction_type,
        "comment_text": comment_text,
        "link": target_url,
        "idpost": target_id,
    }


def _make_context(uid="111111111"):
    return ActionContext(
        worker_id="w1",
        profile_id="p1",
        uid=uid,
        action_group="reaction",
        target_type="STANDARD_POST",
        link="https://www.facebook.com/123",
    )


class _FakePageOpen:
    """Page giả đang mở, trả token hợp lệ."""

    def __init__(self, tokens=None, graphql_response=None, hostname="www.facebook.com"):
        self._closed = False
        self._tokens = tokens or {
            "ok": True,
            "hostname": hostname,
            "origin": "https://www.facebook.com",
            "fb_dtsg": "AQ_fake_dtsg",
            "jazoest": "12345",
            "lsd": "fake_lsd",
            "feedback_id": "ZmVlZGJhY2s=",
        }
        self._graphql_response = graphql_response or {
            "ok": True,
            "status": 200,
            "statusText": "OK",
            "url": "https://www.facebook.com/api/graphql/",
            "text": '{"data": {"feedback_react": {"feedback": {"id": "ZmVlZGJhY2s="}}}}',
        }
        self._hostname = hostname
        self._probe_data = {"hostname": hostname, "href": f"https://{hostname}/123"}

    def is_closed(self):
        return self._closed

    def evaluate(self, script, args=None):
        # probe_context call (no args) -> probe data
        if args is None and "location.hostname" in script and "location.href" in script and "innerHTML" not in script:
            return self._probe_data
        # _JS_EXTRACT_TOKENS
        if args is None and "innerHTML" in script:
            return self._tokens
        # _JS_GRAPHQL_REACTION hoặc _JS_GRAPHQL_COMMENT (có args)
        if args is not None:
            return self._graphql_response
        return {}

    def goto(self, url, **kwargs):
        pass


class _FakePageClosed:
    def is_closed(self):
        return True


class _FakePageMissingTokens:
    """Page trả token thiếu."""

    def is_closed(self):
        return False

    def evaluate(self, script, args=None):
        if args is None and "location.hostname" in script and "innerHTML" not in script:
            return {"hostname": "www.facebook.com", "href": "https://www.facebook.com/123"}
        if args is None and "innerHTML" in script:
            return {
                "ok": True,
                "hostname": "www.facebook.com",
                "origin": "https://www.facebook.com",
                "fb_dtsg": None,   # thiếu
                "jazoest": "12345",
                "lsd": "lsd123",
                "feedback_id": None,  # thiếu
            }
        return {}

    def goto(self, url, **kwargs):
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Tests: page validation
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_fail_page_none():
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(_make_job(), page=None, context=_make_context())
    assert isinstance(result, FacebookActionResult)
    assert result.success is False
    assert result.verified is False
    assert "BROWSER_CONTEXT_UNAVAILABLE" in result.reason
    assert not is_action_claimable(result)


def test_executor_fail_page_closed():
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(_make_job(), page=_FakePageClosed(), context=_make_context())
    assert isinstance(result, FacebookActionResult)
    assert result.success is False
    assert result.verified is False
    assert result.reason in ("PAGE_CLOSED", "BROWSER_CONTEXT_UNAVAILABLE")
    assert not is_action_claimable(result)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: action_group not implemented
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_fail_follow_not_implemented():
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(_make_job(action_group="follow"), page=_FakePageOpen(), context=_make_context())
    assert result.success is False
    assert result.verified is False
    assert "ACTION_GROUP_NOT_IMPLEMENTED" in result.reason
    assert not is_action_claimable(result)


def test_executor_fail_ttc_follow_not_implemented():
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(_make_job(action_group="ttc_follow"), page=_FakePageOpen(), context=_make_context())
    assert result.success is False
    assert "ACTION_GROUP_NOT_IMPLEMENTED" in result.reason


def test_executor_fail_page_like_not_implemented():
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(_make_job(action_group="page_like"), page=_FakePageOpen(), context=_make_context())
    assert result.success is False
    assert "ACTION_GROUP_NOT_IMPLEMENTED" in result.reason
    assert not is_action_claimable(result)


def test_executor_fail_ttc_like_page_not_implemented():
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(_make_job(action_group="ttc_like_page"), page=_FakePageOpen(), context=_make_context())
    assert result.success is False
    assert "ACTION_GROUP_NOT_IMPLEMENTED" in result.reason


# ──────────────────────────────────────────────────────────────────────────────
# Tests: token extraction
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_fail_missing_tokens():
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(_make_job(), page=_FakePageMissingTokens(), context=_make_context())
    assert result.success is False
    assert result.verified is False
    assert "FACEBOOK_TOKEN_EXTRACTION_FAILED" in result.reason
    assert not is_action_claimable(result)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: reaction mapping
# ──────────────────────────────────────────────────────────────────────────────

def test_reaction_mapping_all_types():
    expected = {
        "LIKE":  "1635855486666999",
        "LOVE":  "1678524932434102",
        "CARE":  "613557422527858",
        "HAHA":  "115940658764963",
        "WOW":   "478547315650144",
        "SAD":   "908563459236466",
        "ANGRY": "444813342392137",
    }
    for reaction, expected_id in expected.items():
        assert REACTION_TYPE_MAP[reaction] == expected_id, f"Mismatch for {reaction}"


def test_reaction_mapping_complete():
    """Đảm bảo đủ 7 loại reaction."""
    assert len(REACTION_TYPE_MAP) == 7
    for k in ("LIKE", "LOVE", "CARE", "HAHA", "WOW", "SAD", "ANGRY"):
        assert k in REACTION_TYPE_MAP


# ──────────────────────────────────────────────────────────────────────────────
# Tests: comment empty fail
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_fail_empty_comment():
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(
        _make_job(action_group="ttc_comment", comment_text=""),
        page=_FakePageOpen(),
        context=_make_context(),
    )
    assert result.success is False
    assert result.verified is False
    assert "EMPTY_COMMENT_TEXT" in result.reason
    assert not is_action_claimable(result)


def test_executor_fail_whitespace_comment():
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(
        _make_job(action_group="ttc_comment", comment_text="   "),
        page=_FakePageOpen(),
        context=_make_context(),
    )
    assert result.success is False
    assert "EMPTY_COMMENT_TEXT" in result.reason


# ──────────────────────────────────────────────────────────────────────────────
# Tests: reaction success path
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_reaction_success():
    ex = FacebookGraphQLContextExecutor()
    page = _FakePageOpen()
    result = ex.execute(_make_job(action_group="ttc_like_post_vip_cheo", reaction_type="LIKE"),
                        page=page, context=_make_context())
    assert result.success is True
    assert result.verified is True
    assert is_action_claimable(result)


def test_executor_reaction_success_love():
    ex = FacebookGraphQLContextExecutor()
    page = _FakePageOpen()
    result = ex.execute(_make_job(action_group="ttc_reaction_vip_cheo", reaction_type="LOVE"),
                        page=page, context=_make_context())
    assert result.success is True
    assert result.verified is True


# ──────────────────────────────────────────────────────────────────────────────
# Tests: comment success path
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_comment_success():
    comment_resp = {
        "ok": True,
        "status": 200,
        "statusText": "OK",
        "url": "https://www.facebook.com/api/graphql/",
        "text": '{"data": {"comment_create": {"comment": {"id": "cmt123"}}}}',
    }
    ex = FacebookGraphQLContextExecutor()
    page = _FakePageOpen(graphql_response=comment_resp)
    result = ex.execute(
        _make_job(action_group="ttc_comment", comment_text="Test comment"),
        page=page, context=_make_context(),
    )
    assert result.success is True
    assert result.verified is True
    assert is_action_claimable(result)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: GraphQL fail → không claim
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_graphql_errors_not_claimed():
    error_resp = {
        "ok": True,
        "status": 200,
        "statusText": "OK",
        "url": "https://www.facebook.com/api/graphql/",
        "text": '{"errors": [{"message": "invalid token"}]}',
    }
    ex = FacebookGraphQLContextExecutor()
    page = _FakePageOpen(graphql_response=error_resp)
    result = ex.execute(_make_job(), page=page, context=_make_context())
    assert result.success is False
    assert result.verified is False
    assert not is_action_claimable(result)


def test_executor_graphql_http_error_not_claimed():
    http_error_resp = {
        "ok": False,
        "status": 500,
        "statusText": "Internal Server Error",
        "url": "https://www.facebook.com/api/graphql/",
        "text": "Server Error",
    }
    ex = FacebookGraphQLContextExecutor()
    page = _FakePageOpen(graphql_response=http_error_resp)
    result = ex.execute(_make_job(), page=page, context=_make_context())
    assert result.success is False
    assert result.verified is False
    assert not is_action_claimable(result)


def test_executor_graphql_ambiguous_no_data_not_claimed():
    ambig_resp = {
        "ok": True,
        "status": 200,
        "statusText": "OK",
        "url": "https://www.facebook.com/api/graphql/",
        "text": '{}',  # không có data, không có errors
    }
    ex = FacebookGraphQLContextExecutor()
    page = _FakePageOpen(graphql_response=ambig_resp)
    result = ex.execute(_make_job(), page=page, context=_make_context())
    assert result.success is False
    assert not is_action_claimable(result)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _is_facebook_domain helper
# ──────────────────────────────────────────────────────────────────────────────

def test_is_facebook_domain_valid():
    assert _is_facebook_domain("www.facebook.com") is True
    assert _is_facebook_domain("facebook.com") is True
    assert _is_facebook_domain("m.facebook.com") is True
    assert _is_facebook_domain("web.facebook.com") is True


def test_is_facebook_domain_invalid():
    assert _is_facebook_domain("google.com") is False
    assert _is_facebook_domain("evil-facebook.com") is False
    assert _is_facebook_domain("") is False
    assert _is_facebook_domain("instagram.com") is False


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _parse_graphql_response
# ──────────────────────────────────────────────────────────────────────────────

def test_parse_graphql_response_success():
    resp = {"ok": True, "status": 200, "text": '{"data": {"x": 1}}'}
    verified, reason, evidence = _parse_graphql_response(resp)
    assert verified is True
    assert "OK" in reason


def test_parse_graphql_response_errors():
    resp = {"ok": True, "status": 200, "text": '{"errors": [{"message": "bad"}]}'}
    verified, reason, evidence = _parse_graphql_response(resp)
    assert verified is False
    assert "GRAPHQL_ERRORS" in reason


def test_parse_graphql_response_http_fail():
    resp = {"ok": False, "status": 403, "text": "forbidden"}
    verified, reason, evidence = _parse_graphql_response(resp)
    assert verified is False
    assert "GRAPHQL_HTTP_ERROR" in reason


def test_parse_graphql_response_not_json():
    resp = {"ok": True, "status": 200, "text": "not json at all"}
    verified, reason, evidence = _parse_graphql_response(resp)
    assert verified is False
    assert "GRAPHQL_NOT_JSON" in reason


def test_parse_graphql_response_ambiguous():
    resp = {"ok": True, "status": 200, "text": "{}"}
    verified, reason, evidence = _parse_graphql_response(resp)
    assert verified is False


# ──────────────────────────────────────────────────────────────────────────────
# Tests: executor name
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_name():
    ex = FacebookGraphQLContextExecutor()
    assert ex.name == "facebook_graphql_context"


# ──────────────────────────────────────────────────────────────────────────────
# Tests: missing actor_id (uid)
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_fail_missing_uid():
    ex = FacebookGraphQLContextExecutor()
    ctx = _make_context(uid="")  # UID trống
    result = ex.execute(_make_job(), page=_FakePageOpen(), context=ctx)
    assert result.success is False
    assert result.verified is False
    assert "MISSING_ACTOR_ID" in result.reason
    assert not is_action_claimable(result)


# ──────────────────────────────────────────────────────────────────────────────
# Tests: normalized action group names (reaction/comment từ ttc_job_types)
# ──────────────────────────────────────────────────────────────────────────────

def test_action_group_sets_contain_normalized_names():
    """Đảm bảo sets chứa tên normalized từ ttc_job_types/ACTION_GROUP_MAP."""
    assert "reaction" in REACTION_ACTION_GROUPS
    assert "comment" in COMMENT_ACTION_GROUPS
    assert "follow" in FOLLOW_ACTION_GROUPS
    assert "page_like" in PAGE_LIKE_ACTION_GROUPS


def test_executor_reaction_normalized_group():
    """action_group='reaction' (normalized) phải hoạt động như ttc_like_post_vip_cheo."""
    ex = FacebookGraphQLContextExecutor()
    page = _FakePageOpen()
    result = ex.execute(_make_job(action_group="reaction", reaction_type="LIKE"),
                        page=page, context=_make_context())
    assert result.success is True
    assert result.verified is True
    assert is_action_claimable(result)


def test_executor_comment_normalized_group():
    """action_group='comment' (normalized) phải hoạt động như ttc_comment."""
    comment_resp = {
        "ok": True, "status": 200, "statusText": "OK",
        "url": "https://www.facebook.com/api/graphql/",
        "text": '{"data": {"comment_create": {"comment": {"id": "cmt_norm"}}}}',
    }
    ex = FacebookGraphQLContextExecutor()
    page = _FakePageOpen(graphql_response=comment_resp)
    result = ex.execute(
        _make_job(action_group="comment", comment_text="Normalized comment"),
        page=page, context=_make_context(),
    )
    assert result.success is True
    assert result.verified is True


def test_executor_follow_normalized_group_fails_closed():
    """action_group='follow' (normalized) phải fail-closed."""
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(_make_job(action_group="follow"), page=_FakePageOpen(), context=_make_context())
    assert result.success is False
    assert "ACTION_GROUP_NOT_IMPLEMENTED" in result.reason


def test_executor_page_like_normalized_group_fails_closed():
    """action_group='page_like' (normalized) phải fail-closed."""
    ex = FacebookGraphQLContextExecutor()
    result = ex.execute(_make_job(action_group="page_like"), page=_FakePageOpen(), context=_make_context())
    assert result.success is False
    assert "ACTION_GROUP_NOT_IMPLEMENTED" in result.reason


# ──────────────────────────────────────────────────────────────────────────────
# Tests: _log tương thích WorkerLogger (GUI) style
# ──────────────────────────────────────────────────────────────────────────────

def test_log_compatible_with_workerlogger_style():
    """_log() phải gọi logger.log(worker_id, msg, level) không raise exception."""
    logged = []

    class FakeWorkerLogger:
        def log(self, worker_id, message, level="info"):
            logged.append((worker_id, message, level))

    ctx = ActionContext(
        worker_id="w99",
        profile_id="p99",
        uid="111",
        action_group="reaction",
        target_type="STANDARD_POST",
        link="https://www.facebook.com/123",
        logger=FakeWorkerLogger(),
    )

    ex = FacebookGraphQLContextExecutor()
    # Gọi _log trực tiếp
    ex._log(ctx, "info", "test message")
    ex._log(ctx, "warning", "test warning")

    assert len(logged) == 2
    assert logged[0][0] == "w99"
    assert "test message" in logged[0][1]
    assert logged[0][2] == "info"
    assert logged[1][2] == "warning"


def test_log_compatible_with_standard_logger_style():
    """_log() phải gọi logger.info/warning nếu không có .log() — không raise."""
    logged = []

    class FakeStdLogger:
        def info(self, msg):
            logged.append(("info", msg))
        def warning(self, msg):
            logged.append(("warning", msg))

    ctx = ActionContext(
        worker_id="w88",
        profile_id="p88",
        uid="222",
        action_group="reaction",
        target_type="STANDARD_POST",
        link="https://www.facebook.com/123",
        logger=FakeStdLogger(),
    )

    ex = FacebookGraphQLContextExecutor()
    ex._log(ctx, "info", "std info msg")
    ex._log(ctx, "warning", "std warning msg")

    assert len(logged) == 2
    assert logged[0][0] == "info"
    assert "std info msg" in logged[0][1]


def test_log_no_crash_when_logger_is_none():
    """_log() không được raise khi context.logger là None."""
    ctx = ActionContext(
        worker_id="w77",
        profile_id="p77",
        uid="333",
        action_group="reaction",
        target_type="STANDARD_POST",
        link="https://www.facebook.com/123",
    )
    ex = FacebookGraphQLContextExecutor()
    # Không được raise
    ex._log(ctx, "info", "no logger test")
    ex._log(ctx, "warning", "no logger warning")
    ex._log(ctx, "error", "no logger error")
    ex._log(ctx, "error", "no logger error")

