from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import WebSocket

from app.ws.manager import ConnectionManager
from app.ws.schemas import BanHeroPayload, PickHeroPayload


# ---------------------------------------------------------------------------
# Captain's Mode draft sequence — 22 turns (12 bans, 10 picks)
# ---------------------------------------------------------------------------

# Each entry: (team, action)
DRAFT_SEQUENCE: list[tuple[str, str]] = [
    # Ban Phase 1
    ("radiant", "ban"), ("dire", "ban"), ("radiant", "ban"), ("dire", "ban"),
    # Pick Phase 1
    ("radiant", "pick"), ("dire", "pick"), ("dire", "pick"), ("radiant", "pick"),
    # Ban Phase 2
    ("dire", "ban"), ("radiant", "ban"), ("dire", "ban"), ("radiant", "ban"),
    # Pick Phase 2
    ("radiant", "pick"), ("dire", "pick"), ("dire", "pick"), ("radiant", "pick"),
    # Ban Phase 3
    ("radiant", "ban"), ("dire", "ban"), ("radiant", "ban"), ("dire", "ban"),
    # Pick Phase 3
    ("radiant", "pick"), ("dire", "pick"),
]

_PHASE_LABELS: list[str] = (
    ["Ban Phase 1"] * 4 +
    ["Pick Phase 1"] * 4 +
    ["Ban Phase 2"] * 4 +
    ["Pick Phase 2"] * 4 +
    ["Ban Phase 3"] * 4 +
    ["Pick Phase 3"] * 2
)

TOTAL_STEPS = len(DRAFT_SEQUENCE)


# ---------------------------------------------------------------------------
# In-memory room state (Phase 1 — replaced by DB + Redis in Phase 2)
# ---------------------------------------------------------------------------

class RoomState:
    def __init__(self, room_id: str, host_token: str) -> None:
        self.room_id = room_id
        self.host_token = host_token
        self.closed = False
        self.radiant_picks: list[int] = []
        self.dire_picks: list[int] = []
        self.radiant_bans: list[int] = []
        self.dire_bans: list[int] = []
        self.seq_index: int = 0

    # -- Derived state from sequence ----------------------------------------

    @property
    def current_step(self) -> tuple[str, str] | None:
        if self.seq_index >= TOTAL_STEPS:
            return None
        return DRAFT_SEQUENCE[self.seq_index]

    @property
    def turn(self) -> str:
        step = self.current_step
        return step[0] if step else ""

    @property
    def action(self) -> str:
        step = self.current_step
        return step[1] if step else ""

    @property
    def phase(self) -> str:
        if self.seq_index >= TOTAL_STEPS:
            return "Draft Complete"
        return _PHASE_LABELS[self.seq_index]

    @property
    def draft_complete(self) -> bool:
        return self.seq_index >= TOTAL_STEPS

    def advance(self) -> None:
        self.seq_index += 1

    def all_taken(self) -> set[int]:
        return set(
            self.radiant_picks + self.dire_picks +
            self.radiant_bans + self.dire_bans
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
            "action": self.action,
            "seq_index": self.seq_index,
            "total_steps": TOTAL_STEPS,
            "draft_complete": self.draft_complete,
            "closed": self.closed,
        }


# Module-level store — single source of truth for Phase 1
rooms: dict[str, RoomState] = {}


def get_or_create_room(room_id: str, host_token: str | None = None) -> RoomState:
    if room_id not in rooms:
        rooms[room_id] = RoomState(room_id, host_token or uuid.uuid4().hex)
    return rooms[room_id]


def _out(type_: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": type_, "data": data, "timestamp": time.time()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_turn(
    state: RoomState, team: str, expected_action: str
) -> str | None:
    """Return an error string if this action is not allowed, else None."""
    if state.draft_complete:
        return "The draft is already complete."
    step = state.current_step
    if step is None:
        return "The draft is already complete."
    curr_team, curr_action = step
    if curr_team != team:
        return f"It is {curr_team.capitalize()}'s turn, not {team.capitalize()}'s."
    if curr_action != expected_action:
        return f"This turn is a {curr_action}, not a {expected_action}."
    return None


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

    err = _validate_turn(state, p.team, "pick")
    if err:
        await mgr.send_personal(sender_ws, _out("error", {"message": err}))
        return

    if p.hero_id in state.all_taken():
        await mgr.send_personal(sender_ws, _out("error", {"message": "Hero already taken."}))
        return

    if p.team == "radiant":
        state.radiant_picks.append(p.hero_id)
    else:
        state.dire_picks.append(p.hero_id)

    state.advance()

    msg = _out("hero_picked", {"hero_id": p.hero_id, "team": p.team, "state": state.to_dict()})
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

    err = _validate_turn(state, p.team, "ban")
    if err:
        await mgr.send_personal(sender_ws, _out("error", {"message": err}))
        return

    if p.hero_id in state.all_taken():
        await mgr.send_personal(sender_ws, _out("error", {"message": "Hero already taken."}))
        return

    if p.team == "radiant":
        state.radiant_bans.append(p.hero_id)
    else:
        state.dire_bans.append(p.hero_id)

    state.advance()

    msg = _out("hero_banned", {"hero_id": p.hero_id, "team": p.team, "state": state.to_dict()})
    await mgr.send_personal(sender_ws, msg)
    await mgr.broadcast_to_room(room_id, msg, exclude=sender_ws)
