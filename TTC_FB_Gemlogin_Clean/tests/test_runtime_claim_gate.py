from facebook_action_result import FacebookActionResult
from ttc_runtime import _claim_verified_job


class DummyTTC:
    def __init__(self):
        self.called = False

    def claim_reward(self, raw):
        self.called = True
        return {"success": True, "reason": "CLAIM_SUCCESS"}


def test_claim_guard_blocks_unverified_action():
    ttc = DummyTTC()
    result = FacebookActionResult(True, False, False, "reaction", "STANDARD_POST")
    claim = _claim_verified_job(ttc, {"idpost": "1"}, result)
    assert ttc.called is False
    assert claim["success"] is False
    assert claim["reason"] == "CLAIM_GUARD_BLOCKED_UNVERIFIED_ACTION"


def test_claim_guard_allows_verified_action():
    ttc = DummyTTC()
    result = FacebookActionResult(True, True, False, "reaction", "STANDARD_POST")
    claim = _claim_verified_job(ttc, {"idpost": "1"}, result)
    assert ttc.called is True
    assert claim["success"] is True
