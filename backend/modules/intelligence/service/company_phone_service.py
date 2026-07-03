"""
modules.intelligence.service.company_phone_service
====================================================
Busca e persiste o telefone de uma empresa via Google Places API (New).
Usado na aba People do Drawer para exibir o contato do Google Maps.

Fluxo: Places Text Search → nationalPhoneNumber → persiste em Organization.maps_phone.
A busca só acontece uma vez por empresa; chamadas seguintes retornam do banco.
"""
from __future__ import annotations

from typing import Optional

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.observability.logging_config import get_logger
from models import Organization

log = get_logger(__name__)

_PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


async def fetch_and_cache_company_phone(org_id: int, db: AsyncSession) -> Optional[str]:
    """
    Retorna o telefone da empresa via Google Maps, persistido permanentemente no banco.
    Se já tiver salvo, retorna diretamente sem chamar a API. Caso contrário, busca,
    salva e retorna — futuras chamadas reutilizam o valor do banco.
    """
    stmt = select(Organization).where(or_(Organization.id == org_id, Organization.pipedrive_id == org_id))
    result = await db.execute(stmt)
    org = result.scalars().first()
    if not org:
        return None

    if org.maps_phone:
        return org.maps_phone

    if not org.name or not settings.GOOGLE_MAPS_API_KEY:
        return None

    try:
        headers = {
            "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "places.nationalPhoneNumber,places.internationalPhoneNumber",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                _PLACES_SEARCH_URL,
                headers=headers,
                json={"textQuery": org.name, "languageCode": "pt-BR"},
            )
            if resp.status_code != 200:
                log.warning("company_phone.places_search_failed", status=resp.status_code, org_name=org.name)
                return None

            places = resp.json().get("places", [])
            if not places:
                return None

            place = places[0]
            phone = place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber")
            if not phone:
                return None

            org.maps_phone = phone
            await db.commit()
            log.info("company_phone.fetched_and_cached", org_id=org.id, name=org.name, phone=phone)
            return phone
    except Exception as e:
        log.warning("company_phone.fetch_failed", org_name=org.name, error=str(e))
        return None
