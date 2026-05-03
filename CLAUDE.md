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
  │  WebSocket /ws/{room_id}?token=...   REST GET /api/heroes, POST /api/rooms
  ▼
app/main.py  ← single FastAPI app, CORS, lifespan
  │
  ├── /ws/{room_id}  websocket_endpoint(token: str = "")
  │     ├── Rejects closed/missing rooms before accepting
  │     ├── Identifies host via token == state.host_token
  │     ├── ConnectionManager.connect()       (app/ws/manager.py)
  │     ├── Sends room_state (with is_host, peers) to joining client
  │     └── loop: receive → IncomingMessage → handler
  │           pick_hero / ban_hero  → validated against CM sequence
  │           end_room  (host only) → broadcasts room_closed, breaks
  │           leave_room            → breaks (player disconnects)
  │           join_room             → re-sends room_state (reconnect)
  │
  ├── /api/rooms   (app/api/rooms.py)   POST creates room + host_token, GET returns state
  └── /api/heroes  (app/api/heroes.py)  proxies OpenDota, 1-hour module-level cache
```

### Vite proxy (frontend dev server)
`frontend/vite.config.ts` proxies `/api/*` → `http://localhost:8000` and `/ws/*` → `ws://localhost:8000`. All frontend fetch/WebSocket calls use relative URLs — never hardcoded `localhost:8000`.

Hero images fall back: frontend first tries `/api/heroes` (backend cached), then fetches directly from `https://api.opendota.com/api/heroes` if the backend returns an error. Image URLs are constructed from the hero's internal `name` field (`npc_dota_hero_antimage` → `cdn.cloudflare.steamstatic.com/…/antimage.png`) rather than relying on the API's `img` field, which can vary.

### State ownership (Phase 1)
`rooms: dict[str, RoomState]` in `app/ws/handlers.py` is the single source of truth. It is **module-level and in-memory** — state is lost on server restart and not shared across multiple server processes. This will be replaced by PostgreSQL + Redis in Phase 2.

`ConnectionManager` in `app/ws/manager.py` owns the live WebSocket objects (`active_connections: dict[str, list[WebSocket]]`). It is separate from room state intentionally — Phase 2 will keep `ConnectionManager` local to each server instance while `RoomState` moves to the DB.

### Host / room lifecycle
- `POST /api/rooms` generates both `room_id` (8-char hex) and `host_token` (32-char hex). The frontend stores `host_token` in `sessionStorage` keyed as `draftforge_host_{room_id}`.
- The host token is passed as `?token=` on the WebSocket URL. The server sets `is_host = (token == state.host_token)` for that connection.
- Host disconnect (intentional `end_room` or abrupt close): server marks `state.closed = True` and broadcasts `room_closed` to all peers, who redirect to home.
- New connections to a closed room receive `room_closed` immediately and are rejected.
- Non-host players send `leave_room` to disconnect gracefully.

### Captain's Mode draft sequence
`DRAFT_SEQUENCE` in `app/ws/handlers.py` defines 22 turns (12 bans + 10 picks, 6 bans and 5 picks per team):

```
Ban Phase 1:  R D R D
Pick Phase 1: R D D R
Ban Phase 2:  D R D R
Pick Phase 2: R D D R
Ban Phase 3:  R D R D
Pick Phase 3: R D
```

`RoomState.seq_index` tracks the current turn. `current_step`, `turn`, `action`, `phase`, and `draft_complete` are all derived from it. Every pick/ban handler calls `_validate_turn()` — if it's the wrong team or wrong action type (pick during a ban phase), the server rejects with an error message. On success, `state.advance()` increments `seq_index` and the full updated state is embedded in the broadcast.

Team assignment: host = Radiant, first joiner = Dire. The frontend sets `activeTeam` from the `is_host` field in the first `room_state` message and locks it (`teamAssigned` flag prevents reconnect resets).

### WebSocket message contract
Every message in both directions has a `type` field. Outgoing messages always carry `{ type, data, timestamp }`.

**Client → Server** (`app/ws/schemas.py` `IncomingMessage`):
- `pick_hero`  — `{ hero_id: int, team: "radiant"|"dire" }` — validated against CM sequence
- `ban_hero`   — `{ hero_id: int, team: "radiant"|"dire" }` — validated against CM sequence
- `join_room`  — `{}` re-requests full state (used after reconnect)
- `leave_room` — `{}` graceful player disconnect
- `end_room`   — `{}` host-only; closes room for everyone

**Server → Client** (built by `_out()` helpers):
- `room_state`   — full `RoomState.to_dict()` + `is_host: bool` + `peers: int`, sent on join / reconnect
- `hero_picked` / `hero_banned` — `{ hero_id, team, state }` where `state` is the full updated room state; broadcast to all peers including sender
- `presence`     — `{ event: "joined"|"left", peers: int }`
- `room_closed`  — `{ message: str }` broadcast when host ends/leaves; also sent to late joiners
- `error`        — `{ message: str }` sent only to the offending client

### Frontend data flow
`ws.ts` is a plain-module singleton (not a store). It holds the raw WebSocket, owns reconnect logic (exponential backoff), stores the token for reconnects, and forwards parsed messages to a single registered callback via `onMessage(cb)`.

`draftStore` (`src/lib/stores/draft.ts`) is the single Svelte writable that drives all UI. `DraftState` includes:
- `radiantPicks / direPicks / radiantBans / direBans` — Hero objects (not just IDs)
- `availableHeroes` — all heroes minus taken IDs
- `phase / turn / action / seqIndex / totalSteps / draftComplete` — CM sequence state
- `isHost / roomClosed / roomClosedReason` — room meta

The room page wires everything together: `hero_picked` and `hero_banned` events call `applyRoomState(data.state, allHeroes)` (not the separate `applyPick`/`applyBan`) so the sequence state advances atomically with the hero lists.

`applyRoomState` is the reconciliation path — it rebuilds the full store from a server snapshot. It is called on initial join, every reconnect, and every pick/ban broadcast.

### Phase boundaries
- **Phase 1** (current — complete): in-memory `rooms` dict, Captain's Mode draft enforcement, host/room lifecycle, Vite proxy, hero image CDN fallback
- **Phase 2**: `app/models/db.py` (SQLAlchemy async), `app/services/redis.py` (aioredis pub/sub). `RoomState` moves to Postgres; Redis fan-outs replace direct `broadcast_to_room` calls
- **Phase 3**: `app/ot/transform.py` — Operational Transformation for a collaborative notes panel
- **Phase 4**: Canvas minimap, OpenDota match stats, deployment

Do not add DB or Redis code until Phase 2 is explicitly started.

## Git workflow
- Use conventional commits: `feat:`, `fix:`, `refactor:`, `chore:`
- Push to `main` after every meaningful chunk of work
- `gh` CLI is at `C:\Program Files\GitHub CLI\gh.exe` (not on bash PATH; use PowerShell or full path)
