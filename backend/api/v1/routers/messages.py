"""
api.v1.routers.messages
========================
Endpoints para leitura e sincronização do cache de conversas com contatos externos.

O cache é populado automaticamente pelo agente toda vez que ele busca mensagens
via whatsapp_get_messages ou email_get_contact_history. Na inicialização do
sistema, o cache é sincronizado para contatos já monitorados.

Rotas:
    GET  /messages/contacts                   → lista de contatos rastreados
    GET  /messages/conversation               → mensagens de um contato específico
    POST /messages/sync/{contact_identifier}  → re-sincroniza um contato
"""
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.infra.database import get_db
from core.infra.http_client import get_http_client
from core.observability.logging_config import get_logger
from models.communication.contact_cache import (
    CHANNEL_WHATSAPP,
    ContactConversationCache,
)
from models.people.employee import Employee
from models.organization.organization import Organization

log = get_logger(__name__)

router = APIRouter()

# Pré-compilados para evitar recompilação em loops hot-path
_RE_STRIP_SUFFIX = re.compile(r'\s*-\s*\w+$')
_RE_NON_ALPHA = re.compile(r'[^a-z\s]')
_RE_NON_DIGIT = re.compile(r'\D')


def _normalize_contact_name(name: str) -> str:
    """Normaliza nome para matching fuzzy: minúsculas, sem acentos, sem sufixos comuns."""
    if not name:
        return ""
    normalized = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII').lower()
    normalized = _RE_STRIP_SUFFIX.sub('', normalized)
    normalized = _RE_NON_ALPHA.sub('', normalized)
    return " ".join(normalized.split())


def _find_profile_pic(
    identifier: str,
    contact_name: Optional[str],
    employees: List[Tuple],
    phone_index: Dict[str, str],
    email_index: Dict[str, str],
    normalized_name_index: Dict[str, str],
) -> Optional[str]:
    """Resolve foto de perfil de um contato por e-mail, telefone ou nome normalizado."""
    id_lower = identifier.lower()
    id_digits = _RE_NON_DIGIT.sub('', identifier)

    # 1. Correspondência exata por e-mail
    if pic := email_index.get(id_lower):
        return pic

    # 2. Correspondência por sufixo de telefone (últimos 8 dígitos)
    if id_digits and len(id_digits) >= 8:
        if pic := phone_index.get(id_digits[-8:]):
            return pic

    # 3. Fallback por nome normalizado
    if contact_name:
        if pic := normalized_name_index.get(_normalize_contact_name(contact_name)):
            return pic

    return None


@router.get("/contacts")
async def list_tracked_contacts(
    channel: Optional[str] = Query(None, description="Filtrar por canal: 'whatsapp' ou 'email'"),
    org_id: Optional[int] = Query(None, description="Filtrar pela empresa selecionada (pipedrive_id ou id interno)"),
    db: AsyncSession = Depends(get_db),
):
    """Lista contatos com conversas cacheadas. Filtrado por org_id quando informado.
    
    O frontend envia o pipedrive_id como org_id. Este endpoint resolve para o id
    interno do banco e busca por ambos para cobrir caches antigos e novos.
    """
    stmt = select(ContactConversationCache).order_by(desc(ContactConversationCache.fetched_at))
    if channel:
        stmt = stmt.where(ContactConversationCache.channel == channel)
    if org_id is not None:
        # Resolve pipedrive_id → internal id (o frontend envia pipedrive_id)
        possible_ids = {org_id}
        org_result = await db.execute(
            select(Organization.id, Organization.pipedrive_id).where(
                or_(Organization.id == org_id, Organization.pipedrive_id == org_id)
            )
        )
        for row in org_result.all():
            if row.id is not None:
                possible_ids.add(row.id)
            if row.pipedrive_id is not None:
                possible_ids.add(row.pipedrive_id)
        stmt = stmt.where(ContactConversationCache.org_id.in_(possible_ids))

    result = await db.execute(stmt)
    entries = result.scalars().all()

    profile_pics: Dict[str, str] = {}
    if entries:
        emp_stmt = select(
            Employee.name, Employee.email, Employee.phone,
            Employee.whatsapp_number, Employee.profile_pic,
        ).where(Employee.profile_pic.isnot(None))
        if org_id is not None:
            emp_stmt = emp_stmt.where(
                Employee.company_id.in_(
                    select(Organization.id).where(
                        or_(Organization.id == org_id, Organization.pipedrive_id == org_id)
                    )
                )
            )

        emp_result = await db.execute(emp_stmt)
        employees = emp_result.all()

        # Índices O(1) construídos uma única vez fora do loop de contatos
        email_idx: Dict[str, str] = {}
        phone_idx: Dict[str, str] = {}
        name_idx: Dict[str, str] = {}
        for emp_name, emp_email, emp_phone, emp_whatsapp, emp_pic in employees:
            if not emp_pic:
                continue
            if emp_email:
                email_idx[emp_email.lower()] = emp_pic
            for raw in (emp_phone, emp_whatsapp):
                digits = _RE_NON_DIGIT.sub('', raw or '')
                if len(digits) >= 8:
                    phone_idx[digits[-8:]] = emp_pic
            if emp_name:
                norm = _normalize_contact_name(emp_name)
                if norm:
                    name_idx[norm] = emp_pic

        for e in entries:
            pic = _find_profile_pic(
                e.contact_identifier, e.contact_name,
                employees, phone_idx, email_idx, name_idx,
            )
            if pic:
                profile_pics[e.contact_identifier] = pic

    # Buscar logo_url e domain das empresas para fallback de avatar na UI
    org_logos: Dict[int, str] = {}
    org_domains: Dict[int, str] = {}
    org_ids = {e.org_id for e in entries if e.org_id is not None}
    if org_ids:
        org_stmt = select(Organization.id, Organization.pipedrive_id, Organization.logo_url, Organization.domain).where(
            or_(Organization.id.in_(org_ids), Organization.pipedrive_id.in_(org_ids))
        )
        org_rows = await db.execute(org_stmt)
        for oid, pd_id, logo, dom in org_rows.all():
            if logo:
                if oid is not None:
                    org_logos[oid] = logo
                if pd_id is not None:
                    org_logos[pd_id] = logo
            if dom:
                if oid is not None:
                    org_domains[oid] = dom
                if pd_id is not None:
                    org_domains[pd_id] = dom

    return {
        "contacts": [
            {
                "contact_identifier": e.contact_identifier,
                "contact_name": e.contact_name,
                "channel": e.channel,
                "org_name": e.org_name,
                "org_id": e.org_id,
                "message_count": e.message_count,
                "fetched_at": e.fetched_at.isoformat() if e.fetched_at else None,
                "last_message_preview": e.last_message_preview,
                "chat_id": e.chat_id,
                "has_unread": bool(e.has_unread),
                "is_key_contact": bool(e.is_key_contact),
                "profile_pic": profile_pics.get(e.contact_identifier),
                "org_logo": org_logos.get(e.org_id) if e.org_id is not None else None,
                "org_domain": org_domains.get(e.org_id) if e.org_id is not None else None,
            }
            for e in entries
        ],
        "total": len(entries),
        "unread_count": sum(1 for e in entries if e.has_unread),
    }


@router.get("/conversation")
async def get_conversation(
    contact_identifier: str = Query(..., description="Telefone (digits) ou e-mail do contato"),
    channel: str = Query(..., description="'whatsapp' ou 'email'"),
    db: AsyncSession = Depends(get_db),
):
    """Retorna as mensagens cacheadas de um contato específico."""
    result = await db.execute(
        select(ContactConversationCache).where(
            ContactConversationCache.contact_identifier == contact_identifier,
            ContactConversationCache.channel == channel,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Conversa não encontrada no cache.")

    return {
        "contact_identifier": entry.contact_identifier,
        "contact_name": entry.contact_name,
        "channel": entry.channel,
        "org_name": entry.org_name,
        "org_id": entry.org_id,
        "chat_id": entry.chat_id,
        "messages": entry.get_messages(),
        "message_count": entry.message_count,
        "fetched_at": entry.fetched_at.isoformat() if entry.fetched_at else None,
    }


@router.patch("/read")
async def mark_as_read(
    contact_identifier: str = Query(...),
    channel: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Marca uma conversa como lida (has_unread=0). Chamado quando o usuário abre a conversa na UI."""
    result = await db.execute(
        select(ContactConversationCache).where(
            ContactConversationCache.contact_identifier == contact_identifier,
            ContactConversationCache.channel == channel,
        )
    )
    entry = result.scalar_one_or_none()
    if entry:
        entry.has_unread = 0
        await db.commit()
    return {"ok": True}


@router.post("/sync/{contact_identifier}")
async def sync_contact(
    contact_identifier: str,
    channel: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-sincroniza as mensagens de um contato WhatsApp contra o serviço externo.
    Apenas WhatsApp suporta sync manual aqui; email usa o trigger service.
    """
    if channel != CHANNEL_WHATSAPP:
        raise HTTPException(status_code=400, detail="Sync manual só disponível para WhatsApp.")

    result = await db.execute(
        select(ContactConversationCache).where(
            ContactConversationCache.contact_identifier == contact_identifier,
            ContactConversationCache.channel == CHANNEL_WHATSAPP,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry or not entry.chat_id:
        raise HTTPException(status_code=404, detail="Contato não encontrado ou sem chat_id registrado.")

    try:
        from modules.agent.service.tools._constants import WA_BASE
        from modules.agent.service.tools._message_cache import cache_wa_messages

        client = get_http_client()
        r = await client.get(
            f"{WA_BASE}/chats/{entry.chat_id}/messages",
            params={"limit": 100},
            timeout=15.0,
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"WhatsApp service retornou HTTP {r.status_code}")
        msgs = r.json()
        if isinstance(msgs, dict):
            msgs = msgs.get("messages") or msgs.get("data") or []

        await cache_wa_messages(
            contact_identifier=contact_identifier,
            contact_name=entry.contact_name,
            org_id=entry.org_id,
            org_name=entry.org_name,
            chat_id=entry.chat_id,
            raw_messages=msgs,
        )
        return {"ok": True, "synced": len(msgs), "contact": entry.contact_name}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("messages.sync.failed", contact=contact_identifier, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
