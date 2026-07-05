# -*- coding: utf-8 -*-
"""Test ClaimGate — can_claim() chặn đúng điều kiện."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.claim_gate import ClaimGate


def _make_result(success, verified, reason=""):
    class _R:
        pass
    r = _R()
    r.success = success
    r.verified = verified
    r.reason = reason
    return r


class TestClaimGate:
    def setup_method(self):
        self.gate = ClaimGate()

    def test_can_claim_success_verified(self):
        r = _make_result(True, True, "ACTION_VERIFIED")
        assert self.gate.can_claim(r) is True

    def test_blocked_success_not_verified(self):
        r = _make_result(True, False, "ACTION_NOT_VERIFIED")
        assert self.gate.can_claim(r) is False

    def test_blocked_not_success_verified(self):
        r = _make_result(False, True, "SOME_REASON")
        assert self.gate.can_claim(r) is False

    def test_blocked_both_false(self):
        r = _make_result(False, False, "")
        assert self.gate.can_claim(r) is False

    def test_blocked_none_result(self):
        assert self.gate.can_claim(None) is False

    def test_blocked_reason_unsupported(self):
        r = _make_result(True, True, "ACTION_EXECUTOR_UNSUPPORTED")
        assert self.gate.can_claim(r) is False

    def test_blocked_reason_dry_run(self):
        r = _make_result(True, True, "DRY_RUN_NOT_CLAIMABLE")
        assert self.gate.can_claim(r) is False

    def test_blocked_reason_not_configured(self):
        r = _make_result(True, True, "PAGE_CONTEXT_ACTION_NOT_CONFIGURED")
        assert self.gate.can_claim(r) is False

    def test_blocked_reason_action_not_verified(self):
        r = _make_result(True, True, "ACTION_NOT_VERIFIED")
        assert self.gate.can_claim(r) is False

    def test_blocked_reason_browser_context_unavailable(self):
        r = _make_result(True, True, "BROWSER_CONTEXT_UNAVAILABLE")
        assert self.gate.can_claim(r) is False

    def test_blocked_reason_page_context_failed(self):
        r = _make_result(True, True, "PAGE_CONTEXT_ACTION_FAILED")
        assert self.gate.can_claim(r) is False

    def test_blocked_reason_login_required(self):
        r = _make_result(True, True, "LOGIN_REQUIRED")
        assert self.gate.can_claim(r) is False

    def test_blocked_reason_checkpoint(self):
        r = _make_result(True, True, "CHECKPOINT_OR_LOCKED")
        assert self.gate.can_claim(r) is False

    def test_can_claim_custom_valid_reason(self):
        r = _make_result(True, True, "PROVIDER_CONFIRMED_OK")
        assert self.gate.can_claim(r) is True


def run_tests():
    t = TestClaimGate()
    tests = [m for m in dir(t) if m.startswith("test_")]
    passed = 0
    failed = 0
    for name in tests:
        t.setup_method()
        try:
            getattr(t, name)()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
    print(f"\nClaimGate: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
