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
    rooms as room_store,
)
from app.ws.manager import manager
from app.ws.schemas import IncomingMessage, OutgoingMessage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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
async def websocket_endpoint(websocket: WebSocket, room_id: str, token: str = "") -> None:
    # Reject before accepting if room doesn't exist or is already closed
    if room_id not in room_store:
        await websocket.accept()
        await websocket.send_json(_out("error", {"message": "Room not found"}))
        await websocket.close(code=4004)
        return

    state = room_store[room_id]

    if state.closed:
        await websocket.accept()
        await websocket.send_json(_out("room_closed", {"message": "This room has ended"}))
        await websocket.close(code=4004)
        return

    is_host = bool(token and token == state.host_token)

    await manager.connect(websocket, room_id)
    print(f"[WS] Client joined room={room_id} is_host={is_host} peers={manager.room_size(room_id)}")

    # Send full state (including host flag + current peer count) to the joining client
    await manager.send_personal(websocket, _out("room_state", {
        **state.to_dict(),
        "is_host": is_host,
        "peers": manager.room_size(room_id),
    }))

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
                await manager.send_personal(websocket, _out("room_state", {
                    **state.to_dict(),
                    "is_host": is_host,
                    "peers": manager.room_size(room_id),
                }))

            elif msg.type == "end_room":
                if not is_host:
                    await manager.send_personal(
                        websocket, _out("error", {"message": "Only the host can end the room"})
                    )
                    continue
                state.closed = True
                await manager.broadcast_to_room(
                    room_id, _out("room_closed", {"message": "Host ended the room"})
                )
                break

            elif msg.type == "leave_room":
                break

            else:
                await manager.send_personal(
                    websocket, _out("error", {"message": f"Unknown type: {msg.type}"})
                )

    except WebSocketDisconnect:
        pass

    finally:
        manager.disconnect(websocket, room_id)
        print(f"[WS] Client left room={room_id} is_host={is_host} peers={manager.room_size(room_id)}")

        if is_host and not state.closed:
            # Host disconnected without explicitly ending — close the room for everyone
            state.closed = True
            await manager.broadcast_to_room(
                room_id,
                _out("room_closed", {"message": "Host left the room"}),
            )
        elif not state.closed:
            await manager.broadcast_to_room(
                room_id,
                _out("presence", {"event": "left", "peers": manager.room_size(room_id)}),
            )
