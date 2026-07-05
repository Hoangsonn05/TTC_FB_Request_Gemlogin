# -*- coding: utf-8 -*-
"""Browser-context executor — tích hợp JobActionMapper + BrowserContextRequestAdapter + ActionResultParser.

Executor này chạy request adapter bên trong Playwright page của profile GemLogin.
Không chứa Facebook endpoint nội bộ, không hard-code payload, không dùng requests.Session.
Chỉ claim khi provider trả JSON có success=true và verified=true.
"""

from .base import BaseActionExecutor
from .browser_request_adapter import BrowserContextRequestAdapter
from .job_action_mapper import JobActionMapper
from .result_parser import ActionResultParser
from .result_utils import make_failed_result


class BrowserContextExecutor(BaseActionExecutor):
    name = "browser_context"

    def __init__(self):
        self.mapper = JobActionMapper()
        self.parser = ActionResultParser()

    def _action_config(self, context) -> dict:
        cfg = getattr(context, "config", None) or {}
        nested = cfg.get("action_executor") or {}
        return nested if isinstance(nested, dict) else {}

    def _validate_page(self, job, page, context):
        if page is None:
            return make_failed_result(
                job,
                "BROWSER_CONTEXT_UNAVAILABLE",
                "Playwright page is None.",
                page=page,
                context=context,
                strategy_id=self.name,
            )
        try:
            if page.is_closed():
                return make_failed_result(
                    job,
                    "PAGE_CLOSED",
                    "Playwright page is closed.",
                    page=page,
                    context=context,
                    strategy_id=self.name,
                )
        except Exception as exc:
            return make_failed_result(
                job,
                "BROWSER_CONTEXT_UNAVAILABLE",
                str(exc),
                page=page,
                context=context,
                strategy_id=self.name,
            )
        return None

    def execute(self, job, page, context):
        invalid = self._validate_page(job, page, context)
        if invalid is not None:
            return invalid

        action_config = self._action_config(context)
        timeout_ms = int(action_config.get("timeout_ms") or 15000)
        provider_enabled = bool(action_config.get("provider_enabled", False))

        adapter = BrowserContextRequestAdapter(timeout_ms=timeout_ms)

        # Probe browser context
        try:
            probe = adapter.probe_context(page)
        except Exception as exc:
            return make_failed_result(
                job,
                "BROWSER_CONTEXT_UNAVAILABLE",
                f"Browser context probe exception: {exc}",
                page=page,
                context=context,
                strategy_id=self.name,
            )

        if not probe.get("ok") or not probe.get("hasFetch"):
            return make_failed_result(
                job,
                "BROWSER_CONTEXT_UNAVAILABLE",
                f"Browser context probe failed: hasFetch={probe.get('hasFetch')} href={probe.get('href')}",
                page=page,
                context=context,
                strategy_id=self.name,
            )

        if not provider_enabled:
            href = probe.get("href", "")
            return make_failed_result(
                job,
                "PAGE_CONTEXT_ACTION_NOT_CONFIGURED",
                f"Browser context reachable (href={href}) but no permitted action provider is enabled. "
                "Set action_executor.provider_enabled=true and provider_url to activate.",
                page=page,
                context=context,
                strategy_id=self.name,
            )

        normalized = self.mapper.normalize(job)

        request_spec = self._build_request_spec_from_provider(
            normalized=normalized,
            action_config=action_config,
            context=context,
        )

        if not request_spec:
            return make_failed_result(
                job,
                "PAGE_CONTEXT_ACTION_NOT_CONFIGURED",
                "No valid request_spec returned by configured provider. "
                "Set action_executor.provider_url to a valid endpoint.",
                page=page,
                context=context,
                strategy_id=self.name,
            )

        try:
            response = adapter.run_configured_fetch(page, request_spec)
        except Exception as exc:
            return make_failed_result(
                job,
                "PAGE_CONTEXT_ACTION_FAILED",
                f"Browser-context fetch exception: {exc}",
                page=page,
                context=context,
                strategy_id=self.name,
            )

        result = self.parser.parse(job=job, normalized=normalized, response=response)
        return result

    def verify(self, job, page, context):
        invalid = self._validate_page(job, page, context)
        if invalid is not None:
            return invalid
        return make_failed_result(
            job,
            "ACTION_NOT_VERIFIED",
            "No separate verifier is configured for BrowserContextExecutor. "
            "Verification is embedded in execute() via provider JSON response.",
            page=page,
            context=context,
            strategy_id=self.name,
        )

    def _build_request_spec_from_provider(self, normalized, action_config, context) -> dict | None:
        """Hook provider: build request_spec từ config hợp lệ của dự án.

        Không hard-code Facebook endpoint ở đây.
        Không hard-code token/payload nội bộ ở đây.
        Không copy payload từ requests_fb.py.

        Chỉ build request_spec nếu provider_url được cấu hình rõ ràng.
        """
        provider_url = str(action_config.get("provider_url") or "").strip()

        if not provider_url:
            return None

        return {
            "url": provider_url,
            "method": "POST",
            "headers": {},
            "body": {
                "job_id": normalized.job_id,
                "action_group": normalized.action_group,
                "target_url": normalized.target_url,
                "target_id": normalized.target_id,
                "reaction_type": normalized.reaction_type,
                "comment_text": normalized.comment_text,
            },
        }
