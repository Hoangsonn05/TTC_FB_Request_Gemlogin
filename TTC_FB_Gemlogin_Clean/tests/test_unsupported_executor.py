from action_executors import ActionContext, get_action_executor


class Job:
    raw_data = {"reaction_type": "LIKE"}


class Page:
    url = "https://facebook.com/test"


def test_unsupported_is_not_claimable():
    result = get_action_executor("unsupported").execute(
        Job(), Page(), ActionContext(action_group="reaction", target_type="STANDARD_POST")
    )
    assert result.success is False
    assert result.verified is False
    assert result.reason == "ACTION_EXECUTOR_UNSUPPORTED"
