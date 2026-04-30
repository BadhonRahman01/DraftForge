from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/heroes", tags=["heroes"])

OPENDOTA_HEROES_URL = "https://api.opendota.com/api/heroes"
CDN_PREFIX = "https://cdn.cloudflare.steamstatic.com"

_cache: dict[str, Any] = {"data": None, "fetched_at": 0.0}
CACHE_TTL = 3600  # 1 hour


async def _fetch_heroes() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(OPENDOTA_HEROES_URL)
        resp.raise_for_status()
        raw: list[dict[str, Any]] = resp.json()

    return [
        {
            "id": h["id"],
            "localized_name": h["localized_name"],
            "primary_attr": h["primary_attr"],
            "img": f"{CDN_PREFIX}{h['img']}",
            "icon": f"{CDN_PREFIX}{h['icon']}",
        }
        for h in raw
    ]


@router.get("")
async def list_heroes() -> list[dict[str, Any]]:
    now = time.time()
    if _cache["data"] is None or now - _cache["fetched_at"] > CACHE_TTL:
        try:
            _cache["data"] = await _fetch_heroes()
            _cache["fetched_at"] = now
        except httpx.HTTPError as exc:
            if _cache["data"] is not None:
                # Serve stale data rather than fail
                return _cache["data"]
            raise HTTPException(status_code=502, detail=f"OpenDota API error: {exc}") from exc

    return _cache["data"]
