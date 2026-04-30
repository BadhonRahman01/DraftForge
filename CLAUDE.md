# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
cd backend
uvicorn app.main:app --reload          # dev server on :8000
pytest                                  # run all tests
pytest tests/test_handlers.py -k pick  # run a single test
```

`asyncpg` cannot be pip-installed on this Windows machine (needs C++ Build Tools). Install everything else and rely on Docker for the DB. `asyncpg` compiles fine inside the container.

### Frontend
```bash
cd frontend
npm run dev          # dev server on :5173
npm run check        # svelte-check + tsc (run before committing)
npm run build        # production build
```

### Infrastructure
```bash
docker-compose up -d postgres redis    # start DB + cache only
docker-compose up                      # start everything including backend
```

Backend `.env` is gitignored. Copy `backend/.env.example` and fill in values for local dev.

## Architecture

### Request / event flow
```
Browser (SvelteKit)
  │  WebSocket /ws/{room_id}         REST GET /api/heroes, POST /api/rooms
  ▼
app/main.py  ← single FastAPI app, CORS, lifespan
  │
  ├── /ws/{room_id}  websocket_endpoint()
  │     ├── ConnectionManager.connect()       (app/ws/manager.py)
  │     ├── sends room_state to joining client
  │     └── loop: receive → IncomingMessage → handle_pick/ban_hero()
  │                                            (app/ws/handlers.py)
  │
  ├── /api/rooms   (app/api/rooms.py)   POST creates room, GET returns state dict
  └── /api/heroes  (app/api/heroes.py)  proxies OpenDota, 1-hour module-level cache
```

### State ownership (Phase 1)
`rooms: dict[str, RoomState]` in `app/ws/handlers.py` is the single source of truth. It is **module-level and in-memory** — state is lost on server restart and not shared across multiple server processes. This will be replaced by PostgreSQL + Redis in Phase 2.

`ConnectionManager` in `app/ws/manager.py` owns the live WebSocket objects (`active_connections: dict[str, list[WebSocket]]`). It is separate from room state intentionally — Phase 2 will keep `ConnectionManager` local to each server instance while `RoomState` moves to the DB.

### WebSocket message contract
Every message in both directions has a `type` field. Outgoing messages always carry `{ type, data, timestamp }`.

**Client → Server** (`app/ws/schemas.py` `IncomingMessage`):
- `pick_hero` — `{ hero_id: int, team: "radiant"|"dire" }`
- `ban_hero`  — `{ hero_id: int, team: "radiant"|"dire" }`
- `join_room` — `{}` (re-requests full state, used after reconnect)

**Server → Client** (built by `_out()` helpers):
- `room_state` — full `RoomState.to_dict()`, sent on join and explicit `join_room`
- `hero_picked` / `hero_banned` — `{ hero_id, team, state }` broadcast to all peers including sender
- `presence` — `{ event: "joined"|"left", peers: int }`
- `error` — `{ message: str }` sent only to the offending client

### Frontend data flow
`ws.ts` is a plain-module singleton (not a store). It holds the raw WebSocket, owns reconnect logic, and forwards parsed messages to a single registered callback via `onMessage(cb)`.

`draftStore` (`src/lib/stores/draft.ts`) is the single Svelte writable that drives all UI. The room page (`routes/room/[id]/+page.svelte`) wires them together: it calls `onMessage(handleWsMessage)` and dispatches to `draftStore.applyPick`, `applyBan`, or `applyRoomState`. Hero objects are stored in the store (not just IDs) so components never need to look up heroes themselves.

`applyRoomState` is the reconciliation path — it rebuilds the full store from a server snapshot and recomputes `availableHeroes` as `allHeroes` minus all taken IDs. It is called on initial join and after every reconnect.

### Phase boundaries
- **Phase 1** (current): in-memory `rooms` dict, in-memory `ConnectionManager`, no DB, no Redis
- **Phase 2**: `app/models/db.py` (SQLAlchemy async), `app/services/redis.py` (aioredis pub/sub). `RoomState` moves to Postgres; Redis fan-outs replace direct `broadcast_to_room` calls
- **Phase 3**: `app/ot/transform.py` — Operational Transformation for a collaborative notes panel
- **Phase 4**: Canvas minimap, OpenDota match stats, deployment

Do not add DB or Redis code until Phase 2 is explicitly started.

## Git workflow
- Use conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`
- Push to `main` after every meaningful chunk of work
- `gh` CLI is at `C:\Program Files\GitHub CLI\gh.exe` (not on bash PATH; use PowerShell or full path)
