"""
services.message_sync
=====================
Sincronização contínua de mensagens para contatos rastreados no cache.

Fluxo de vida:
  1. sync_tracked_contacts_on_startup() — executa uma vez no startup (com delay
     de 20s para o WA service inicializar) e depois chama o loop contínuo.
  2. _poll_loop() — loop infinito que re-fetcha mensagens a cada WA_POLL_SEC e
     detecta novas mensagens. Quando detecta mensagem nova de um contato-chave
     (Employee com seniority ≥ 3 ou temperature='hot'), marca has_unread=1 e
     registra no log estruturado para notificação via SSE/trigger service.

Apenas WhatsApp tem polling ativo aqui. Email já é coberto pelo TriggerService
(que varre o Outlook a cada 120s e cruza com ActivityLog).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from core.infra.database import async_session
from core.infra.http_client import get_http_client
from core.observability.logging_config import get_logger
from models.communication.contact_cache import CHANNEL_WHATSAPP

log = get_logger(__name__)

_STARTUP_DELAY_SEC = 20
_WA_POLL_SEC = 60            # intervalo de polling WhatsApp
_SYNC_MAX_AGE_DAYS = 14      # não poleia contatos sem acesso há mais de 14 dias
_WA_FETCH_LIMIT = 80


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _latest_ts(messages: list) -> int:
    """Retorna o maior timestamp de uma lista de mensagens WA. 0 se vazia."""
    if not messages:
        return 0
    return max((int(m.get("timestamp") or 0) for m in messages), default=0)


async def _is_key_contact(phone_or_email: str, channel: str) -> bool:
    """
    Verifica se o contato é um decisor/alta senioridade consultando a tabela Employee.
    Considerado chave: seniority >= 3 (gerente ou acima) OU temperature='hot'.
    """
    try:
        from models.people.employee import Employee
        from sqlalchemy import select, or_

        async with async_session() as session:
            if channel == CHANNEL_WHATSAPP:
                stmt = select(Employee).where(
                    or_(
                        Employee.whatsapp_number == phone_or_email,
                        Employee.phone == phone_or_email,
                        Employee.phone.like(f"%{phone_or_email[-8:]}"),  # últimos 8 dígitos
                    )
                )
            else:
                stmt = select(Employee).where(Employee.email == phone_or_email)

            result = await session.execute(stmt)
            emp = result.scalars().first()
            if not emp:
                return False
            return (emp.seniority or 0) >= 3 or emp.temperature == "hot"
    except Exception as e:
        log.debug("message_sync.is_key_contact_failed", contact=phone_or_email, error=str(e))
        return False


async def _sync_one_wa_contact(
    client: httpx.AsyncClient,
    wa_base: str,
    cache_wa_fn,
    contact,  # ContactConversationCache row
) -> bool:
    """
    Re-fetcha mensagens de um contato WhatsApp e atualiza o cache.
    Retorna True se novas mensagens foram detectadas.
    """
    if not contact.chat_id:
        return False
    try:
        r = await client.get(
            f"{wa_base}/chats/{contact.chat_id}/messages",
            params={"limit": _WA_FETCH_LIMIT},
            timeout=12.0,
        )
        if r.status_code != 200:
            return False

        msgs = r.json()
        if isinstance(msgs, dict):
            msgs = msgs.get("messages") or msgs.get("data") or []
        if not msgs:
            return False

        # Aplica o mesmo filtro de body que cache_wa_messages usa antes de comparar.
        # Sem isso, mensagens de mídia/sistema (sem body) têm timestamp mais alto que as
        # mensagens de texto no cache, causando has_new=True em todo ciclo mesmo sem
        # mensagens novas de texto.
        msgs_with_body = [
            m for m in msgs
            if (m.get("body") or m.get("text") or m.get("content") or "")
        ]

        cached_ts = _latest_ts(contact.get_messages())
        new_ts = _latest_ts(msgs_with_body)
        has_new = new_ts > cached_ts

        await cache_wa_fn(
            contact_identifier=contact.contact_identifier,
            contact_name=contact.contact_name,
            org_id=contact.org_id,
            org_name=contact.org_name,
            chat_id=contact.chat_id,
            raw_messages=msgs,
        )
        return has_new
    except Exception as e:
        log.warning("message_sync.poll.contact_error",
                    contact=contact.contact_name, error=str(e))
        return False


async def _mark_unread_and_notify(contact, is_key: bool) -> None:
    """Marca has_unread=1 no cache e loga para notificação.

    Guard: se has_unread já é 1, não reescreve nem loga de novo — evita spam
    de 'new_message_detected' em cada ciclo de polling para o mesmo contato.
    """
    try:
        from models.communication.contact_cache import ContactConversationCache
        from sqlalchemy import select

        async with async_session() as session:
            result = await session.execute(
                select(ContactConversationCache).where(
                    ContactConversationCache.contact_identifier == contact.contact_identifier,
                    ContactConversationCache.channel == contact.channel,
                )
            )
            entry = result.scalar_one_or_none()
            if not entry:
                return

            already_unread = bool(entry.has_unread)
            if not already_unread:
                entry.has_unread = 1
            if is_key and not entry.is_key_contact:
                entry.is_key_contact = 1

            if not already_unread or (is_key and not entry.is_key_contact):
                await session.commit()

        if not already_unread:
            log.info(
                "message_sync.new_message_detected",
                contact=contact.contact_name,
                org=contact.org_name,
                channel=contact.channel,
                is_key_contact=is_key,
            )
    except Exception as e:
        log.warning("message_sync.mark_unread_failed", error=str(e))


# ─── Loop contínuo ────────────────────────────────────────────────────────────

async def _poll_loop(wa_base: str, cache_wa_fn) -> None:
    """Loop infinito de polling de mensagens WhatsApp para contatos rastreados."""
    from models.communication.contact_cache import ContactConversationCache
    from sqlalchemy import select

    while True:
        await asyncio.sleep(_WA_POLL_SEC)

        try:
            cutoff = datetime.utcnow() - timedelta(days=_SYNC_MAX_AGE_DAYS)

            async with async_session() as session:
                result = await session.execute(
                    select(ContactConversationCache).where(
                        ContactConversationCache.channel == CHANNEL_WHATSAPP,
                        ContactConversationCache.fetched_at >= cutoff,
                    )
                )
                contacts = result.scalars().all()

            if not contacts:
                continue

            client = get_http_client()
            # Verifica se o WA service ainda está online
            try:
                st = await client.get(f"{wa_base}/status", timeout=5.0)
                st_data = st.json() if st.status_code == 200 else {}
                if not (st_data.get("isReady") or st_data.get("authenticated")):
                    log.warning("message_sync.poll.wa_not_ready")
                    continue
            except Exception:
                continue

            for contact in contacts:
                has_new = await _sync_one_wa_contact(client, wa_base, cache_wa_fn, contact)
                if has_new:
                    is_key = await _is_key_contact(contact.contact_identifier, CHANNEL_WHATSAPP)
                    await _mark_unread_and_notify(contact, is_key)
                await asyncio.sleep(0.4)  # throttle suave

        except Exception as e:
            log.warning("message_sync.poll.cycle_error", error=str(e))


# ─── Entrypoints públicos ──────────────────────────────────────────────────────

async def sync_tracked_contacts_on_startup() -> None:
    """
    Executa sync inicial no startup (delay=20s para o WA service inicializar)
    e depois dispara o loop de polling contínuo.
    """
    await asyncio.sleep(_STARTUP_DELAY_SEC)

    try:
        from models.communication.contact_cache import ContactConversationCache
        from modules.agent.service.tools._constants import WA_BASE
        from modules.agent.service.tools._message_cache import cache_wa_messages
        from sqlalchemy import select

        cutoff = datetime.utcnow() - timedelta(days=_SYNC_MAX_AGE_DAYS)

        async with async_session() as session:
            result = await session.execute(
                select(ContactConversationCache).where(
                    ContactConversationCache.channel == CHANNEL_WHATSAPP,
                    ContactConversationCache.fetched_at >= cutoff,
                )
            )
            contacts = result.scalars().all()

        if not contacts:
            log.info("message_sync.startup.no_contacts")
        else:
            log.info("message_sync.startup.begin", count=len(contacts))

            # Verifica se o WA service está acessível
            wa_ready = False
            client = get_http_client()
            try:
                st = await client.get(f"{WA_BASE}/status", timeout=5.0)
                st_data = st.json() if st.status_code == 200 else {}
                wa_ready = bool(st_data.get("isReady") or st_data.get("authenticated"))
            except Exception as e:
                log.warning("message_sync.startup.wa_unreachable", error=str(e))

            if wa_ready:
                synced = 0
                for contact in contacts:
                    has_new = await _sync_one_wa_contact(client, WA_BASE, cache_wa_messages, contact)
                    if has_new:
                        is_key = await _is_key_contact(contact.contact_identifier, CHANNEL_WHATSAPP)
                        await _mark_unread_and_notify(contact, is_key)
                        synced += 1
                    await asyncio.sleep(0.5)
                log.info("message_sync.startup.done", synced=synced, total=len(contacts))
            else:
                log.warning("message_sync.startup.wa_not_ready_skipping_initial_sync")

        # Inicia o loop contínuo (roda para sempre, gerenciado como background task)
        log.info("message_sync.poll_loop.starting", interval_sec=_WA_POLL_SEC)
        from modules.agent.service.tools._constants import WA_BASE
        from modules.agent.service.tools._message_cache import cache_wa_messages
        await _poll_loop(WA_BASE, cache_wa_messages)

    except Exception as e:
        log.warning("message_sync.startup.error", error=str(e))
