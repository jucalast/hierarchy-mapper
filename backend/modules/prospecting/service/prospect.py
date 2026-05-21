"""
Orquestrador de prospecção com busca automática por todos os segmentos ICP.

Fluxo:
  1. start_prospect_search(lat, lng, radius_km)
     → reverse geocode lat/lng → cidade
     → para cada segmento ICP, busca no LinkedIn via DuckDuckGo + cidade
  2. Cada empresa encontrada:
     → verifica dedup Pipedrive → qualifica IA → geocodifica para o mapa
  3. Frontend faz polling via GET /sessions/{id}/leads
  4. Usuário aprova → cria no Pipedrive; rejeita → descarta
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select, func

from core.infra.database import async_session
from core.observability.logging_config import get_logger
from models.organization import Organization
from models.people.prospect import ProspectLead, ProspectSession
from modules.ai.service.context.business_context import ICP
from modules.hierarchy.service.search_engine import get_duck_results

from .duplicate_checker import check_pipedrive_duplicate
from .geocoding import forward_geocode, jitter_coords, reverse_geocode
from .qualifier import qualify_prospect
from modules.intelligence.service.brand_discovery import fetch_linkedin_logo

log = get_logger(__name__)

# Segmentos ICP derivados de business_context.py — buscamos todos automaticamente
_ICP_SEGMENTS = [
    "autopeças",
    "montadora automotiva",
    "máquinas industriais",
    "ferramentas industriais",
    "motores industriais",
    "exportação industrial",
    "metalúrgica",
]

# Delay entre processamento de leads para não explodir rate limits
_INTER_LEAD_DELAY_SEC = 2.5


# ---------------------------------------------------------------------------
# Entrada pública
# ---------------------------------------------------------------------------

async def start_prospect_search(
    lat: float,
    lng: float,
    radius_km: int = 50,
) -> str:
    """
    Inicia sessão de prospecção com base em coordenadas + raio.
    Retorna session_id imediatamente; busca ocorre em background.
    """
    session_id = str(uuid.uuid4())

    city_name = await reverse_geocode(lat, lng)

    from modules.ai.service.context.business_context import load_db_setting
    icp_config = await load_db_setting("icp_config", {})
    segments = icp_config.get("icp_segments", _ICP_SEGMENTS) if isinstance(icp_config, dict) else _ICP_SEGMENTS

    async with async_session() as db:
        sess = ProspectSession(
            id=session_id,
            lat=str(lat),
            lng=str(lng),
            radius_km=radius_km,
            city_name=city_name,
            segments_searched=segments,
            status="running",
        )
        db.add(sess)
        await db.commit()

    asyncio.create_task(
        _run_search(session_id, lat, lng, radius_km, city_name),
        name=f"prospect_{session_id[:8]}",
    )

    log.info(
        "prospect.session.created",
        session_id=session_id,
        city=city_name,
        radius_km=radius_km,
    )
    return session_id


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def stop_prospect_search(session_id: str) -> bool:
    """Para uma sessão de prospecção em andamento."""
    async with async_session() as db:
        sess = await db.get(ProspectSession, session_id)
        if sess and sess.status == "running":
            sess.status = "failed" # Usamos failed para indicar parada forçada
            sess.error_message = "Interrompido pelo usuário"
            await db.commit()
            log.info("prospect.session.stopped", session_id=session_id)
            return True
    return False

async def _is_session_active(session_id: str) -> bool:
    """Verifica se a sessão ainda deve continuar rodando."""
    async with async_session() as db:
        sess = await db.get(ProspectSession, session_id)
        return sess is not None and sess.status == "running"

async def _run_search(
    session_id: str,
    center_lat: float,
    center_lng: float,
    radius_km: int,
    city_name: Optional[str],
) -> None:
    found = 0
    location_hint = city_name or ""

    from modules.ai.service.context.business_context import load_db_setting
    icp_config = await load_db_setting("icp_config", {})
    segments = icp_config.get("icp_segments", _ICP_SEGMENTS) if isinstance(icp_config, dict) else _ICP_SEGMENTS

    try:
        for segment in segments:
            # 🛑 Check stop signal
            if not await _is_session_active(session_id):
                log.info("prospect.search.aborted", session_id=session_id)
                return

            try:
                saved = await _search_segment(
                    session_id, segment, location_hint,
                    center_lat, center_lng, radius_km,
                )
                found += saved
            except Exception as e:
                log.warning("prospect.segment.failed", segment=segment, error=str(e))
            
            # Pausa entre segmentos para respeitar rate limits do DuckDuckGo
            await asyncio.sleep(5.0)

        await _finish_session(session_id, found)
        log.info("prospect.search.done", session_id=session_id, found=found)

    except Exception as e:
        log.error("prospect.search.error", session_id=session_id, error=str(e))
        await _finish_session(session_id, found, str(e))


async def _search_segment(
    session_id: str,
    segment: str,
    city: str,
    center_lat: float,
    center_lng: float,
    radius_km: int,
) -> int:
    query = f'site:linkedin.com/company "{segment}"'
    if city:
        query += f' "{city}"'

    log.info("prospect.segment.search", segment=segment, city=city)
    results = await get_duck_results(query, max_results=10, is_company=True)

    saved = 0
    for raw in results:
        # 🛑 Check stop signal
        if not await _is_session_active(session_id):
            return saved

        try:
            ok = await _process_result(
                session_id, raw, city, center_lat, center_lng, radius_km
            )
            if ok:
                saved += 1
        except Exception as e:
            log.warning("prospect.result.failed", error=str(e))
        await asyncio.sleep(_INTER_LEAD_DELAY_SEC)

    return saved


async def _process_result(
    session_id: str,
    raw: dict,
    city: str,
    center_lat: float,
    center_lng: float,
    radius_km: int,
) -> bool:
    href = raw.get("href", "")
    title = raw.get("title", "")
    body = raw.get("body", "")

    company_name = _extract_company_name(title)
    if not company_name:
        return False

    # Evita duplicatas dentro da mesma sessão
    if await _lead_exists_in_session(session_id, company_name):
        return False

    domain = _extract_domain(body)

    # Dedup cross-sessão: já foi aprovada ou rejeitada antes → não mostra de novo
    if await _lead_already_processed(company_name, domain=domain):
        log.info("prospect.skip.already_processed", company=company_name)
        return False

    # Empresa descartada localmente (reject_lead marca is_excluded=1)
    if await _is_org_excluded(company_name, domain=domain):
        log.info("prospect.skip.excluded", company=company_name)
        return False

    # Dedup no Pipedrive global — qualquer empresa já cadastrada é ignorada
    dedup = await check_pipedrive_duplicate(company_name, domain=domain)
    if dedup["status"] != "new":
        log.info("prospect.skip.in_pipedrive", company=company_name, status=dedup["status"])
        return False

    # Qualifica com IA + ICP scoring
    qual = await qualify_prospect(
        company_name=company_name,
        description=body,
        location=city,
        linkedin_url=href,
    )

    if qual["icp_tier"] == "C":
        log.info("prospect.skip.tier_c", company=company_name, score=qual["icp_score"])
        return False

    # Coordenadas para o mapa
    lead_lat, lead_lng = await _resolve_coords(
        company_name, body, center_lat, center_lng, radius_km
    )

    # Logo da empresa (LinkedIn og:image)
    logo_url = None
    if href and "/company/" in href:
        try:
            logo_url = fetch_linkedin_logo(href)
        except Exception:
            pass  # Logo é opcional

    # Tenta extrair um endereço mais detalhado se disponível, senão usa a cidade
    detailed_address = _extract_city_from_body(body) or city

    async with async_session() as db:
        lead = ProspectLead(
            id=str(uuid.uuid4()),
            session_id=session_id,
            name=company_name,
            domain=_extract_domain(body),
            address=detailed_address,
            logo_url=logo_url,
            segment=qual.get("segment"),
            size_label=qual.get("size_label"),
            employee_count=qual.get("employee_count"),
            exports=1 if qual.get("exports") else 0,
            linkedin_url=href,
            description=qual.get("description_pt"),
            icp_score=qual.get("icp_score", 0),
            icp_tier=qual.get("icp_tier"),
            icp_reasons=qual.get("icp_reasons"),
            icp_penalties=qual.get("icp_penalties"),
            icp_recommendation=qual.get("icp_recommendation"),
            outreach_angle=qual.get("outreach_angle"),
            relevance_signal=qual.get("relevance_signal"),
            pipedrive_status=dedup["status"],
            pipedrive_org_id=dedup["org_id"],
            pipedrive_last_activity=dedup["last_activity"],
            pipedrive_deal_info=dedup["deal_info"],
            lat=str(lead_lat),
            lng=str(lead_lng),
            status="pending",
        )
        db.add(lead)
        
        # Também já salva na tabela principal de Organizations
        domain = _extract_domain(body)
        org = Organization(
            name=company_name,
            domain=domain,
            category=qual.get("segment"),
            description=qual.get("description_pt"),
            linkedin_url=href,
            source="prospecting",
            is_excluded=0,
            address=detailed_address,
            icp_score=qual.get("icp_score", 0),
            icp_tier=qual.get("icp_tier"),
            logo_url=logo_url
        )
        db.add(org)
        
        await db.commit()

    log.info(
        "prospect.lead.saved",
        company=company_name,
        tier=qual["icp_tier"],
        score=qual["icp_score"],
    )
    return True


# ---------------------------------------------------------------------------
# Coordenadas do lead para o mapa
# ---------------------------------------------------------------------------

async def _resolve_coords(
    company_name: str,
    body: str,
    center_lat: float,
    center_lng: float,
    radius_km: int,
) -> Tuple[float, float]:
    """
    Tenta geocodificar a empresa. Fallback: posição com jitter dentro do raio.
    """
    # Tenta extrair cidade do snippet do LinkedIn
    city_in_body = _extract_city_from_body(body)
    if city_in_body:
        coords = await forward_geocode(f"{city_in_body}, Brasil")
        if coords:
            lat, lng = jitter_coords(coords[0], coords[1], radius_km * 0.3, company_name)
            return lat, lng

    # Fallback: spread aleatório em torno do centro
    lat, lng = jitter_coords(center_lat, center_lng, radius_km, company_name)
    return lat, lng


def _extract_city_from_body(body: str) -> Optional[str]:
    """
    Extrai nome de cidade do snippet do LinkedIn.
    Ex: "São Paulo, Brasil · 500+ funcionários"
    """
    if not body:
        return None
    # Padrão comum nos snippets: "Cidade, Estado · ..."
    m = re.search(r'([A-ZÀ-Ü][a-zà-ü]+(?:\s[A-ZÀ-Ü][a-zà-ü]+)*)\s*,\s*(?:SP|RJ|MG|RS|PR|SC|BA|GO|ES|PE|AM)', body)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Queries de leitura
# ---------------------------------------------------------------------------

async def get_session(session_id: str) -> Optional[dict]:
    async with async_session() as db:
        res = await db.execute(
            select(ProspectSession).where(ProspectSession.id == session_id)
        )
        sess = res.scalars().first()
        return _session_to_dict(sess) if sess else None


async def list_sessions(limit: int = 20) -> List[dict]:
    from sqlalchemy import desc
    async with async_session() as db:
        res = await db.execute(
            select(ProspectSession)
            .order_by(desc(ProspectSession.created_at))
            .limit(limit)
        )
        return [_session_to_dict(s) for s in res.scalars().all()]


async def get_session_leads(session_id: str) -> List[dict]:
    from sqlalchemy import desc
    async with async_session() as db:
        res = await db.execute(
            select(ProspectLead)
            .where(ProspectLead.session_id == session_id)
            .order_by(desc(ProspectLead.icp_score))
        )
        return [_lead_to_dict(l) for l in res.scalars().all()]


async def get_all_pending_leads() -> List[dict]:
    from sqlalchemy import desc, or_
    async with async_session() as db:
        res = await db.execute(
            select(ProspectLead)
            .where(or_(ProspectLead.status == "pending", ProspectLead.status == "created"))
            .order_by(desc(ProspectLead.icp_score))
        )
        return [_lead_to_dict(l) for l in res.scalars().all()]


# ---------------------------------------------------------------------------
# Ações do usuário
# ---------------------------------------------------------------------------

async def approve_lead(lead_id: str) -> dict:
    from modules.crm.service.pipedrive_service import pipedrive_service

    async with async_session() as db:
        res = await db.execute(select(ProspectLead).where(ProspectLead.id == lead_id))
        lead = res.scalars().first()

        if not lead:
            raise ValueError(f"Lead não encontrado: {lead_id}")
        if lead.status != "pending":
            raise ValueError(f"Lead já processado: {lead.status}")

        from core.config import settings
        
        pipedrive_id = lead.pipedrive_org_id
        
        if pipedrive_id:
            # Empresa já existe no Pipedrive — apenas troca o dono e atualiza dados
            success = await pipedrive_service.update_organization(pipedrive_id, {
                "owner_id": settings.PIPEDRIVE_USER_ID,
                "name": lead.name,
                "domain": lead.domain,
                "address": lead.address
            })
            if not success:
                log.warning("prospect.lead.owner_transfer_failed", lead=lead.name, pipedrive_id=pipedrive_id)
        else:
            # Empresa nova — cria no Pipedrive
            pipedrive_id = await pipedrive_service.create_organization({
                "name": lead.name,
                "address": lead.address,
                "domain": lead.domain,
                "owner_id": settings.PIPEDRIVE_USER_ID
            })

        # 3. Criação da Organização Local (Para o Drawer já ter domínio, logo, etc.)
        from models import Organization
        stmt = select(Organization).where(Organization.pipedrive_id == pipedrive_id)
        res = await db.execute(stmt)
        local_org = res.scalars().first()

        if not local_org:
            # Tenta achar por nome (evitar duplicata se já existir sem Pipedrive ID)
            stmt_name = select(Organization).where(func.lower(Organization.name) == lead.name.lower())
            res_name = await db.execute(stmt_name)
            local_org = res_name.scalars().first()

        if not local_org:
            local_org = Organization(
                pipedrive_id=pipedrive_id,
                name=lead.name,
                domain=lead.domain,
                logo_url=lead.logo_url,
                linkedin_url=lead.linkedin_url,
                address=lead.address,
                icp_score=lead.icp_score,
                icp_tier=lead.icp_tier,
                source="prospecting"
            )
            db.add(local_org)
        else:
            # Atualiza dados se já existir e vincula ID se faltar
            local_org.pipedrive_id = pipedrive_id
            local_org.domain = lead.domain or local_org.domain
            local_org.logo_url = lead.logo_url or local_org.logo_url
            local_org.linkedin_url = lead.linkedin_url or local_org.linkedin_url
            local_org.address = lead.address or local_org.address
            local_org.icp_score = lead.icp_score
            local_org.icp_tier = lead.icp_tier
            local_org.logo_url = lead.logo_url
            local_org.linkedin_url = lead.linkedin_url
            local_org.address = lead.address
            local_org.icp_score = lead.icp_score
            local_org.icp_tier = lead.icp_tier

        await db.flush()

        # 4. Criação do Negócio (Deal) vinculado à empresa
        deal_id = None
        if pipedrive_id:
            try:
                log.info("prospect.deal.creating", lead=lead.name, org_id=pipedrive_id)
                deal_id = await pipedrive_service.create_deal(
                    title=f"Negócio - {lead.name}",
                    org_id=pipedrive_id,
                    stage_name="Entrada"
                )
                if not deal_id:
                    # Fallback: sem estágio específico, Pipedrive usa o primeiro da pipeline padrão
                    log.warning("prospect.deal.trying_fallback_no_stage", lead=lead.name)
                    deal_id = await pipedrive_service.create_deal(
                        title=f"Negócio - {lead.name}",
                        org_id=pipedrive_id,
                        stage_name=None
                    )
            except Exception as de:
                log.error("prospect.deal.error", error=str(de), lead=lead.name)

        # 5. Atualiza o lead com os IDs gerados
        lead.status = "created"
        lead.pipedrive_created_id = pipedrive_id
        lead.pipedrive_deal_id = deal_id
        
        await db.commit()
        log.info("prospect.lead.approved_full", name=lead.name, org_id=pipedrive_id, deal_id=deal_id)

        log.info("prospect.lead.approved", lead=lead.name, pipedrive_id=pipedrive_id, deal_id=deal_id)
        return {"status": "created", "lead_id": lead_id, "company_name": lead.name, "pipedrive_id": pipedrive_id, "deal_id": deal_id}


async def reject_lead(lead_id: str) -> dict:
    async with async_session() as db:
        res = await db.execute(select(ProspectLead).where(ProspectLead.id == lead_id))
        lead = res.scalars().first()

        if not lead:
            raise ValueError(f"Lead não encontrado: {lead_id}")

        lead.status = "rejected"

        # Marca a org local como excluída (não deleta, para preservar o dedup futuro)
        org_res = await db.execute(select(Organization).where(Organization.name == lead.name))
        org = org_res.scalars().first()
        if org:
            org.is_excluded = 1

        await db.commit()

        return {"status": "rejected", "lead_id": lead_id}


async def clear_prospecting_data() -> dict:
    """Limpa TODOS os dados de prospecção (sessões e leads)."""
    from sqlalchemy import delete
    async with async_session() as db:
        await db.execute(delete(ProspectLead))
        await db.execute(delete(ProspectSession))
        await db.commit()
    log.info("prospect.data.cleared")
    return {"status": "cleared", "message": "Todos os dados de prospecção foram removidos."}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _lead_exists_in_session(session_id: str, company_name: str) -> bool:
    from sqlalchemy import func
    async with async_session() as db:
        res = await db.execute(
            select(ProspectLead).where(
                ProspectLead.session_id == session_id,
                func.lower(ProspectLead.name) == company_name.lower(),
                ProspectLead.status != "rejected",
            )
        )
        return res.scalars().first() is not None


async def _lead_already_processed(company_name: str, domain: Optional[str] = None) -> bool:
    """Verifica se a empresa já foi aprovada ou rejeitada em qualquer sessão anterior."""
    from sqlalchemy import func, or_
    async with async_session() as db:
        name_cond = func.lower(ProspectLead.name) == company_name.lower()
        if domain:
            cond = or_(name_cond, ProspectLead.domain == domain)
        else:
            cond = name_cond
        res = await db.execute(
            select(ProspectLead).where(
                ProspectLead.status.in_(["rejected", "created"]),
                cond,
            )
        )
        return res.scalars().first() is not None


async def _is_org_excluded(company_name: str, domain: Optional[str] = None) -> bool:
    """Verifica se a empresa foi descartada via Organization.is_excluded."""
    from sqlalchemy import func, or_
    async with async_session() as db:
        name_cond = func.lower(Organization.name) == company_name.lower()
        if domain:
            cond = or_(name_cond, Organization.domain == domain)
        else:
            cond = name_cond
        res = await db.execute(
            select(Organization).where(Organization.is_excluded == 1, cond)
        )
        return res.scalars().first() is not None


async def _finish_session(session_id: str, found: int, error: Optional[str] = None) -> None:
    async with async_session() as db:
        res = await db.execute(
            select(ProspectSession).where(ProspectSession.id == session_id)
        )
        sess = res.scalars().first()
        if sess:
            sess.status = "failed" if error else "completed"
            sess.total_found = found
            sess.completed_at = datetime.now(timezone.utc)
            if error:
                sess.error_message = error
            await db.commit()


def _extract_company_name(title: str) -> str:
    if not title:
        return ""
    name = title.replace("| LinkedIn", "").replace("- LinkedIn", "").strip()
    if "|" in name:
        name = name.split("|")[0].strip()
    if " - " in name:
        name = name.split(" - ")[0].strip()
    return name[:120].strip()


def _extract_domain(body: str) -> Optional[str]:
    matches = re.findall(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z]{2,6})', body)
    for m in matches:
        if not any(s in m for s in ["linkedin", "facebook", "instagram", "google", "twitter"]):
            return m
    return None


def _session_to_dict(sess: ProspectSession) -> dict:
    return {
        "id": sess.id,
        "status": sess.status,
        "lat": sess.lat,
        "lng": sess.lng,
        "radius_km": sess.radius_km,
        "city_name": sess.city_name,
        "segments_searched": sess.segments_searched or [],
        "total_found": sess.total_found,
        "created_at": sess.created_at.isoformat() if sess.created_at else None,
        "completed_at": sess.completed_at.isoformat() if sess.completed_at else None,
        "error_message": sess.error_message,
    }


def _lead_to_dict(lead: ProspectLead) -> dict:
    return {
        "id": lead.id,
        "name": lead.name,
        "cnpj": lead.cnpj,
        "domain": lead.domain,
        "logo_url": lead.logo_url,
        "segment": lead.segment,
        "size_label": lead.size_label,
        "employee_count": lead.employee_count,
        "exports": bool(lead.exports),
        "linkedin_url": lead.linkedin_url,
        "description": lead.description,
        "contacts": lead.contacts or [],
        "icp_score": lead.icp_score,
        "icp_tier": lead.icp_tier,
        "icp_reasons": lead.icp_reasons or [],
        "icp_penalties": lead.icp_penalties or [],
        "icp_recommendation": lead.icp_recommendation,
        "outreach_angle": lead.outreach_angle,
        "relevance_signal": lead.relevance_signal,
        "pipedrive_status": lead.pipedrive_status,
        "pipedrive_org_id": lead.pipedrive_org_id,
        "pipedrive_last_activity": (
            lead.pipedrive_last_activity.isoformat() if lead.pipedrive_last_activity else None
        ),
        "pipedrive_deal_info": lead.pipedrive_deal_info,
        "lat": lead.lat,
        "lng": lead.lng,
        "status": lead.status,
        "pipedrive_created_id": lead.pipedrive_created_id,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
    }
