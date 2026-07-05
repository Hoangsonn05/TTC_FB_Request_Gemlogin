# -*- coding: utf-8 -*-
"""DelayPolicy — Chính sách delay linh hoạt theo scope và action_group.

Thay thế hàm pick_range cũ, tương thích ngược với config dạng flat key cũ
(reaction_min_delay_after_job, ...) và config dạng nested mới (delays.after_job...).
"""

import random
import time


class DelayPolicy:
    """Chọn và thực thi delay ngẫu nhiên theo scope.

    Config dạng mới (ưu tiên hơn):
        {
            "delays": {
                "after_job": {
                    "reaction": [30, 60],
                    "comment": [60, 120],
                    "follow": [45, 90],
                    "page_like": [45, 90]
                },
                "api_error": [20, 60],
                "no_job": [15, 45]
            }
        }

    Config dạng cũ (flat key) — vẫn được hỗ trợ qua from_flat_config():
        {
            "reaction_min_delay_after_job": 30,
            "reaction_max_delay_after_job": 45,
            ...
        }
    """

    def __init__(self, config: dict):
        self.config = config or {}

    @classmethod
    def from_flat_config(cls, cfg: dict) -> "DelayPolicy":
        """Tạo DelayPolicy từ config flat key kiểu cũ.

        Tương thích với DEFAULT_TTC_CONFIG trong ttc_runtime.py.
        """
        delays = {
            "after_job": {
                "reaction": [
                    int(cfg.get("reaction_min_delay_after_job", 30)),
                    int(cfg.get("reaction_max_delay_after_job", 45)),
                ],
                "comment": [
                    int(cfg.get("comment_min_delay_after_job", 60)),
                    int(cfg.get("comment_max_delay_after_job", 90)),
                ],
                "follow": [
                    int(cfg.get("follow_min_delay_after_job", 30)),
                    int(cfg.get("follow_max_delay_after_job", 45)),
                ],
                "page_like": [
                    int(cfg.get("page_like_min_delay_after_job", 30)),
                    int(cfg.get("page_like_max_delay_after_job", 45)),
                ],
            },
            "api_error": [
                int(cfg.get("api_error_retry_delay", 20)),
                int(cfg.get("api_error_retry_delay", 20)),
            ],
            "no_job": [
                int(cfg.get("wait_no_job_delay", 30)),
                int(cfg.get("wait_no_job_delay", 30)),
            ],
        }
        return cls({"delays": delays})

    def pick(self, scope: str, action_group: str = "") -> float:
        """Chọn giá trị delay float trong khoảng cấu hình.

        Args:
            scope: "after_job" | "api_error" | "no_job" hoặc key tùy chỉnh.
            action_group: "reaction" | "comment" | "follow" | "page_like" ...
                          Chỉ dùng khi scope là "after_job" và có nested config.

        Returns:
            Số giây float để sleep. Trả về 0.0 nếu không có config phù hợp.
        """
        delays = self.config.get("delays") or {}
        value = None

        scope_val = delays.get(scope)
        if isinstance(scope_val, dict) and action_group:
            value = scope_val.get(action_group)
        elif isinstance(scope_val, (list, int, float)):
            value = scope_val

        # Nếu scope_val là dict nhưng không có action_group → fallback sang default action
        if value is None and isinstance(scope_val, dict):
            # Thử lấy key đầu tiên nếu không khớp action_group
            value = None

        if isinstance(value, list) and len(value) >= 2:
            lo = float(value[0])
            hi = float(value[1])
            if lo > hi:
                lo, hi = hi, lo
            return random.uniform(lo, hi)

        if isinstance(value, (int, float)):
            return float(value)

        return 0.0

    def sleep(self, scope: str, action_group: str = "") -> float:
        """Sleep theo delay chọn được.

        Returns:
            Số giây đã sleep thực tế.
        """
        seconds = self.pick(scope, action_group)
        if seconds > 0:
            time.sleep(seconds)
        return seconds


# ── Backward-compatible helper ─────────────────────────────────────────────────
def pick_range(min_value, max_value, default_min=0, default_max=0):
    """Hàm cũ — giữ nguyên để không phá import hiện tại."""
    try:
        mn = int(min_value)
    except Exception:
        mn = int(default_min)
    try:
        mx = int(max_value)
    except Exception:
        mx = int(default_max)
    if mn > mx:
        mn, mx = mx, mn
    return random.randint(mn, mx)
