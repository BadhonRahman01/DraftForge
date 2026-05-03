from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.ws.handlers import get_or_create_room, rooms

router = APIRouter(prefix="/rooms", tags=["rooms"])


class CreateRoomResponse(BaseModel):
    room_id: str
    host_token: str


@router.post("", response_model=CreateRoomResponse)
async def create_room() -> CreateRoomResponse:
    room_id = uuid.uuid4().hex[:8]
    host_token = uuid.uuid4().hex
    get_or_create_room(room_id, host_token)
    return CreateRoomResponse(room_id=room_id, host_token=host_token)


@router.get("/{room_id}")
async def get_room(room_id: str) -> dict[str, Any]:
    if room_id not in rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    room = rooms[room_id]
    if room.closed:
        raise HTTPException(status_code=410, detail="Room has ended")
    return room.to_dict()
