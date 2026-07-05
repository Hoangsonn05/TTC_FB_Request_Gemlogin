# -*- coding: utf-8 -*-
"""Test BrowserContextRequestAdapter — ensure/probe fail-closed khi page đóng."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from action_executors.browser_request_adapter import BrowserContextRequestAdapter


class MockPageOpen:
    """Mock page đang mở và hoạt động bình thường."""
    evaluate_calls = []

    def is_closed(self):
        return False

    def evaluate(self, script, *args):
        self.evaluate_calls.append(script)
        if "hasFetch" in script:
            return {
                "ok": True,
                "href": "https://www.facebook.com/",
                "origin": "https://www.facebook.com",
                "readyState": "complete",
                "hasFetch": True,
                "hasAbortController": True,
            }
        return {"ok": True}


class MockPageClosed:
    """Mock page đã bị đóng."""
    def is_closed(self):
        return True


class MockPageNone:
    pass


class TestBrowserContextRequestAdapter:
    def setup_method(self):
        self.adapter = BrowserContextRequestAdapter(timeout_ms=10000)

    def test_ensure_page_ready_none(self):
        ok, reason = self.adapter.ensure_page_ready(None)
        assert ok is False
        assert "None" in reason

    def test_ensure_page_ready_closed(self):
        ok, reason = self.adapter.ensure_page_ready(MockPageClosed())
        assert ok is False
        assert "closed" in reason.lower()

    def test_ensure_page_ready_open(self):
        ok, reason = self.adapter.ensure_page_ready(MockPageOpen())
        assert ok is True
        assert reason == ""

    def test_probe_context_open_page(self):
        page = MockPageOpen()
        result = self.adapter.probe_context(page)
        assert result.get("ok") is True
        assert result.get("hasFetch") is True
        assert result.get("href") == "https://www.facebook.com/"

    def test_run_configured_fetch_calls_evaluate(self):
        page = MockPageOpen()
        page.evaluate_calls = []

        class _Page:
            def is_closed(self): return False
            def evaluate(self, script, arg):
                return {
                    "ok": True,
                    "status": 200,
                    "statusText": "OK",
                    "url": arg["requestSpec"]["url"],
                    "text": '{"success": true, "verified": true}',
                }

        spec = {"url": "https://example.com/provider", "method": "POST", "body": {}}
        result = self.adapter.run_configured_fetch(_Page(), spec)
        assert result["ok"] is True
        assert result["status"] == 200
        assert "success" in result["text"]

    def test_timeout_ms_default(self):
        adapter = BrowserContextRequestAdapter()
        assert adapter.timeout_ms == 15000

    def test_timeout_ms_custom(self):
        adapter = BrowserContextRequestAdapter(timeout_ms=5000)
        assert adapter.timeout_ms == 5000


def run_tests():
    t = TestBrowserContextRequestAdapter()
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
    print(f"\nBrowserContextRequestAdapter: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
