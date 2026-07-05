# -*- coding: utf-8 -*-
"""facebook_graphql_context.py — Executor thực hiện Facebook action bằng GraphQL request
phát ra từ chính browser context của profile GemLogin đang chạy qua Playwright CDP.

Nguyên tắc bất biến:
  - Không dùng requests.Session, không truyền cookie thủ công.
  - Không hard-code browser headers (User-Agent, sec-ch-ua, Accept-Language…).
  - Không dùng provider_url ngoài.
  - fetch() dùng credentials:"include" để browser tự mang session/cookie của profile.
  - Fail-closed: chỉ trả success=True/verified=True khi mutation GraphQL xác nhận rõ ràng.
  - Không claim TTC nếu token thiếu, response lỗi, hoặc không verified.

Token extraction (fb_dtsg, jazoest, lsd, feedback_id) được chạy trong page.evaluate()
từ DOM/HTML hiện tại của profile — không parse bằng HTTP client ngoài.

Kỹ thuật GraphQL payload tham khảo từ TTCMMOFB/requests_fb.py (auto_like, auto_comment)
nhưng được build và phát ra từ browser context, không copy hard-coded headers.
"""

import json
import logging
from typing import Any

from .base import ActionContext, BaseActionExecutor
from .job_action_mapper import JobActionMapper
from .result_utils import make_failed_result, make_success_result

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Reaction type → Facebook reaction id mapping
# Nguồn: TTCMMOFB/requests_fb.py auto_like()
# ──────────────────────────────────────────────────────────────────────────────
REACTION_TYPE_MAP: dict[str, str] = {
    "LIKE":  "1635855486666999",
    "LOVE":  "1678524932434102",
    "CARE":  "613557422527858",
    "HAHA":  "115940658764963",
    "WOW":   "478547315650144",
    "SAD":   "908563459236466",
    "ANGRY": "444813342392137",
}

# Action groups được executor này hỗ trợ — bao gồm cả tên normalized lẫn job_type đầy đủ
REACTION_ACTION_GROUPS = {
    "reaction",                  # normalized bởi ttc_job_types/ACTION_GROUP_MAP
    "ttc_like_post_vip_cheo",
    "ttc_like_post_vip_re",
    "ttc_reaction_vip_cheo",
    "ttc_reaction_vip_re",
}

COMMENT_ACTION_GROUPS = {
    "comment",                   # normalized
    "ttc_comment",
}

FOLLOW_ACTION_GROUPS = {
    "follow",                    # normalized
    "ttc_follow",
}

PAGE_LIKE_ACTION_GROUPS = {
    "page_like",                 # normalized
    "ttc_like_page",
}

# Facebook domains hợp lệ
FACEBOOK_DOMAINS = {"www.facebook.com", "facebook.com", "m.facebook.com", "web.facebook.com"}

# GraphQL doc_id
REACT_DOC_ID    = "29333620026283566"   # CometUFIFeedbackReactMutation
COMMENT_DOC_ID  = "9761804193899543"    # useCometUFICreateCommentMutation

# ──────────────────────────────────────────────────────────────────────────────
# JavaScript chạy trong page.evaluate() để extract tokens từ HTML hiện tại
# ──────────────────────────────────────────────────────────────────────────────
_JS_EXTRACT_TOKENS = """
() => {
    try {
        const html = document.documentElement.innerHTML;
        const hostname = location.hostname;

        // Hàm helper tìm giá trị giữa hai chuỗi
        function extract(src, before, after) {
            const idx = src.indexOf(before);
            if (idx === -1) return null;
            const start = idx + before.length;
            const endIdx = src.indexOf(after, start);
            if (endIdx === -1) return null;
            const val = src.substring(start, endIdx);
            return val.length > 0 && val.length < 256 ? val : null;
        }

        // fb_dtsg: tìm nhiều pattern khác nhau
        let fb_dtsg = null;
        const dtsg_patterns = [
            ['"w":0,"f":"', '",'],
            ['"DTSGInitialData",[],{"token":"', '"}'],
            ['name="fb_dtsg" value="', '"'],
            ['"fb_dtsg":{"token":"', '"'],
        ];
        for (const [b, a] of dtsg_patterns) {
            fb_dtsg = extract(html, b, a);
            if (fb_dtsg) break;
        }

        // jazoest
        let jazoest = null;
        const jazoest_patterns = [
            ['comet_req=15&jazoest=', '",'],
            ['jazoest=', '&'],
            ['"jazoest":"', '"'],
            ['name="jazoest" value="', '"'],
        ];
        for (const [b, a] of jazoest_patterns) {
            jazoest = extract(html, b, a);
            if (jazoest) break;
        }

        // lsd token
        let lsd = null;
        const lsd_patterns = [
            ['["LSD",[],{"token":"', '"}'],
            ['"LSD",[],{"token":"', '"'],
            ['name="lsd" value="', '"'],
        ];
        for (const [b, a] of lsd_patterns) {
            lsd = extract(html, b, a);
            if (lsd) break;
        }

        // feedback_id — lấy cái đầu tiên tìm thấy
        let feedback_id = null;
        const fb_id_patterns = [
            ['"feedback":{"id":"', '"'],
            ['"feedback_id":"', '"'],
            ['feedback_id=', '&'],
        ];
        for (const [b, a] of fb_id_patterns) {
            feedback_id = extract(html, b, a);
            if (feedback_id) break;
        }

        return {
            ok: true,
            hostname: hostname,
            origin: location.origin,
            fb_dtsg: fb_dtsg,
            jazoest: jazoest,
            lsd: lsd,
            feedback_id: feedback_id,
        };
    } catch(e) {
        return {ok: false, error: String(e)};
    }
}
"""

# ──────────────────────────────────────────────────────────────────────────────
# JavaScript GraphQL fetch trong browser context — Reaction
# ──────────────────────────────────────────────────────────────────────────────
_JS_GRAPHQL_REACTION = """
async ({ fb_dtsg, jazoest, lsd, feedback_id, actor_id, reaction_id, doc_id, timeoutMs }) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const variables = JSON.stringify({
            input: {
                feedback_id: feedback_id,
                feedback_reaction_id: reaction_id,
                feedback_source: "TAHOE",
                is_tracking_encrypted: true,
                tracking: [],
                actor_id: actor_id,
                client_mutation_id: "1"
            },
            useDefaultActor: false,
            "__relay_internal__pv__CometUFIReactionsEnableShortNamerelayprovider": false
        });

        const params = new URLSearchParams();
        params.append("av", actor_id);
        params.append("__user", actor_id);
        params.append("fb_dtsg", fb_dtsg);
        params.append("jazoest", jazoest);
        params.append("lsd", lsd);
        params.append("doc_id", doc_id);
        params.append("fb_api_caller_class", "RelayModern");
        params.append("fb_api_req_friendly_name", "CometUFIFeedbackReactMutation");
        params.append("__dyn", "");
        params.append("variables", variables);
        params.append("server_timestamps", "true");

        const graphqlUrl = new URL("/api/graphql/", location.origin).toString();

        const resp = await fetch(graphqlUrl, {
            method: "POST",
            headers: {"content-type": "application/x-www-form-urlencoded"},
            body: params.toString(),
            credentials: "include",
            signal: controller.signal
        });

        const text = await resp.text();
        return {
            ok: resp.ok,
            status: resp.status,
            statusText: resp.statusText,
            url: resp.url,
            text: text
        };
    } catch(err) {
        return {
            ok: false,
            status: 0,
            statusText: String(err && err.name || "FETCH_ERROR"),
            url: "",
            text: String(err && err.message || err)
        };
    } finally {
        clearTimeout(timer);
    }
}
"""

# ──────────────────────────────────────────────────────────────────────────────
# JavaScript GraphQL fetch trong browser context — Comment
# ──────────────────────────────────────────────────────────────────────────────
_JS_GRAPHQL_COMMENT = """
async ({ fb_dtsg, jazoest, lsd, feedback_id, actor_id, comment_text, doc_id, timeoutMs }) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const variables = JSON.stringify({
            feedLocation: "NEWSFEED",
            feedbackSource: 1,
            groupID: null,
            input: {
                feedback_id: feedback_id,
                feedback_source: "TAHOE",
                is_tracking_encrypted: true,
                tracking: [],
                actor_id: actor_id,
                client_mutation_id: "1",
                message: {ranges: [], text: comment_text}
            },
            useDefaultActor: false,
            "__relay_internal__pv__CometUFIReactionsEnableShortNamerelayprovider": false
        });

        const params = new URLSearchParams();
        params.append("av", actor_id);
        params.append("__user", actor_id);
        params.append("fb_dtsg", fb_dtsg);
        params.append("jazoest", jazoest);
        params.append("lsd", lsd);
        params.append("doc_id", doc_id);
        params.append("fb_api_caller_class", "RelayModern");
        params.append("fb_api_req_friendly_name", "useCometUFICreateCommentMutation");
        params.append("__dyn", "");
        params.append("variables", variables);
        params.append("server_timestamps", "true");

        const graphqlUrl = new URL("/api/graphql/", location.origin).toString();

        const resp = await fetch(graphqlUrl, {
            method: "POST",
            headers: {"content-type": "application/x-www-form-urlencoded"},
            body: params.toString(),
            credentials: "include",
            signal: controller.signal
        });

        const text = await resp.text();
        return {
            ok: resp.ok,
            status: resp.status,
            statusText: resp.statusText,
            url: resp.url,
            text: text
        };
    } catch(err) {
        return {
            ok: false,
            status: 0,
            statusText: String(err && err.name || "FETCH_ERROR"),
            url: "",
            text: String(err && err.message || err)
        };
    } finally {
        clearTimeout(timer);
    }
}
"""


def _is_facebook_domain(hostname: str) -> bool:
    """Kiểm tra hostname có thuộc Facebook domain không."""
    h = str(hostname or "").lower().strip()
    return h in FACEBOOK_DOMAINS or h.endswith(".facebook.com")


def _safe_log(log_fn, msg: str) -> None:
    """Log an toàn, không raise exception."""
    try:
        log_fn(msg)
    except Exception:
        pass


def _parse_graphql_response(response: dict) -> tuple[bool, str, str]:
    """Parse GraphQL response, trả về (verified, reason, evidence).

    verified=True khi:
    - HTTP status OK
    - Response parse được JSON
    - Không có 'errors' key
    - Có 'data' key với nội dung mutation hợp lệ
    """
    if not isinstance(response, dict):
        return False, "GRAPHQL_RESPONSE_INVALID", "response is not dict"

    if not response.get("ok"):
        status = response.get("status", 0)
        text_snippet = str(response.get("text") or "")[:200]
        return False, "GRAPHQL_HTTP_ERROR", f"status={status} text={text_snippet}"

    raw_text = str(response.get("text") or "")

    # Parse JSON
    parsed = None
    try:
        parsed = json.loads(raw_text)
    except Exception:
        pass

    if not isinstance(parsed, dict):
        snippet = raw_text[:200]
        return False, "GRAPHQL_NOT_JSON", f"response not JSON: {snippet}"

    # Fail nếu có errors
    if "errors" in parsed and parsed["errors"]:
        err_snippet = str(parsed["errors"])[:300]
        return False, "GRAPHQL_ERRORS", f"errors={err_snippet}"

    # Verify có data
    data = parsed.get("data")
    if data is not None:
        return True, "GRAPHQL_MUTATION_OK", f"data keys={list(data.keys()) if isinstance(data, dict) else 'present'}"

    # Không có errors và không có data — ambiguous, fail-closed
    snippet = raw_text[:200]
    return False, "GRAPHQL_AMBIGUOUS", f"no data no errors: {snippet}"


class FacebookGraphQLContextExecutor(BaseActionExecutor):
    """Executor thực hiện Facebook action qua GraphQL request phát ra từ browser context.

    Thay thế hoàn toàn cơ chế provider_url cũ.
    Không dùng requests.Session, không cookie thủ công, không hard-code headers.
    fetch() dùng credentials:"include" — browser tự dùng session của profile GemLogin.
    """

    name = "facebook_graphql_context"

    def __init__(self):
        self.mapper = JobActionMapper()

    def _get_timeout_ms(self, context: ActionContext) -> int:
        cfg = getattr(context, "config", None) or {}
        ae = cfg.get("action_executor") if isinstance(cfg.get("action_executor"), dict) else {}
        return int(ae.get("timeout_ms") or 15000)

    def _log(self, context: ActionContext, level: str, msg: str) -> None:
        """Log thông qua context.logger nếu có, fallback module logger.
        Tương thích cả WorkerLogger.log(worker_id, msg, level) lẫn standard logging.Logger.
        Không log token/cookie/lsd/fb_dtsg."""
        log_msg = f"[FacebookAction] worker={getattr(context, 'worker_id', '')} profile={getattr(context, 'profile_id', '')} {msg}"
        ctx_logger = getattr(context, "logger", None)
        worker_id = str(getattr(context, "worker_id", "") or "")

        try:
            if ctx_logger is not None:
                # GUI WorkerLogger: log(worker_id, message, level)
                gui_log = getattr(ctx_logger, "log", None)
                if callable(gui_log):
                    gui_log(worker_id, log_msg, level)
                    return

                # Standard logging.Logger style: .info/.warning/.error
                std_fn = getattr(ctx_logger, level, None)
                if callable(std_fn):
                    std_fn(log_msg)
                    return

            # Fallback: module-level logger
            fn = getattr(logger, level, logger.info)
            fn(log_msg)
        except Exception:
            pass

    def _validate_page(self, job: Any, page: Any, context: ActionContext):
        """Validate page tồn tại và chưa closed. Trả None nếu OK, result nếu fail."""
        if page is None:
            return make_failed_result(
                job, "BROWSER_CONTEXT_UNAVAILABLE", "Playwright page is None.",
                page=page, context=context, strategy_id=self.name,
            )
        try:
            if page.is_closed():
                return make_failed_result(
                    job, "PAGE_CLOSED", "Playwright page is closed.",
                    page=page, context=context, strategy_id=self.name,
                )
        except Exception as exc:
            return make_failed_result(
                job, "BROWSER_CONTEXT_UNAVAILABLE", str(exc),
                page=page, context=context, strategy_id=self.name,
            )
        return None

    def _ensure_facebook_page(self, job: Any, page: Any, context: ActionContext, target_url: str):
        """Đảm bảo page đang ở Facebook domain.

        Nếu page hiện tại chưa phải Facebook domain, navigate bằng page.goto().
        Không dùng HTTP client ngoài.
        Trả (None, tokens_ok) nếu OK, (result_fail, None) nếu fail.
        """
        try:
            probe = page.evaluate("() => ({hostname: location.hostname, href: location.href})")
        except Exception as exc:
            return make_failed_result(
                job, "BROWSER_CONTEXT_UNAVAILABLE", f"probe exception: {exc}",
                page=page, context=context, strategy_id=self.name,
            ), None

        hostname = probe.get("hostname", "")
        href = probe.get("href", "")

        if not _is_facebook_domain(hostname):
            self._log(context, "info", f"current page not Facebook (hostname={hostname}), navigating to target")
            nav_url = target_url or getattr(context, "link", "") or "https://www.facebook.com"
            try:
                page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                return make_failed_result(
                    job, "NAVIGATION_FAILED", f"goto({nav_url}) failed: {exc}",
                    page=page, context=context, strategy_id=self.name,
                ), None

            # Re-probe sau navigate
            try:
                probe = page.evaluate("() => ({hostname: location.hostname, href: location.href})")
                hostname = probe.get("hostname", "")
                href = probe.get("href", "")
            except Exception as exc:
                return make_failed_result(
                    job, "BROWSER_CONTEXT_UNAVAILABLE", f"post-nav probe failed: {exc}",
                    page=page, context=context, strategy_id=self.name,
                ), None

            if not _is_facebook_domain(hostname):
                return make_failed_result(
                    job, "NOT_FACEBOOK_DOMAIN", f"after navigate still not Facebook: hostname={hostname} href={href}",
                    page=page, context=context, strategy_id=self.name,
                ), None

        return None, href

    def _extract_tokens(self, job: Any, page: Any, context: ActionContext):
        """Extract fb_dtsg, jazoest, lsd, feedback_id từ DOM của page hiện tại.

        Trả (None, tokens_dict) nếu OK, (result_fail, None) nếu thiếu token bắt buộc.
        Không log giá trị token.
        """
        try:
            tokens = page.evaluate(_JS_EXTRACT_TOKENS)
        except Exception as exc:
            return make_failed_result(
                job, "FACEBOOK_TOKEN_EXTRACTION_FAILED", f"evaluate exception: {exc}",
                page=page, context=context, strategy_id=self.name,
            ), None

        if not isinstance(tokens, dict) or not tokens.get("ok"):
            err = tokens.get("error", "unknown") if isinstance(tokens, dict) else "not dict"
            return make_failed_result(
                job, "FACEBOOK_TOKEN_EXTRACTION_FAILED", f"JS error: {err}",
                page=page, context=context, strategy_id=self.name,
            ), None

        missing = []
        for key in ("fb_dtsg", "jazoest", "lsd", "feedback_id"):
            if not tokens.get(key):
                missing.append(key)

        if missing:
            return make_failed_result(
                job, "FACEBOOK_TOKEN_EXTRACTION_FAILED",
                f"missing fb_dtsg/jazoest/lsd/feedback_id — missing: {missing}",
                page=page, context=context, strategy_id=self.name,
            ), None

        return None, tokens

    def _do_reaction(self, job: Any, page: Any, context: ActionContext, tokens: dict, normalized) -> Any:
        """Thực hiện reaction action qua GraphQL trong browser context."""
        reaction_type = str(normalized.reaction_type or "LIKE").upper()
        reaction_id = REACTION_TYPE_MAP.get(reaction_type, REACTION_TYPE_MAP["LIKE"])

        actor_id = str(getattr(context, "uid", "") or "")
        if not actor_id:
            return make_failed_result(
                job, "MISSING_ACTOR_ID", "context.uid is empty — TTC UID not configured",
                page=page, context=context, strategy_id=self.name,
            )

        timeout_ms = self._get_timeout_ms(context)
        self._log(context, "info",
                  f"executor={self.name} action=reaction reaction_type={reaction_type} "
                  f"origin={tokens.get('origin', '')} target={normalized.target_url}")

        try:
            response = page.evaluate(
                _JS_GRAPHQL_REACTION,
                {
                    "fb_dtsg":     tokens["fb_dtsg"],
                    "jazoest":     tokens["jazoest"],
                    "lsd":         tokens["lsd"],
                    "feedback_id": tokens["feedback_id"],
                    "actor_id":    actor_id,
                    "reaction_id": reaction_id,
                    "doc_id":      REACT_DOC_ID,
                    "timeoutMs":   timeout_ms,
                },
            )
        except Exception as exc:
            return make_failed_result(
                job, "PAGE_CONTEXT_ACTION_FAILED", f"reaction evaluate exception: {exc}",
                page=page, context=context, strategy_id=self.name,
            )

        status = response.get("status", 0) if isinstance(response, dict) else 0
        verified, reason, evidence = _parse_graphql_response(response)
        self._log(context, "info",
                  f"executor={self.name} action=reaction GraphQL status={status} verified={verified} reason={reason}")

        if verified:
            return make_success_result(
                job, reason="GRAPHQL_MUTATION_OK", evidence=evidence,
                page=page, context=context, strategy_id=self.name,
            )
        return make_failed_result(
            job, reason, evidence,
            page=page, context=context, strategy_id=self.name,
        )

    def _do_comment(self, job: Any, page: Any, context: ActionContext, tokens: dict, normalized) -> Any:
        """Thực hiện comment action qua GraphQL trong browser context."""
        comment_text = str(normalized.comment_text or "").strip()
        if not comment_text:
            return make_failed_result(
                job, "EMPTY_COMMENT_TEXT", "comment_text is empty — không thực hiện comment",
                page=page, context=context, strategy_id=self.name,
            )

        actor_id = str(getattr(context, "uid", "") or "")
        if not actor_id:
            return make_failed_result(
                job, "MISSING_ACTOR_ID", "context.uid is empty — TTC UID not configured",
                page=page, context=context, strategy_id=self.name,
            )

        timeout_ms = self._get_timeout_ms(context)
        self._log(context, "info",
                  f"executor={self.name} action=comment origin={tokens.get('origin', '')} target={normalized.target_url}")

        try:
            response = page.evaluate(
                _JS_GRAPHQL_COMMENT,
                {
                    "fb_dtsg":      tokens["fb_dtsg"],
                    "jazoest":      tokens["jazoest"],
                    "lsd":          tokens["lsd"],
                    "feedback_id":  tokens["feedback_id"],
                    "actor_id":     actor_id,
                    "comment_text": comment_text,
                    "doc_id":       COMMENT_DOC_ID,
                    "timeoutMs":    timeout_ms,
                },
            )
        except Exception as exc:
            return make_failed_result(
                job, "PAGE_CONTEXT_ACTION_FAILED", f"comment evaluate exception: {exc}",
                page=page, context=context, strategy_id=self.name,
            )

        status = response.get("status", 0) if isinstance(response, dict) else 0
        verified, reason, evidence = _parse_graphql_response(response)
        self._log(context, "info",
                  f"executor={self.name} action=comment GraphQL status={status} verified={verified} reason={reason}")

        if verified:
            return make_success_result(
                job, reason="GRAPHQL_MUTATION_OK", evidence=evidence,
                page=page, context=context, strategy_id=self.name,
            )
        return make_failed_result(
            job, reason, evidence,
            page=page, context=context, strategy_id=self.name,
        )

    def execute(self, job: Any, page: Any, context: ActionContext) -> Any:
        """Entry point chính của executor.

        Flow:
        1. Validate page
        2. Normalize job
        3. Check action_group
        4. Ensure Facebook domain (navigate nếu cần)
        5. Extract tokens từ DOM
        6. Thực hiện GraphQL action trong browser context
        7. Return verified result (fail-closed)
        """
        # 1. Validate page
        invalid = self._validate_page(job, page, context)
        if invalid is not None:
            return invalid

        # 2. Normalize job
        normalized = self.mapper.normalize(job)
        action_group = normalized.action_group.lower()
        target_url = normalized.target_url or getattr(context, "link", "") or ""

        self._log(context, "info",
                  f"executor={self.name} action_group={action_group} target={target_url}")

        # 3. Check action_group — fail-closed cho follow/page_like
        if action_group in FOLLOW_ACTION_GROUPS:
            self._log(context, "warning",
                      f"executor={self.name} action_group={action_group} not implemented (fail-closed)")
            return make_failed_result(
                job, "ACTION_GROUP_NOT_IMPLEMENTED",
                f"follow action not implemented in facebook_graphql_context executor",
                page=page, context=context, strategy_id=self.name,
            )

        if action_group in PAGE_LIKE_ACTION_GROUPS:
            self._log(context, "warning",
                      f"executor={self.name} action_group={action_group} not implemented (fail-closed)")
            return make_failed_result(
                job, "ACTION_GROUP_NOT_IMPLEMENTED",
                f"page_like action not implemented in facebook_graphql_context executor",
                page=page, context=context, strategy_id=self.name,
            )

        is_reaction = action_group in REACTION_ACTION_GROUPS
        is_comment  = action_group in COMMENT_ACTION_GROUPS

        if not is_reaction and not is_comment:
            self._log(context, "warning",
                      f"executor={self.name} action_group={action_group} unknown (fail-closed)")
            return make_failed_result(
                job, "ACTION_GROUP_NOT_IMPLEMENTED",
                f"action_group={action_group} not supported by facebook_graphql_context",
                page=page, context=context, strategy_id=self.name,
            )

        # 4. Ensure Facebook domain
        fail_result, _href = self._ensure_facebook_page(job, page, context, target_url)
        if fail_result is not None:
            return fail_result

        # 5. Extract tokens từ DOM
        fail_result, tokens = self._extract_tokens(job, page, context)
        if fail_result is not None:
            self._log(context, "warning",
                      f"executor={self.name} verified=False reason=FACEBOOK_TOKEN_EXTRACTION_FAILED "
                      f"evidence=missing fb_dtsg/jazoest/lsd/feedback_id")
            return fail_result

        # 6. Thực hiện action
        if is_reaction:
            return self._do_reaction(job, page, context, tokens, normalized)
        if is_comment:
            return self._do_comment(job, page, context, tokens, normalized)

        # Fallback (không bao giờ tới đây)
        return make_failed_result(
            job, "ACTION_GROUP_NOT_IMPLEMENTED", f"action_group={action_group}",
            page=page, context=context, strategy_id=self.name,
        )

    def verify(self, job: Any, page: Any, context: ActionContext) -> Any:
        """Verification đã tích hợp trong execute() qua parse GraphQL response."""
        invalid = self._validate_page(job, page, context)
        if invalid is not None:
            return invalid
        return make_failed_result(
            job, "ACTION_NOT_VERIFIED",
            "Verification is embedded in execute() via GraphQL response parsing.",
            page=page, context=context, strategy_id=self.name,
        )
