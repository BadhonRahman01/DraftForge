from __future__ import annotations

import json
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # room_id → list of connected WebSocket clients
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str) -> None:
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str) -> None:
        room = self.active_connections.get(room_id, [])
        if websocket in room:
            room.remove(websocket)
        if not room:
            self.active_connections.pop(room_id, None)

    async def broadcast_to_room(
        self,
        room_id: str,
        message: dict[str, Any],
        exclude: WebSocket | None = None,
    ) -> None:
        payload = json.dumps(message)
        for ws in list(self.active_connections.get(room_id, [])):
            if ws is exclude:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(ws, room_id)

    async def send_personal(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(message))

    def room_size(self, room_id: str) -> int:
        return len(self.active_connections.get(room_id, []))


manager = ConnectionManager()
