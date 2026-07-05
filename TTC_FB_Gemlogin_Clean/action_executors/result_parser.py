# -*- coding: utf-8 -*-
"""ActionResultParser — Chuyển response từ browser-context fetch thành FacebookActionResult.

Quy tắc fail-closed:
- Chỉ success khi provider trả JSON có success=true VÀ verified=true.
- Nếu response mơ hồ → không claim.
- Nếu HTTP ok nhưng không verified → không claim.
- Nếu response là text thường → không claim.
"""

import json

from .result_utils import make_failed_result, make_success_result


class ActionResultParser:
    """Parse response từ BrowserContextRequestAdapter thành FacebookActionResult."""

    def parse(self, job, normalized, response):
        """Parse kết quả fetch.

        Args:
            job: Job object gốc từ TTC.
            normalized: NormalizedAction từ JobActionMapper.
            response: dict trả về từ BrowserContextRequestAdapter.run_configured_fetch().

        Returns:
            FacebookActionResult với success=True verified=True chỉ khi provider
            trả JSON {"success": true, "verified": true}.
        """
        if not isinstance(response, dict):
            return make_failed_result(
                job,
                "PAGE_CONTEXT_ACTION_FAILED",
                "Response is not a dict"
            )

        if not response.get("ok"):
            status = response.get("status", 0)
            raw_text = str(response.get("text") or "")[:300]
            return make_failed_result(
                job,
                "PAGE_CONTEXT_ACTION_FAILED",
                f"status={status} text={raw_text}"
            )

        raw_text = response.get("text") or ""

        # Thử parse JSON
        parsed = None
        try:
            parsed = json.loads(raw_text)
        except Exception:
            parsed = None

        if isinstance(parsed, dict):
            success = parsed.get("success") is True
            verified = parsed.get("verified") is True

            if success and verified:
                evidence = str(parsed.get("evidence") or "provider returned success+verified")
                return make_success_result(
                    job,
                    reason="ACTION_VERIFIED",
                    evidence=evidence,
                )

            # success=true nhưng verified=false, hoặc cả hai false
            reason = str(parsed.get("reason") or "ACTION_NOT_VERIFIED")
            evidence = str(parsed.get("evidence") or raw_text[:300])
            return make_failed_result(job, reason, evidence)

        # Response là text thường, không phải JSON verified → fail closed
        return make_failed_result(
            job,
            "ACTION_NOT_VERIFIED",
            "Provider response was not verified JSON."
        )
