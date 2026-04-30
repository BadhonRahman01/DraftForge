from __future__ import annotations

import time
from typing import Any

from fastapi import WebSocket

from app.ws.manager import ConnectionManager
from app.ws.schemas import BanHeroPayload, PickHeroPayload


# ---------------------------------------------------------------------------
# In-memory room state (Phase 1 — replaced by DB + Redis in Phase 2)
# ---------------------------------------------------------------------------

class RoomState:
    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.radiant_picks: list[int] = []
        self.dire_picks: list[int] = []
        self.radiant_bans: list[int] = []
        self.dire_bans: list[int] = []
        self.phase: str = "draft"
        self.turn: str = "radiant"

    def all_taken(self) -> set[int]:
        return set(
            self.radiant_picks
            + self.dire_picks
            + self.radiant_bans
            + self.dire_bans
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "radiant_picks": self.radiant_picks,
            "dire_picks": self.dire_picks,
            "radiant_bans": self.radiant_bans,
            "dire_bans": self.dire_bans,
            "phase": self.phase,
            "turn": self.turn,
        }


# Module-level store — single source of truth for Phase 1
rooms: dict[str, RoomState] = {}


def get_or_create_room(room_id: str) -> RoomState:
    if room_id not in rooms:
        rooms[room_id] = RoomState(room_id)
    return rooms[room_id]


def _out(type_: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": type_, "data": data, "timestamp": time.time()}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_pick_hero(
    room_id: str,
    payload: dict[str, Any],
    sender_ws: WebSocket,
    mgr: ConnectionManager,
) -> None:
    try:
        p = PickHeroPayload(**payload)
    except Exception as exc:
        await mgr.send_personal(sender_ws, _out("error", {"message": str(exc)}))
        return

    state = get_or_create_room(room_id)

    if p.hero_id in state.all_taken():
        await mgr.send_personal(
            sender_ws,
            _out("error", {"message": f"Hero {p.hero_id} is already picked or banned."}),
        )
        return

    if p.team == "radiant":
        if len(state.radiant_picks) >= 5:
            await mgr.send_personal(sender_ws, _out("error", {"message": "Radiant already has 5 picks."}))
            return
        state.radiant_picks.append(p.hero_id)
    else:
        if len(state.dire_picks) >= 5:
            await mgr.send_personal(sender_ws, _out("error", {"message": "Dire already has 5 picks."}))
            return
        state.dire_picks.append(p.hero_id)

    msg = _out("hero_picked", {"hero_id": p.hero_id, "team": p.team, "state": state.to_dict()})
    # Send confirmation to sender too so their UI stays consistent
    await mgr.send_personal(sender_ws, msg)
    await mgr.broadcast_to_room(room_id, msg, exclude=sender_ws)


async def handle_ban_hero(
    room_id: str,
    payload: dict[str, Any],
    sender_ws: WebSocket,
    mgr: ConnectionManager,
) -> None:
    try:
        p = BanHeroPayload(**payload)
    except Exception as exc:
        await mgr.send_personal(sender_ws, _out("error", {"message": str(exc)}))
        return

    state = get_or_create_room(room_id)

    if p.hero_id in state.all_taken():
        await mgr.send_personal(
            sender_ws,
            _out("error", {"message": f"Hero {p.hero_id} is already picked or banned."}),
        )
        return

    if p.team == "radiant":
        if len(state.radiant_bans) >= 7:
            await mgr.send_personal(sender_ws, _out("error", {"message": "Radiant already has 7 bans."}))
            return
        state.radiant_bans.append(p.hero_id)
    else:
        if len(state.dire_bans) >= 7:
            await mgr.send_personal(sender_ws, _out("error", {"message": "Dire already has 7 bans."}))
            return
        state.dire_bans.append(p.hero_id)

    msg = _out("hero_banned", {"hero_id": p.hero_id, "team": p.team, "state": state.to_dict()})
    await mgr.send_personal(sender_ws, msg)
    await mgr.broadcast_to_room(room_id, msg, exclude=sender_ws)
