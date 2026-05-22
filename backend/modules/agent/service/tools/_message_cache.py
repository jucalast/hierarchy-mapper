"""
modules.agent.service.tools._message_cache
==========================================
Helpers para persistir mensagens buscadas pelo agente no ContactConversationCache.

Funções públicas:
    cache_wa_messages    — salva snapshot de conversa WhatsApp
    cache_email_messages — salva snapshot de histórico de email
    get_cached_messages  — retorna snapshot salvo (None se ausente ou stale)

Chamado com asyncio.create_task() para não bloquear o executor do tool.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List, Optional

from core.infra.database import async_session
from core.observability.logging_config import get_logger
from models.communication.contact_cache import CHANNEL_EMAIL, CHANNEL_WHATSAPP

log = get_logger(__name__)

_CACHE_STALE_MINUTES = 10  # mensagens mais velhas que isso serão re-fetchadas pelo agente


async def _upsert_contact_cache(
    contact_identifier: str,
    contact_name: str,
    channel: str,
    messages: List[Dict[str, Any]],
    org_id: Optional[int],
    org_name: Optional[str],
    chat_id: Optional[str] = None,
) -> None:
    """Upsert genérico do ContactConversationCache. Compartilhado por WA e email."""
    from models.communication.contact_cache import ContactConversationCache
    from sqlalchemy import select

    async with async_session() as session:
        result = await session.execute(
            select(ContactConversationCache).where(
                ContactConversationCache.contact_identifier == contact_identifier,
                ContactConversationCache.channel == channel,
            )
        )
        entry = result.scalar_one_or_none()
        if entry:
            entry.set_messages(messages)
            entry.contact_name = contact_name
            if org_id:
                entry.org_id = org_id
            if org_name:
                entry.org_name = org_name
            if chat_id:
                entry.chat_id = chat_id
        else:
            entry = ContactConversationCache(
                contact_identifier=contact_identifier,
                contact_name=contact_name,
                channel=channel,
                org_id=org_id,
                org_name=org_name,
                chat_id=chat_id,
            )
            entry.set_messages(messages)
            session.add(entry)
        await session.commit()
        log.info("message_cache.saved", channel=channel, contact=contact_name, count=len(messages))


async def cache_wa_messages(
    contact_identifier: str,
    contact_name: str,
    org_id: Optional[int],
    org_name: Optional[str],
    chat_id: Optional[str],
    raw_messages: List[Dict[str, Any]],
) -> None:
    """Persiste mensagens brutas do WhatsApp. Upsert por (contact_identifier, channel)."""
    if not contact_identifier or not raw_messages:
        return
    try:
        clean_msgs = [
            {
                "body": m.get("body") or m.get("text") or m.get("content") or "",
                "fromMe": bool(m.get("fromMe")),
                "timestamp": m.get("timestamp") or 0,
                "id": str(m.get("id") or ""),
            }
            for m in raw_messages
            if (m.get("body") or m.get("text") or m.get("content") or "")
        ]
        if not clean_msgs:
            return
        await _upsert_contact_cache(
            contact_identifier, contact_name, CHANNEL_WHATSAPP, clean_msgs,
            org_id, org_name, chat_id,
        )
    except Exception as e:
        log.warning("message_cache.wa.failed", error=str(e))


async def cache_email_messages(
    contact_identifier: str,
    contact_name: str,
    org_id: Optional[int],
    org_name: Optional[str],
    emails: List[Dict[str, Any]],
) -> None:
    """Persiste emails buscados pelo agente. Upsert por (contact_identifier, channel)."""
    if not contact_identifier or not emails:
        return
    try:
        await _upsert_contact_cache(
            contact_identifier, contact_name, CHANNEL_EMAIL, emails,
            org_id, org_name,
        )
    except Exception as e:
        log.warning("message_cache.email.failed", error=str(e))


async def get_cached_messages(
    contact_identifier: str,
    channel: str,
    max_age_minutes: int = _CACHE_STALE_MINUTES,
) -> Optional[List[Dict[str, Any]]]:
    """
    Retorna mensagens do cache se existirem e não estiverem stale.
    Retorna None se ausente ou mais velhas que max_age_minutes.
    """
    try:
        from models.communication.contact_cache import ContactConversationCache
        from sqlalchemy import select

        async with async_session() as session:
            result = await session.execute(
                select(ContactConversationCache).where(
                    ContactConversationCache.contact_identifier == contact_identifier,
                    ContactConversationCache.channel == channel,
                )
            )
            entry = result.scalar_one_or_none()
            if not entry:
                return None
            age = datetime.utcnow() - entry.fetched_at
            if age > timedelta(minutes=max_age_minutes):
                return None
            return entry.get_messages()
    except Exception as e:
        log.warning("message_cache.get.failed", error=str(e))
        return None
