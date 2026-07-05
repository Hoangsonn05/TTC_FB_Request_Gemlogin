# -*- coding: utf-8 -*-
"""JobActionMapper — Chuẩn hóa job TTC thành NormalizedAction trung lập.

Mapper chỉ normalize dữ liệu. Không request network, không chứa endpoint/payload
nội bộ, không phụ thuộc Facebook UI.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class NormalizedAction:
    job_id: str
    action_group: str
    target_url: str = ""
    target_id: str = ""
    reaction_type: str = ""
    comment_text: str = ""
    raw_job: dict[str, Any] | None = None


class JobActionMapper:
    """Chuyển đổi job dict/object từ TTC thành NormalizedAction.

    Quy tắc ưu tiên field theo thứ tự ưu tiên giảm dần, tương thích
    với cả schema TTC mới lẫn schema legacy.
    """

    def normalize(self, job: Any) -> NormalizedAction:
        raw: dict[str, Any]
        if isinstance(job, dict):
            raw = job
        else:
            raw = getattr(job, "raw_data", None) or {}
            if not isinstance(raw, dict):
                raw = {}

        action_group = str(
            raw.get("action_group")
            or raw.get("job_type")
            or raw.get("type")
            or raw.get("loai")
            or ""
        ).lower()

        target_url = str(
            raw.get("link")
            or raw.get("url")
            or raw.get("target_url")
            or ""
        )

        target_id = str(
            raw.get("idpost")
            or raw.get("object_id")
            or raw.get("id")
            or raw.get("target_id")
            or ""
        )

        job_id = str(
            raw.get("job_id")
            or (getattr(job, "buff_id", None) if not isinstance(job, dict) else None)
            or raw.get("id")
            or target_id
            or ""
        )

        reaction_type = str(
            raw.get("reaction_type")
            or raw.get("camxuc")
            or raw.get("reaction")
            or ""
        )

        comment_text = str(
            raw.get("comment_text")
            or raw.get("comment")
            or raw.get("noidung")
            or ""
        )

        return NormalizedAction(
            job_id=job_id,
            action_group=action_group,
            target_url=target_url,
            target_id=target_id,
            reaction_type=reaction_type,
            comment_text=comment_text,
            raw_job=raw,
        )
