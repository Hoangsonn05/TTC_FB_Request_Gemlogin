# -*- coding: utf-8 -*-
"""Base contract for Facebook action executors.

Executors receive the Playwright page that is already attached to the GemLogin
profile through CDP. This package must not use an external HTTP client for
Facebook actions; the runtime claims TTC only when the returned result is both
success=True and verified=True.
"""

from dataclasses import dataclass
from typing import Any

from facebook_action_result import FacebookActionResult


@dataclass
class ActionContext:
    worker_id: str = ""
    profile_id: str = ""
    uid: str = ""
    thread_name: str = ""
    action_group: str = ""
    target_type: str = ""
    link: str = ""
    config: dict[str, Any] | None = None
    logger: Any = None


class BaseActionExecutor:
    name = "base"

    def supports(self, job: Any) -> bool:
        return True

    def execute(self, job: Any, page: Any, context: ActionContext) -> FacebookActionResult:
        raise NotImplementedError

    def verify(self, job: Any, page: Any, context: ActionContext) -> FacebookActionResult:
        raise NotImplementedError
