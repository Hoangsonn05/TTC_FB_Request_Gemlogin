# TTC FB GemLogin — Facebook GraphQL Context Executor

Tool TTC/GemLogin thực hiện Facebook action (reaction/comment) bằng GraphQL request phát ra từ **chính browser context** của profile GemLogin đang chạy qua Playwright CDP.

## Workflow

```text
[GemLogin] start_profile profile_id=... headless=True
[GemLogin] Profile started. Debug address: ...
[Browser] CDP connected
[TTC] authenticate OK
[TTC] configure UID OK
[TTC] get job OK
[Browser] navigate target OK
[FacebookAction] executor=facebook_graphql_context origin=https://www.facebook.com action=reaction
[FacebookAction] GraphQL status=200 verified=True
[TTC] claim_reward OK
```

Nếu GraphQL fail hoặc token thiếu:

```text
[FacebookAction] verified=False reason=FACEBOOK_TOKEN_EXTRACTION_FAILED
[TTC] Không nhận xu vì thao tác Facebook chưa được xác minh.
```

## Kiến trúc

```text
GemLogin profile → Playwright CDP connect → TTC API login/get job
→ navigate target Facebook trong chính profile
→ FacebookGraphQLContextExecutor.execute(job, page, context)
    → extract tokens từ DOM (page.evaluate, không dùng HTTP client ngoài)
    → build GraphQL payload trong browser context
    → fetch("/api/graphql/", {credentials:"include"}) từ chính page
    → parse GraphQL response → FacebookActionResult
→ is_action_claimable(result) → ClaimGate
→ TTCClient.claim_reward() CHỈ KHI success=True AND verified=True
```

## Action Executor

| Name | Mô tả |
|------|-------|
| `facebook_graphql_context` | **Default**. Thực hiện reaction/comment bằng GraphQL fetch từ browser context của profile. Không cần provider URL ngoài. |
| `dry_run` | Mô phỏng flow, `success=True` nhưng `verified=False`, không claim. |
| `unsupported` | Không action, không claim. |
| `browser_context` | Executor cũ (tương thích ngược), không còn dùng. |

### facebook_graphql_context — Cách hoạt động

- **Không** dùng `requests.Session` cho Facebook action.
- **Không** truyền cookie Facebook thủ công từ config.
- **Không** hard-code browser headers (User-Agent, sec-ch-ua, Accept-Language…).
- **Không** dùng provider URL ngoài.
- Token (`fb_dtsg`, `jazoest`, `lsd`, `feedback_id`) được extract từ DOM hiện tại qua `page.evaluate()`.
- GraphQL request build và phát ra trong browser context bằng `fetch()` với `credentials: "include"` — browser tự mang session/cookie của profile GemLogin.
- **Fail-closed**: chỉ trả `success=True, verified=True` khi GraphQL response không có `errors` và có `data`.

### Reaction types được hỗ trợ

| Reaction | ID Facebook |
|----------|-------------|
| `LIKE`   | 1635855486666999 |
| `LOVE`   | 1678524932434102 |
| `CARE`   | 613557422527858  |
| `HAHA`   | 115940658764963  |
| `WOW`    | 478547315650144  |
| `SAD`    | 908563459236466  |
| `ANGRY`  | 444813342392137  |

### Action groups được hỗ trợ

| Action group | Loại |
|---|---|
| `ttc_like_post_vip_cheo`, `ttc_like_post_vip_re` | Reaction (LIKE mặc định) |
| `ttc_reaction_vip_cheo`, `ttc_reaction_vip_re` | Reaction (type từ job) |
| `ttc_comment` | Comment |
| `ttc_follow`, `ttc_like_page` | **Chưa triển khai** — fail-closed, không claim |

### Cấu hình executor

```json
{
  "facebook_action_executor": "facebook_graphql_context",
  "action_executor": {
    "name": "facebook_graphql_context",
    "verify_after_action": true,
    "fail_closed": true,
    "timeout_ms": 15000,
    "max_action_retry": 0
  }
}
```

> **Không còn** `provider_enabled` và `provider_url` trong schema. Config cũ có các field này sẽ được tự động ignore khi load.

## Kiến trúc kỹ thuật

```text
action_executors/
├── facebook_graphql_context.py — Executor chính: GraphQL fetch từ browser context
├── job_action_mapper.py        — normalize job TTC → NormalizedAction (trung lập)
├── browser_request_adapter.py  — fetch trong page.evaluate, credentials: "include"
├── result_parser.py            — parse response → FacebookActionResult (fail-closed)
├── browser_context.py          — BrowserContextExecutor (cũ, tương thích ngược)
├── dry_run.py                  — executor mô phỏng, không claim
├── unsupported.py              — executor mặc định an toàn, không claim
├── registry.py                 — get_action_executor(name) factory
└── result_utils.py             — make_failed_result / make_success_result helpers

runtime/
├── claim_gate.py   — ClaimGate chặn claim nếu chưa verified
├── delay_policy.py — DelayPolicy linh hoạt theo scope/action_group
├── retry_policy.py — should_retry_claim()
└── risk_state.py   — RiskState cooldown
```

## Resource Blocking

```json
{
  "resource_blocking_enabled": true,
  "block_images": true,
  "block_media": true,
  "block_fonts": true,
  "block_stylesheets": false
}
```

Không chặn `document`, `script`, `xhr` hoặc `fetch`.

## Kiểm tra

```bash
python -m compileall .
python -m pytest tests -q
```

## Ghi chú an toàn

- Không import `requests_fb.py` hay dùng bất kỳ logic nào từ `TTCMMOFB/requests_fb.py`.
- Không dùng `requests.Session` cho Facebook action.
- Không lưu token/cookie thật vào `config.example.json`.
- Không claim khi action chưa verified (`is_action_claimable()` là gate duy nhất).
- Không hard-code endpoint/payload Facebook ngoài browser context.
- Không dùng external API trung gian để bắn request.
- Không log cookie/fb_dtsg/lsd/jazoest ra log file.
