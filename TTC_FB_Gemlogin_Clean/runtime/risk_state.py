# -*- coding: utf-8 -*-
import time
from dataclasses import dataclass, field


@dataclass
class RiskState:
    cooldown_until: dict[tuple[str, str], float] = field(default_factory=dict)

    def pause(self, profile_id: str, action_group: str, seconds: int):
        self.cooldown_until[(str(profile_id), str(action_group))] = time.time() + max(0, int(seconds))

    def should_pause(self, profile_id: str, action_group: str) -> bool:
        return time.time() < self.cooldown_until.get((str(profile_id), str(action_group)), 0)
