# -*- coding: utf-8 -*-
import requests


class GemLoginClient:
    """
    Client for GemLogin local API profile lifecycle.
    """

    def __init__(self, base_url="http://localhost:1010"):
        self.base_url = base_url.rstrip("/")

    def start_profile(self, profile_id, headless=False):
        """
        Start a GemLogin profile và trả về remote_debugging_address.

        Nếu headless=True mà API không start được hoặc không trả debug address
        thì raise lỗi rõ ràng — KHÔNG fallback sang visible mode.
        """
        url = f"{self.base_url}/api/profiles/start/{profile_id}"
        params = {"addination_args": "--headless=new"} if headless else None
        print(f"[GemLogin] start_profile profile_id={profile_id} headless={bool(headless)}")
        if headless:
            print(f"[GemLogin] headless requested — params={params}")

        try:
            res = requests.get(url, params=params, timeout=60)
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                f"[GemLogin] Cannot connect to {self.base_url}.\n"
                "  -> Check that GemLogin is open and Local API is enabled on port 1010."
            )

        if res.status_code != 200:
            if headless:
                raise RuntimeError(
                    f"[GemLogin] headless start failed; visible fallback disabled.\n"
                    f"  -> HTTP {res.status_code}: {res.text[:300]}"
                )
            raise RuntimeError(
                f"[GemLogin] API returned HTTP {res.status_code}.\n"
                f"  -> Response: {res.text[:300]}"
            )

        try:
            data = res.json()
        except Exception:
            raise RuntimeError(f"[GemLogin] Response is not valid JSON: {res.text[:300]}")

        if not data.get("success"):
            msg = data.get("message", str(data))
            if headless:
                raise RuntimeError(
                    f"[GemLogin] headless start failed; visible fallback disabled.\n"
                    f"  -> GemLogin API error: {msg}"
                )
            raise RuntimeError(
                f"[GemLogin] start_profile failed: {msg}\n"
                "  -> If the profile is already open, try closing it and starting again."
            )

        profile_data = data.get("data", {})
        debug_address = profile_data.get("remote_debugging_address")

        if not debug_address:
            if headless:
                raise RuntimeError(
                    "[GemLogin] headless start failed; visible fallback disabled.\n"
                    "  -> remote_debugging_address not found. GemLogin may not support --headless=new.\n"
                    f"  -> Full response: {data}"
                )
            raise RuntimeError(
                "[GemLogin] remote_debugging_address not found in API response.\n"
                f"  -> Full response: {data}"
            )

        print(f"[GemLogin] Profile started. Debug address: {debug_address}")
        return debug_address

    def close_profile(self, profile_id):
        """
        Close a GemLogin profile. Returns True on success, False on failure.
        """
        url = f"{self.base_url}/api/profiles/close/{profile_id}"
        print(f"[GemLogin] Closing profile: {profile_id}")

        try:
            res = requests.get(url, timeout=30)
        except Exception as e:
            print(f"[GemLogin] Close profile connection error: {e}")
            return False

        if res.status_code != 200:
            print(f"[GemLogin] Close profile HTTP {res.status_code}: {res.text[:200]}")
            return False

        try:
            data = res.json()
            ok = bool(data.get("success"))
            if ok:
                print(f"[GemLogin] Profile {profile_id} closed.")
            else:
                print(f"[GemLogin] Close profile returned error: {data.get('message', data)}")
            return ok
        except Exception:
            return False
