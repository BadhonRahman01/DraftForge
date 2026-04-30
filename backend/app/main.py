from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.api import heroes, rooms
from app.ws.handlers import (
    get_or_create_room,
    handle_ban_hero,
    handle_pick_hero,
)
from app.ws.manager import manager
from app.ws.schemas import IncomingMessage, OutgoingMessage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Phase 1: no DB or Redis to initialise — placeholders ready for Phase 2
    print("[DraftForge] Starting up (Phase 1 — in-memory mode)")
    yield
    print("[DraftForge] Shutting down")


app = FastAPI(title="DraftForge API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rooms.router, prefix="/api")
app.include_router(heroes.router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

def _out(type_: str, data: dict) -> dict:
    return {"type": type_, "data": data, "timestamp": time.time()}


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str) -> None:
    await manager.connect(websocket, room_id)
    state = get_or_create_room(room_id)
    print(f"[WS] Client joined room={room_id}  peers={manager.room_size(room_id)}")

    # Send current state to the newly joined client
    await manager.send_personal(websocket, _out("room_state", state.to_dict()))

    # Notify others that someone joined
    await manager.broadcast_to_room(
        room_id,
        _out("presence", {"event": "joined", "peers": manager.room_size(room_id)}),
        exclude=websocket,
    )

    try:
        while True:
            raw = await websocket.receive_text()
            print(f"[WS] recv room={room_id}  data={raw[:120]}")

            try:
                data = json.loads(raw)
                msg = IncomingMessage(**data)
            except Exception as exc:
                await manager.send_personal(
                    websocket, _out("error", {"message": f"Invalid message: {exc}"})
                )
                continue

            if msg.type == "pick_hero":
                await handle_pick_hero(room_id, msg.payload, websocket, manager)
            elif msg.type == "ban_hero":
                await handle_ban_hero(room_id, msg.payload, websocket, manager)
            elif msg.type == "join_room":
                # Re-send state on explicit join (e.g. after reconnect)
                await manager.send_personal(
                    websocket, _out("room_state", state.to_dict())
                )
            else:
                await manager.send_personal(
                    websocket, _out("error", {"message": f"Unknown type: {msg.type}"})
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        print(f"[WS] Client left room={room_id}  peers={manager.room_size(room_id)}")
        await manager.broadcast_to_room(
            room_id,
            _out("presence", {"event": "left", "peers": manager.room_size(room_id)}),
        )
