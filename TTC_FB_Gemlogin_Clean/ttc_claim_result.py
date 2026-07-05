# -*- coding: utf-8 -*-
from dataclasses import dataclass


@dataclass
class TTCClaimResult:
    success: bool
    reason: str
    message: str
    earned_coin: int = 0
    balance: int | None = None
    http_status: int | None = None
    retryable: bool = False
    endpoint_key: str = ""
    evidence: str = ""
    response_kind: str = ""
    response_keys: tuple[str, ...] = ()
    raw_summary: str = ""

    def to_dict(self):
        return {
            "success": self.success,
            "reason": self.reason,
            "message": self.message,
            "earned_coin": self.earned_coin,
            "balance": self.balance,
            "http_status": self.http_status,
            "retryable": self.retryable,
            "endpoint_key": self.endpoint_key,
            "evidence": self.evidence,
            "response_kind": self.response_kind,
            "response_keys": self.response_keys,
            "raw_summary": self.raw_summary,
        }
