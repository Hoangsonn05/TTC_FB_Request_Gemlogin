from action_executors import ActionContext, get_action_executor
from facebook_action_result import is_action_claimable


class Job:
    raw_data = {"reaction_type": "LOVE"}


class Page:
    url = "https://facebook.com/test"


def test_dry_run_success_but_not_claimable():
    result = get_action_executor("dry_run").execute(
        Job(), Page(), ActionContext(action_group="reaction", target_type="STANDARD_POST")
    )
    assert result.success is True
    assert result.verified is False
    assert result.reason == "DRY_RUN_NOT_CLAIMABLE"
    assert is_action_claimable(result) is False
