# TTC FB GemLogin — Clean Baseline

## Nội dung đã làm sạch

Đã loại bỏ khỏi bản clean:

- `.git/`, `__pycache__/`, `.pyc`, file history runtime.
- `config.json` chứa token/cookie/local credential. Chỉ giữ `config.example.json`.
- `api_bumx.py`: monolith CLI cũ, trùng trách nhiệm với `ttc_api.py` + `ttc_runtime.py`.
- `job_dispatcher.py`: dispatcher cũ phụ thuộc `api_bumx.py`.
- `facebook_post_layout_1.py`, `facebook_post_layout_2.py`, `facebook_reaction_router.py`, `facebook_reel_engine.py`, `test_facebook_router.py`: logic click/UI Facebook cũ.

## Module còn giữ

- GUI: `ttc_gui_pyside6.py`, `main_window.py`, `gui_worker.py`, panel/theme files.
- TTC API/runtime: `ttc_api.py`, `ttc_runtime.py`, `ttc_dispatcher.py`, `ttc_job_types.py`, `ttc_claim_result.py`.
- Queue/history: `job_queue.py`, `interaction_history.py`, `job_history.py`.
- Browser/GemLogin: `gemlogin_client.py`, `chrome_auto.py`, `resource_policy.py`.
- Facebook state/guard/result: `facebook_target_state.py`, `facebook_guard.py`, `facebook_action_result.py`.
- Executor seam: `action_executors package`.

## Trạng thái hiện tại

Bản clean giữ nguyên khung GUI + TTC + GemLogin + Playwright navigation.
Action Facebook được đưa qua `action_executors package`. Executor mặc định là `unsupported`, nên runtime sẽ không claim job nếu chưa có executor hợp lệ xác minh thành công.

## Cách chạy

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
copy config.example.json config.json
python ttc_gui_pyside6.py
```

## Lưu ý bảo mật

Không commit `config.json`, token, cookie, `interaction_history.json` hoặc file `.pyc`.


## Integration update

- Converted `action_executors.py` into `action_executors/` package.
- Added `browser_context` executor skeleton that fail-closes without a permitted provider.
- Added tests for executor registry, config migration and claim gate.
