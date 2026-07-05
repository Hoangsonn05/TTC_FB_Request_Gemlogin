# -*- coding: utf-8 -*-
from .browser_context import BrowserContextExecutor
from .dry_run import DryRunActionExecutor
from .facebook_graphql_context import FacebookGraphQLContextExecutor
from .unsupported import UnsupportedActionExecutor

_EXECUTOR_CLASSES = {
    UnsupportedActionExecutor.name: UnsupportedActionExecutor,
    DryRunActionExecutor.name: DryRunActionExecutor,
    BrowserContextExecutor.name: BrowserContextExecutor,
    FacebookGraphQLContextExecutor.name: FacebookGraphQLContextExecutor,
}


def get_action_executor(name: str | None):
    key = str(name or "unsupported").strip().lower()
    executor_cls = _EXECUTOR_CLASSES.get(key, UnsupportedActionExecutor)
    return executor_cls()


def available_action_executors():
    return sorted(_EXECUTOR_CLASSES.keys())
