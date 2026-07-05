# -*- coding: utf-8 -*-
from facebook_action_result import FacebookActionResult

from .base import BaseActionExecutor
from .result_utils import get_action_type, get_final_url, get_requested_reaction, get_target_type


class DryRunActionExecutor(BaseActionExecutor):
    name = "dry_run"

    def execute(self, job, page, context):
        return FacebookActionResult(
            success=True,
            verified=False,
            clicked=False,
            action_type=get_action_type(job, context),
            target_type=get_target_type(job, context),
            requested_reaction=get_requested_reaction(job),
            reason="DRY_RUN_NOT_CLAIMABLE",
            evidence="Dry-run reached the action stage but did not perform or verify the Facebook action.",
            final_url=get_final_url(page),
            strategy_id=self.name,
        )

    def verify(self, job, page, context):
        return self.execute(job, page, context)
