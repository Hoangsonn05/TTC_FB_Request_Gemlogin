# -*- coding: utf-8 -*-
CLAIM_RETRYABLE_REASONS = {
    "NOT_OBSERVED_YET",
    "HTTP_ERROR",
    "NETWORK_TIMEOUT",
    "RATE_LIMITED",
    "INVALID_RESPONSE",
}


def should_retry_claim(claim_result: dict, attempt: int, max_attempts: int, stop_event=None) -> bool:
    if stop_event is not None and stop_event.is_set():
        return False
    if attempt >= max_attempts:
        return False
    reason = str((claim_result or {}).get("reason") or "")
    return bool((claim_result or {}).get("retryable")) and reason in CLAIM_RETRYABLE_REASONS
