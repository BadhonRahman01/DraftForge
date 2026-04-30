# DraftForge

A real-time collaborative Dota 2 draft board where two coaches or players can simultaneously run a pick/ban simulation in the same browser room. When one person picks or bans a hero, the other sees it instantly — no refresh, no polling. Built as a portfolio project to demonstrate WebSocket protocol design, real-time state synchronisation, Redis Pub/Sub fan-out, and Operational Transformation for conflict-free collaborative editing.

---

## Architecture

```
Browser A (SvelteKit)          Browser B (SvelteKit)
      │  WebSocket /ws/{room}        │
      └──────────┬───────────────────┘
                 │
         FastAPI (Python)
         ┌───────────────────────────┐
         │  ConnectionManager        │  ← in-memory room map (Phase 1)
         │  WS handlers              │  ← validate & apply actions
         │  REST: /api/rooms         │
         │       /api/heroes         │  ← proxied from OpenDota API
         └──────────┬────────────────┘
                    │
         ┌──────────┴────────────┐
         │                       │
    PostgreSQL 15            Redis 7
    (Phase 2: persist      (Phase 2: Pub/Sub
     DraftEvent rows)       fan-out across
                            server instances)
```

**WebSocket event flow:**
1. Client sends `{ type: "pick_hero", payload: { hero_id, team } }`
2. Server validates (hero not already taken, team not full)
3. Server updates in-memory `RoomState` and broadcasts `hero_picked` to all peers
4. All clients update their `draftStore` → Svelte UI reacts instantly

---

## Setup

### Prerequisites
- Docker + Docker Compose
- Python 3.11+
- Node.js 18+

### 1. Start infrastructure

```bash
docker-compose up -d postgres redis
```

### 2. Start the backend

```bash
cd backend
cp .env.example .env          # edit DATABASE_URL / REDIS_URL if needed
pip install -r requirements.txt
uvicorn app.main:app --reload
# → http://localhost:8000
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### 4. Try it

1. Open `http://localhost:5173` in two browser tabs
2. Click **Create Room** in one tab — copy the room ID
3. Paste it into the **Join Room** field in the second tab
4. Pick or ban heroes in one tab — watch them appear in the other instantly

---

## What this demonstrates

| Skill | Where |
|---|---|
| **WebSockets** | `backend/app/main.py` endpoint, `frontend/src/lib/ws.ts` client |
| **Real-time state sync** | `ConnectionManager.broadcast_to_room`, `draftStore.applyPick/applyBan` |
| **Auto-reconnect with backoff** | `ws.ts` — exponential back-off 500ms → 16s |
| **FastAPI async patterns** | All handlers are `async def`, lifespan context manager |
| **Pydantic v2 message schema** | `app/ws/schemas.py` — discriminated union on `type` field |
| **SvelteKit reactive stores** | `draft.ts` writable store drives all UI reactivity |
| **Redis Pub/Sub** *(Phase 2)* | `app/services/redis.py` — fan-out to multiple server instances |
| **PostgreSQL persistence** *(Phase 2)* | `app/models/db.py` — SQLAlchemy 2 async, DraftEvent rows |
| **Operational Transformation** *(Phase 3)* | `app/ot/transform.py` — conflict-free collaborative notes |

---

## Build phases

- **Phase 1** ✅ WebSocket rooms + real-time pick/ban sync (in-memory)
- **Phase 2** PostgreSQL persistence + Redis Pub/Sub for horizontal scale
- **Phase 3** Collaborative notes panel with Operational Transformation
- **Phase 4** Canvas minimap drawing + OpenDota match stats + deployment
