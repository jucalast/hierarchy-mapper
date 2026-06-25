"""
modules.intelligence.service.company_photo_service
====================================================
Busca e persiste (cache permanente em base64) a foto de uma empresa via Google
Places API (New). Usada no header do Drawer como background atrás do nome/logo.

Fluxo: 1) Places Text Search pra achar o place_id/foto da empresa.
       2) Places Photo Media pra baixar os bytes da foto.
       3) Converte para data URI base64 e persiste em Organization.photo_url —
          assim a busca na API só acontece uma vez por empresa (ver init_db()
          pra migração resiliente da coluna).
"""
from __future__ import annotations

import base64
from typing import Optional

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.observability.logging_config import get_logger
from models import Organization

log = get_logger(__name__)

_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


async def _search_place_photo_resource(org_name: str, address: Optional[str]) -> Optional[str]:
    """Busca a empresa no Google Places e retorna o resource name da primeira foto disponível."""
    if not settings.GOOGLE_MAPS_API_KEY or not org_name:
        return None
    try:
        query = f"{org_name} {address}" if address else org_name
        headers = {
            "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "places.photos",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                _PLACES_SEARCH_URL,
                headers=headers,
                json={"textQuery": query, "languageCode": "pt-BR"},
            )
            if resp.status_code != 200:
                log.warning("company_photo.places_search_failed", status=resp.status_code, org_name=org_name)
                return None
            places = resp.json().get("places", [])
            if not places:
                return None
            photos = places[0].get("photos") or []
            if not photos:
                return None
            return photos[0].get("name")
    except Exception as e:
        log.warning("company_photo.search_failed", org_name=org_name, error=str(e))
        return None


async def _download_photo_as_base64(photo_resource_name: str) -> Optional[str]:
    """Baixa a foto do endpoint de Photo Media do Places API e converte para base64."""
    try:
        url = f"https://places.googleapis.com/v1/{photo_resource_name}/media"
        params = {"maxWidthPx": "900", "key": settings.GOOGLE_MAPS_API_KEY}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                b64 = base64.b64encode(resp.content).decode("utf-8")
                return f"data:{content_type};base64,{b64}"
            log.warning("company_photo.download_failed", status=resp.status_code)
    except Exception as e:
        log.warning("company_photo.download_exception", error=str(e))
    return None


async def fetch_and_cache_company_photo(org_id: int, db: AsyncSession) -> Optional[str]:
    """
    Retorna a foto da empresa (data URI base64), persistida permanentemente no banco.
    Se a organização já tiver uma foto salva, retorna do cache sem chamar a API de novo.
    Caso contrário, busca no Google Places, baixa, converte e salva — a partir daí
    qualquer abertura futura do Drawer reaproveita o valor salvo.
    """
    stmt = select(Organization).where(or_(Organization.id == org_id, Organization.pipedrive_id == org_id))
    result = await db.execute(stmt)
    org = result.scalars().first()
    if not org:
        return None

    if org.photo_url:
        return org.photo_url

    if not org.name:
        return None

    photo_resource = await _search_place_photo_resource(org.name, org.address)
    if not photo_resource:
        return None

    photo_b64 = await _download_photo_as_base64(photo_resource)
    if not photo_b64:
        return None

    org.photo_url = photo_b64
    await db.commit()
    log.info("company_photo.fetched_and_cached", org_id=org.id, name=org.name)
    return photo_b64
