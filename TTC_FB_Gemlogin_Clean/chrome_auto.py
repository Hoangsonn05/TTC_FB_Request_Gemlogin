# -*- coding: utf-8 -*-
"""Lean browser/GemLogin adapter used by ttc_runtime.

Old Facebook UI action methods were removed from this baseline. Action execution
is now delegated to action_executors package so the browser layer only handles:
- GemLogin/local Chromium startup
- CDP connection
- page selection
- resource policy
- navigation
- cookie bootstrap when explicitly configured
- cleanup
"""

import threading
import time
from dataclasses import dataclass

from gemlogin_client import GemLoginClient
from playwright.sync_api import sync_playwright
from resource_policy import ResourcePolicy, apply_resource_policy


@dataclass
class NavigationResult:
    ok: bool
    reason: str
    requested_url: str
    final_url: str = ""
    error: str = ""
    retryable: bool = False
    navigation_id: int = 0
    caller: str = ""
    thread_id: int = 0


class AUTO_CHROME:
    def __init__(
        self,
        headless=False,
        mode="local_chrome",
        profile_id=None,
        gemlogin_url="http://localhost:1010",
        use_cookie=True,
        auto_close_profile=True,
        resource_policy=None,
    ):
        self.headless = bool(headless)
        self.mode = mode
        self.profile_id = profile_id
        self.gemlogin_url = gemlogin_url
        self.use_cookie = use_cookie
        self.auto_close_profile = auto_close_profile
        self.resource_policy = resource_policy or ResourcePolicy()

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._gemlogin_client = None
        self.last_action_error = ""
        self._navigation_lock = threading.Lock()
        self._navigation_seq = 0
        self.navigation_state = "IDLE"
        self.last_navigation_result = None

    def setup_driver(self):
        self.playwright = sync_playwright().start()
        if self.mode == "gemlogin":
            self._setup_gemlogin()
        else:
            self._setup_local_chrome()
        apply_resource_policy(self.context, self.resource_policy)

    def _setup_local_chrome(self):
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        self.context = self.browser.new_context(no_viewport=True)
        self.page = self.context.new_page()

    def _setup_gemlogin(self):
        if not self.profile_id:
            raise ValueError("[GemLogin] mode gemlogin requires profile_id.")
        self._gemlogin_client = GemLoginClient(base_url=self.gemlogin_url)
        debug_address = self._gemlogin_client.start_profile(self.profile_id, headless=self.headless)
        try:
            self.browser = self.playwright.chromium.connect_over_cdp(f"http://{debug_address}")
        except Exception as exc:
            raise RuntimeError(f"[GemLogin] connect_over_cdp failed for {debug_address}: {exc}")
        if not self.browser.contexts:
            raise RuntimeError("[GemLogin] browser.contexts is empty after CDP connect.")
        self.context = self.browser.contexts[0]
        self.page = self._pick_best_page()

    def _pick_best_page(self):
        pages = self.context.pages if self.context else []
        for page in pages:
            try:
                if "facebook.com" in str(page.url):
                    return page
            except Exception:
                pass
        return pages[0] if pages else self.context.new_page()

    def _classify_navigation_error(self, exc: Exception) -> tuple[str, bool]:
        text = str(exc or "").casefold()
        if "interrupted by another navigation" in text:
            return "NAVIGATION_CONFLICT", True
        if "timeout" in text:
            return "NAVIGATION_TIMEOUT", True
        if "target page" in text or "target closed" in text or "browser has been closed" in text:
            return "BROWSER_CLOSED", True
        if "net::err_aborted" in text:
            return "NAVIGATION_ABORTED", True
        return "UNKNOWN_NAVIGATION_ERROR", False

    def _interruptible_wait(self, wait_ms: int, stop_event=None):
        deadline = time.monotonic() + max(0, int(wait_ms)) / 1000.0
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                return False
            step_ms = min(250, max(1, int((deadline - time.monotonic()) * 1000)))
            try:
                self.page.wait_for_timeout(step_ms)
            except Exception:
                time.sleep(step_ms / 1000.0)
        return True

    def navigate_to_target(self, url, target_type="", stop_event=None, timeout_ms=60000, caller="runtime", settle_ms=5000):
        requested_url = str(url or "")
        thread_id = threading.get_ident()
        if stop_event is not None and stop_event.is_set():
            return NavigationResult(False, "STOP_REQUESTED", requested_url, retryable=False, caller=caller, thread_id=thread_id)
        if self.page is None:
            return NavigationResult(False, "BROWSER_CLOSED", requested_url, retryable=True, caller=caller, thread_id=thread_id)
        if not self._navigation_lock.acquire(blocking=False):
            result = NavigationResult(False, "NAVIGATION_CONFLICT", requested_url, final_url=str(getattr(self.page, "url", "") or ""), error="navigation owner is busy", retryable=True, caller=caller, thread_id=thread_id)
            self.last_navigation_result = result
            return result
        try:
            self._navigation_seq += 1
            nav_id = self._navigation_seq
            self.navigation_state = "NAVIGATING"
            try:
                self.page.goto(requested_url, timeout=max(1000, int(timeout_ms)), wait_until="domcontentloaded")
                if stop_event is not None and stop_event.is_set():
                    result = NavigationResult(False, "STOP_REQUESTED", requested_url, final_url=str(getattr(self.page, "url", "") or ""), retryable=False, navigation_id=nav_id, caller=caller, thread_id=thread_id)
                else:
                    self.navigation_state = "SETTLING"
                    if not self._interruptible_wait(settle_ms, stop_event=stop_event):
                        result = NavigationResult(False, "STOP_REQUESTED", requested_url, final_url=str(getattr(self.page, "url", "") or ""), retryable=False, navigation_id=nav_id, caller=caller, thread_id=thread_id)
                    else:
                        result = NavigationResult(True, "OK", requested_url, final_url=str(getattr(self.page, "url", "") or ""), retryable=False, navigation_id=nav_id, caller=caller, thread_id=thread_id)
            except Exception as exc:
                reason, retryable = self._classify_navigation_error(exc)
                result = NavigationResult(False, reason, requested_url, final_url=str(getattr(self.page, "url", "") or ""), error=str(exc), retryable=retryable, navigation_id=nav_id, caller=caller, thread_id=thread_id)
            self.last_navigation_result = result
            return result
        finally:
            self.navigation_state = "IDLE"
            self._navigation_lock.release()

    def chrome_login_cookie(self, cookie_string):
        if not self.page:
            return
        if not self.use_cookie or not cookie_string or not str(cookie_string).strip():
            print("[Browser] Cookie disabled/empty. Using existing profile session.")
            return
        cookies = []
        for item in str(cookie_string).split(";"):
            item = item.strip()
            if not item or "=" not in item:
                continue
            name, value = item.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".facebook.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
            })
        if cookies:
            self.context.add_cookies(cookies)

    def close(self):
        try:
            if self.browser:
                self.browser.close()
        except Exception as exc:
            print(f"[Browser] browser.close failed: {exc}")
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception as exc:
            print(f"[Browser] playwright.stop failed: {exc}")
        if self.mode == "gemlogin" and self.auto_close_profile and self._gemlogin_client and self.profile_id:
            try:
                self._gemlogin_client.close_profile(self.profile_id)
            except Exception as exc:
                print(f"[GemLogin] close_profile failed: {exc}")
