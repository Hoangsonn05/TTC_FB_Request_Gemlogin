from action_executors import get_action_executor


def test_registry_known_executors():
    assert get_action_executor("unsupported").name == "unsupported"
    assert get_action_executor("dry_run").name == "dry_run"
    assert get_action_executor("browser_context").name == "browser_context"
    assert get_action_executor("facebook_graphql_context").name == "facebook_graphql_context"


def test_registry_unknown_fallback():
    assert get_action_executor("missing").name == "unsupported"


def test_registry_facebook_graphql_context_is_registered():
    from action_executors import available_action_executors
    executors = available_action_executors()
    assert "facebook_graphql_context" in executors
