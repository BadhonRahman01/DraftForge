from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel


class PickHeroPayload(BaseModel):
    hero_id: int
    team: Literal["radiant", "dire"]


class BanHeroPayload(BaseModel):
    hero_id: int
    team: Literal["radiant", "dire"]


class JoinRoomPayload(BaseModel):
    pass


class IncomingMessage(BaseModel):
    type: Literal["pick_hero", "ban_hero", "join_room", "leave_room", "end_room"]
    payload: dict[str, Any] = {}


class OutgoingMessage(BaseModel):
    type: str
    data: dict[str, Any]
    timestamp: float = 0.0

    def model_post_init(self, __context: Any) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()
