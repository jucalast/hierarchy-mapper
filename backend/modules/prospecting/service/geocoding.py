"""
Geocoding via Nominatim (OpenStreetMap) — sem API key, rate limit de 1 req/s.

Uso:
  city = await reverse_geocode(lat=-23.6, lng=-46.5)   # → "Santo André"
  coords = await forward_geocode("Santo André, SP")     # → (-23.66, -46.53)
"""
from __future__ import annotations

import asyncio
import random
from typing import Optional, Tuple

import httpx

from core.observability.logging_config import get_logger

log = get_logger(__name__)

_NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
_HEADERS = {"User-Agent": "LINKB2B-ProspectingModule/1.0 (luccasmoura902@gmail.com)"}
_LOCK = asyncio.Lock()
_last_call: float = 0.0


async def _throttled_get(url: str, params: dict) -> Optional[dict]:
    """Garante no máximo 1 req/s para respeitar o ToS do Nominatim."""
    global _last_call
    async with _LOCK:
        import time
        wait = 1.1 - (time.time() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=_HEADERS) as client:
                resp = await client.get(url, params=params)
                _last_call = time.time()
                if resp.status_code == 200:
                    return resp.json()
        except Exception as e:
            log.warning("geocoding.request_failed", url=url, error=str(e))
    return None


async def reverse_geocode(lat: float, lng: float) -> Optional[str]:
    """
    Converte lat/lng em nome de cidade.
    Retorna: "São Bernardo do Campo" ou None.
    """
    data = await _throttled_get(
        f"{_NOMINATIM_BASE}/reverse",
        {"lat": lat, "lon": lng, "format": "json", "zoom": 10, "addressdetails": 1},
    )
    if not data:
        return None
    addr = data.get("address", {})
    return (
        addr.get("city")
        or addr.get("town")
        or addr.get("municipality")
        or addr.get("county")
    )


async def forward_geocode(query: str) -> Optional[Tuple[float, float]]:
    """
    Converte nome de cidade/endereço em (lat, lng).
    Retorna: (-23.66, -46.53) ou None.
    """
    data = await _throttled_get(
        f"{_NOMINATIM_BASE}/search",
        {"q": query, "format": "json", "limit": 1, "countrycodes": "br"},
    )
    if data and isinstance(data, list) and data:
        try:
            return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception:
            pass
    return None


def jitter_coords(
    lat: float, lng: float, radius_km: float, seed: Optional[str] = None
) -> Tuple[float, float]:
    """
    Adiciona deslocamento aleatório dentro do raio para que pins não se sobreponham.
    Usa seed reproduzível por nome de empresa para consistência entre reloads.
    """
    rng = random.Random(seed)
    # 1 grau latitude ≈ 111 km
    max_offset_deg = (radius_km * 0.6) / 111.0
    dlat = rng.uniform(-max_offset_deg, max_offset_deg)
    dlng = rng.uniform(-max_offset_deg, max_offset_deg)
    return lat + dlat, lng + dlng
