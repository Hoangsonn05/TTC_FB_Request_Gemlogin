# -*- coding: utf-8 -*-
from .base import BaseActionExecutor
from .result_utils import make_failed_result


class UnsupportedActionExecutor(BaseActionExecutor):
    name = "unsupported"

    def execute(self, job, page, context):
        return make_failed_result(
            job,
            "ACTION_EXECUTOR_UNSUPPORTED",
            "No enabled action executor is configured. TTC claim is blocked until an action is verified.",
            page=page,
            context=context,
            strategy_id=self.name,
        )

    def verify(self, job, page, context):
        return self.execute(job, page, context)
