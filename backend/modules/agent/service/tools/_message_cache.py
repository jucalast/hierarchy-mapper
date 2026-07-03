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

from datetime import datetime, timedelta
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
    """
    Upsert inteligente do ContactConversationCache com mesclagem e deduplicação.
    Evita salvar duplicados se o agente e o trigger service buscarem o mesmo e-mail/msg.
    """
    from models.communication.contact_cache import ContactConversationCache, CHANNEL_EMAIL, CHANNEL_WHATSAPP
    from sqlalchemy import select

    async with async_session() as session:
        # Resolve org_id and org_name if they are not provided (None or 0)
        resolved_org_id = org_id
        resolved_org_name = org_name

        if not resolved_org_id or resolved_org_id == 0:
            from models.people.employee import Employee
            from models.organization.organization import Organization
            from sqlalchemy import or_
            
            conditions = []
            if channel == CHANNEL_WHATSAPP:
                clean_id = "".join(c for c in contact_identifier if c.isdigit())
                conditions.append(Employee.whatsapp_number == contact_identifier)
                conditions.append(Employee.phone == contact_identifier)
                if clean_id and len(clean_id) >= 8:
                    suffix = clean_id[-8:]
                    conditions.append(Employee.whatsapp_number.like(f"%{suffix}%"))
                    conditions.append(Employee.phone.like(f"%{suffix}%"))
            else:  # email
                conditions.append(Employee.email == contact_identifier)
            
            if contact_name:
                conditions.append(Employee.name == contact_name)
                conditions.append(Employee.name.like(f"%{contact_name}%"))

            if conditions:
                emp_result = await session.execute(
                    select(Employee)
                    .where(or_(*conditions))
                    .order_by(Employee.company_id.isnot(None).desc())
                )
                emp = emp_result.scalars().first()
                if emp and emp.company_id:
                    org_result = await session.execute(
                        select(Organization).where(Organization.id == emp.company_id)
                    )
                    org = org_result.scalar_one_or_none()
                    if org:
                        resolved_org_id = org.pipedrive_id or org.id
                        resolved_org_name = org.name

        result = await session.execute(
            select(ContactConversationCache).where(
                ContactConversationCache.contact_identifier == contact_identifier,
                ContactConversationCache.channel == channel,
            )
        )
        entry = result.scalar_one_or_none()

        # Lookup secundário: evita criar linha duplicada quando o mesmo contato
        # já existe sob um identificador diferente (WA: phone vs LID; Email: email vs @domínio).
        if not entry:
            from sqlalchemy import or_
            if channel == CHANNEL_WHATSAPP and contact_name and resolved_org_id:
                # Mesmo contato pode ter sido salvo como número de telefone ou LID do WA
                r2 = await session.execute(
                    select(ContactConversationCache).where(
                        ContactConversationCache.channel == channel,
                        ContactConversationCache.org_id == resolved_org_id,
                        ContactConversationCache.contact_name == contact_name,
                    )
                )
                entry = r2.scalar_one_or_none()
                if entry:
                    # Promove identificador: prefere número de telefone (<=13 dígitos) ao LID
                    _new_is_lid = "@lid" in contact_identifier or (
                        contact_identifier.isdigit() and len(contact_identifier) > 13
                    )
                    _cur_is_lid = "@lid" in (entry.contact_identifier or "") or (
                        (entry.contact_identifier or "").isdigit()
                        and len(entry.contact_identifier or "") > 13
                    )
                    if not _new_is_lid and _cur_is_lid:
                        entry.contact_identifier = contact_identifier

            elif channel == CHANNEL_EMAIL and resolved_org_id:
                # Email e domínio (@domain.com) do mesmo contato são a mesma conversa
                _domain = (
                    contact_identifier
                    if contact_identifier.startswith("@")
                    else (
                        "@" + contact_identifier.split("@")[1]
                        if "@" in contact_identifier
                        # bare domain sem @: "dva.com" → "@dva.com"
                        else ("@" + contact_identifier if "." in contact_identifier and " " not in contact_identifier else None)
                    )
                )
                if _domain:
                    r2 = await session.execute(
                        select(ContactConversationCache).where(
                            ContactConversationCache.channel == channel,
                            ContactConversationCache.org_id == resolved_org_id,
                            or_(
                                ContactConversationCache.contact_identifier == _domain,
                                ContactConversationCache.contact_identifier.like(f"%{_domain}"),
                            ),
                        )
                    )
                    entry = r2.scalar_one_or_none()
                    if entry:
                        # Promove para identificador de domínio se ainda for email específico
                        if not entry.contact_identifier.startswith("@") and contact_identifier.startswith("@"):
                            entry.contact_identifier = contact_identifier

        # Lógica de Mesclagem (Merge) e Deduplicação
        final_messages = messages
        if entry:
            existing = entry.get_messages()
            if existing:
                # Deduplicação por ID único do provedor.
                # Email: messageId (Message-ID RFC822, estável entre cópias físicas do
                # mesmo e-mail em pastas diferentes) tem prioridade sobre entryId (que o
                # Outlook gera um por cópia física, não por e-mail — cai para entryId só
                # em entradas de cache antigas que ainda não tinham messageId salvo).
                # WhatsApp usa id.
                def _get_id(m: dict):
                    if channel == CHANNEL_EMAIL:
                        return m.get("messageId") or m.get("entryId")
                    return m.get("id")

                # Mapa de mensagens existentes
                merged_map = {_get_id(m): m for m in existing if _get_id(m)}

                # Adiciona/Sobrescreve com as novas (mais frescas)
                for m in messages:
                    mid = _get_id(m)
                    if mid:
                        merged_map[mid] = m
                    else:
                        # Fallback se não houver ID (mensagens de sistema) — usa body como chave
                        b_key = m.get("body") or m.get("content") or ""
                        if b_key: merged_map[f"raw_{b_key[:50]}"] = m
                
                # Converte de volta para lista
                final_messages = list(merged_map.values())
                
                # Re-ordenar (Emails: data decrescente | WA: timestamp crescente)
                if channel == CHANNEL_EMAIL:
                    final_messages.sort(key=lambda x: x.get("date") or "", reverse=True)
                else:
                    final_messages.sort(key=lambda x: int(x.get("timestamp") or 0))
                
                # Limite de segurança (mantém as 100 mais recentes)
                final_messages = final_messages[:100]

        if entry:
            entry.set_messages(final_messages)
            entry.contact_name = contact_name
            if resolved_org_id:
                entry.org_id = resolved_org_id
            if resolved_org_name:
                entry.org_name = resolved_org_name
            if chat_id:
                entry.chat_id = chat_id
        else:
            entry = ContactConversationCache(
                contact_identifier=contact_identifier,
                contact_name=contact_name,
                channel=channel,
                org_id=resolved_org_id,
                org_name=resolved_org_name,
                chat_id=chat_id,
            )
            entry.set_messages(final_messages)
            session.add(entry)
            
        await session.commit()
        log.info("message_cache.merged", channel=channel, contact=contact_name, total=len(final_messages))


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
                "id": str(m.get("id", {}).get("_serialized") if isinstance(m.get("id"), dict) else m.get("id", "")),
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
        # Garante que campos vitais de e-mail existam para deduplicação
        clean_emails = []
        for e in emails:
            if not e.get("entryId"): continue
            clean_emails.append(e)
            
        if not clean_emails: return
        
        await _upsert_contact_cache(
            contact_identifier, contact_name, CHANNEL_EMAIL, clean_emails,
            org_id, org_name,
        )
    except Exception as e:
        log.warning("message_cache.email.failed", error=str(e))


async def get_cached_messages(
    contact_identifier: str,
    channel: str,
    max_age_minutes: Optional[int] = _CACHE_STALE_MINUTES,
) -> Optional[List[Dict[str, Any]]]:
    """
    Retorna mensagens do cache se existirem e não estiverem stale.
    Se max_age_minutes for None ou 0, ignora a idade (prioriza o banco).
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
            
            # Se max_age_minutes for None, confiamos plenamente no banco de dados
            if max_age_minutes is not None and max_age_minutes > 0:
                age = datetime.utcnow() - entry.fetched_at
                if age > timedelta(minutes=max_age_minutes):
                    return None
                    
            return entry.get_messages()
    except Exception as e:
        log.warning("message_cache.get.failed", error=str(e))
        return None
