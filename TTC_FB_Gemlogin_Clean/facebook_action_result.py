# -*- coding: utf-8 -*-
from dataclasses import dataclass


@dataclass
class FacebookActionResult:
    success: bool
    verified: bool
    clicked: bool
    action_type: str
    target_type: str
    requested_reaction: str = ""
    active_reaction: str = ""
    reason: str = ""
    evidence: str = ""
    final_url: str = ""
    content_type: str = ""
    layout_type: str = ""
    strategy_id: str = ""

    def __bool__(self):
        return self.success is True and self.verified is True


def is_action_claimable(result) -> bool:
    return (
        isinstance(result, FacebookActionResult)
        and result.success is True
        and result.verified is True
    )


def bool_action_result(ok, action_type="reaction", target_type="STANDARD_POST", reason=""):
    if isinstance(ok, FacebookActionResult):
        return ok
    return FacebookActionResult(
        success=(ok is True),
        verified=(ok is True),
        clicked=(ok is True),
        action_type=action_type,
        target_type=target_type,
        reason=reason or ("OK" if ok is True else "ACTION_FAILED"),
    )
