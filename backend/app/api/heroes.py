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


def _cdn(path: str, short_name: str, kind: str) -> str:
    """Build a CDN URL that works regardless of whether the API returns a relative or absolute path."""
    if path and path.startswith("http"):
        return path
    if path and path.startswith("/"):
        return f"{CDN_PREFIX}{path}"
    # Fallback: construct from the hero's internal name, which is always stable
    if kind == "icon":
        return f"{CDN_PREFIX}/apps/dota2/images/dota_react/heroes/icons/{short_name}.png"
    return f"{CDN_PREFIX}/apps/dota2/images/dota_react/heroes/{short_name}.png"


async def _fetch_heroes() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(OPENDOTA_HEROES_URL)
        resp.raise_for_status()
        raw: list[dict[str, Any]] = resp.json()

    return [
        {
            "id": h["id"],
            "name": h["name"],
            "localized_name": h["localized_name"],
            "primary_attr": h["primary_attr"],
            "img": _cdn(h.get("img", ""), h["name"].replace("npc_dota_hero_", ""), "img"),
            "icon": _cdn(h.get("icon", ""), h["name"].replace("npc_dota_hero_", ""), "icon"),
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
        except Exception as exc:
            if _cache["data"] is not None:
                return _cache["data"]
            raise HTTPException(status_code=502, detail=f"Failed to fetch heroes: {exc}") from exc

    return _cache["data"]
