# -*- coding: utf-8 -*-
"""ClaimGate — Chặn TTC claim nếu action chưa được verified đúng quy trình.

ClaimGate là lớp bảo vệ cuối cùng trước khi gọi TTCClient.claim_reward().
Chỉ can_claim=True khi action_result.success=True VÀ action_result.verified=True
VÀ reason không thuộc danh sách bị chặn.
"""


class ClaimGate:
    """Cổng kiểm tra điều kiện trước khi claim TTC.

    Sử dụng trong ttc_runtime.py:

        claim_gate = ClaimGate()
        if not claim_gate.can_claim(action_result):
            logger.warning("Skip claim: action not claimable.")
            continue
        claim_result = ttc_client.claim_reward(job)
    """

    BLOCKED_REASONS = frozenset({
        "ACTION_EXECUTOR_UNSUPPORTED",
        "DRY_RUN_NOT_CLAIMABLE",
        "BROWSER_CONTEXT_UNAVAILABLE",
        "PAGE_CLOSED",
        "PAGE_CONTEXT_ACTION_NOT_CONFIGURED",
        "PAGE_CONTEXT_ACTION_FAILED",
        "ACTION_NOT_VERIFIED",
        "TARGET_UNAVAILABLE",
        "LOGIN_REQUIRED",
        "CHECKPOINT_OR_LOCKED",
        "CLAIM_GUARD_BLOCKED_UNVERIFIED_ACTION",
    })

    def can_claim(self, action_result) -> bool:
        """Kiểm tra action_result có đủ điều kiện claim không.

        Returns:
            True chỉ khi:
            - action_result không phải None
            - success=True
            - verified=True
            - reason không thuộc BLOCKED_REASONS
        """
        if action_result is None:
            return False

        if not getattr(action_result, "success", False):
            return False

        if not getattr(action_result, "verified", False):
            return False

        reason = str(getattr(action_result, "reason", "") or "")
        if reason in self.BLOCKED_REASONS:
            return False

        return True
