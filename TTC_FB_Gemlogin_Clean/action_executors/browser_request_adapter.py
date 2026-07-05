# -*- coding: utf-8 -*-
"""BrowserContextRequestAdapter — Chạy fetch từ bên trong browser context của profile GemLogin.

Không dùng requests.Session.
Không truyền cookie thủ công.
Không hard-code header trình duyệt.
Không override User-Agent.
credentials: "include" để browser tự dùng session/cookie của profile.
"""

from typing import Any


class BrowserContextRequestAdapter:
    """Adapter chạy fetch bên trong Playwright page context.

    Adapter này chỉ là cơ chế browser-context fetch, không chứa:
    - Endpoint Facebook nội bộ
    - Payload Facebook
    - Token bảo mật
    - Cookie thủ công
    - User-Agent cụ thể

    Tất cả headers, cookies, credentials được browser tự quản lý qua session
    của profile GemLogin đã attach qua CDP.
    """

    def __init__(self, timeout_ms: int = 15000):
        self.timeout_ms = int(timeout_ms or 15000)

    def ensure_page_ready(self, page: Any) -> tuple[bool, str]:
        """Kiểm tra page có sẵn sàng để evaluate không."""
        if page is None:
            return False, "Playwright page is None"

        try:
            if page.is_closed():
                return False, "Playwright page is closed"
        except Exception as exc:
            return False, f"Cannot inspect Playwright page: {exc}"

        return True, ""

    def probe_context(self, page: Any) -> dict[str, Any]:
        """Probe nhẹ để xác nhận JavaScript context có hoạt động không."""
        return page.evaluate(
            """
            () => {
                return {
                    ok: true,
                    href: location.href,
                    origin: location.origin,
                    readyState: document.readyState,
                    hasFetch: typeof fetch === "function",
                    hasAbortController: typeof AbortController === "function"
                };
            }
            """
        )

    def run_configured_fetch(self, page: Any, request_spec: dict[str, Any]) -> dict[str, Any]:
        """Chạy fetch trong browser context.

        request_spec chỉ được lấy từ provider/config hợp lệ của dự án.
        Không hard-code endpoint nội bộ ở đây.
        Không inject token bảo mật ở đây.
        Không tự chế header trình duyệt ở đây.

        request_spec schema:
            url      (str)  — URL endpoint do provider cung cấp
            method   (str)  — HTTP method, mặc định "POST"
            headers  (dict) — Headers bổ sung, mặc định rỗng
            body     (Any)  — Body object, sẽ được JSON.stringify trong browser

        Trả về dict:
            ok         (bool) — response.ok
            status     (int)  — HTTP status code
            statusText (str)
            url        (str)  — response.url (sau redirect)
            text       (str)  — response body text
        """
        return page.evaluate(
            """
            async ({ requestSpec, timeoutMs }) => {
                const controller = new AbortController();
                const timeout = setTimeout(() => controller.abort(), timeoutMs);

                try {
                    const url = requestSpec.url;
                    const method = requestSpec.method || "POST";
                    const body = requestSpec.body || null;

                    const headers = Object.assign(
                        {"content-type": "application/json"},
                        requestSpec.headers || {}
                    );

                    const response = await fetch(url, {
                        method,
                        headers,
                        body: body == null ? null : JSON.stringify(body),
                        credentials: "include",
                        signal: controller.signal
                    });

                    const text = await response.text();

                    return {
                        ok: response.ok,
                        status: response.status,
                        statusText: response.statusText,
                        url: response.url,
                        text
                    };
                } catch (error) {
                    return {
                        ok: false,
                        status: 0,
                        statusText: String(error && error.name || "FETCH_ERROR"),
                        url: requestSpec.url || "",
                        text: String(error && error.message || error)
                    };
                } finally {
                    clearTimeout(timeout);
                }
            }
            """,
            {
                "requestSpec": request_spec,
                "timeoutMs": self.timeout_ms,
            }
        )
