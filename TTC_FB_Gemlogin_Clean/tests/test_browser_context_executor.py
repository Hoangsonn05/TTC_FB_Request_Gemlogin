from action_executors import ActionContext, get_action_executor


class Job:
    raw_data = {"reaction_type": "LIKE"}


class Page:
    url = "https://facebook.com/test"

    def is_closed(self):
        return False

    def evaluate(self, script, args=None):
        # Trả probe response hợp lệ để pass qua probe check
        return {
            "ok": True,
            "href": self.url,
            "origin": "https://facebook.com",
            "readyState": "complete",
            "hasFetch": True,
            "hasAbortController": True,
        }


def test_browser_context_without_provider_fails_closed():
    cfg = {"action_executor": {"name": "browser_context", "provider_enabled": False}}
    result = get_action_executor("browser_context").execute(
        Job(), Page(), ActionContext(action_group="reaction", target_type="STANDARD_POST", config=cfg)
    )
    assert result.success is False
    assert result.verified is False
    assert result.reason == "PAGE_CONTEXT_ACTION_NOT_CONFIGURED"


def test_browser_context_page_none():
    result = get_action_executor("browser_context").execute(
        Job(), None, ActionContext(action_group="reaction", target_type="STANDARD_POST", config={})
    )
    assert result.reason == "BROWSER_CONTEXT_UNAVAILABLE"
