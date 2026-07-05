# -*- coding: utf-8 -*-
"""Helpers for building FacebookActionResult consistently."""

from typing import Any

from facebook_action_result import FacebookActionResult


def _job_raw(job: Any) -> dict:
    raw = getattr(job, "raw_data", None)
    if isinstance(raw, dict):
        return raw
    if isinstance(job, dict):
        return job
    return {}


def get_action_type(job: Any, context: Any = None) -> str:
    if context is not None and getattr(context, "action_group", ""):
        return str(context.action_group)
    raw = _job_raw(job)
    return str(raw.get("action_group") or raw.get("type") or raw.get("job_type") or raw.get("loai") or "")


def get_target_type(job: Any, context: Any = None) -> str:
    if context is not None and getattr(context, "target_type", ""):
        return str(context.target_type)
    raw = _job_raw(job)
    return str(raw.get("target_type") or raw.get("object_type") or "")


def get_requested_reaction(job: Any) -> str:
    raw = _job_raw(job)
    return str(raw.get("reaction_type") or raw.get("camxuc") or raw.get("reaction") or "")


def get_final_url(page: Any) -> str:
    try:
        return str(getattr(page, "url", "") or "")
    except Exception:
        return ""


def make_failed_result(job: Any, reason: str, evidence: str = "", page: Any = None, context: Any = None, strategy_id: str = ""):
    return FacebookActionResult(
        success=False,
        verified=False,
        clicked=False,
        action_type=get_action_type(job, context),
        target_type=get_target_type(job, context),
        requested_reaction=get_requested_reaction(job),
        reason=str(reason or "ACTION_FAILED"),
        evidence=str(evidence or ""),
        final_url=get_final_url(page),
        strategy_id=str(strategy_id or ""),
    )


def make_success_result(job: Any, reason: str = "ACTION_VERIFIED", evidence: str = "", page: Any = None, context: Any = None, strategy_id: str = ""):
    return FacebookActionResult(
        success=True,
        verified=True,
        clicked=False,
        action_type=get_action_type(job, context),
        target_type=get_target_type(job, context),
        requested_reaction=get_requested_reaction(job),
        reason=str(reason or "ACTION_VERIFIED"),
        evidence=str(evidence or ""),
        final_url=get_final_url(page),
        strategy_id=str(strategy_id or ""),
    )
