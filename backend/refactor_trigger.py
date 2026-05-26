import os

# New content for trigger_service.py
TRIGGER_SERVICE_CONTENT = '''"""
trigger_service.py — Gatilhos Autônomos de Resposta de Clientes (ARQ Worker version)

Monitora em background os canais de comunicação (Email + WhatsApp) em busca de
novas respostas de clientes. Quando detectada, dispara o workflow do agente em
modo "sugerir + aprovar".

Esta versão foi migrada para rodar exclusivamente como cron_jobs no ARQ Worker,
liberando o lifespan do FastAPI e usando Redis para compartilhar o estado pendente.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from core.config import settings
from core.observability.logging_config import get_logger
from models.conversation import ActivityLog

log = get_logger(__name__)

EMAIL_POLL_INTERVAL_SEC = 120   # 2 minutos
WA_POLL_INTERVAL_SEC = 60       # 1 minuto

QUIET_HOURS_START: int = int(getattr(settings, "TRIGGER_QUIET_START", 22))  # 22h
QUIET_HOURS_END: int   = int(getattr(settings, "TRIGGER_QUIET_END",   7))   #  7h

def is_quiet_hours() -> bool:
    hour = datetime.now().hour
    if QUIET_HOURS_START > QUIET_HOURS_END:
        return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END
    else:
        return QUIET_HOURS_START <= hour < QUIET_HOURS_END

# O estado de "pause" agora será mantido no Redis para que a API controle o worker
async def is_service_paused(redis) -> bool:
    val = await redis.get("trigger_service_paused")
    return val == b"1"

async def pause_service(redis) -> str:
    await redis.set("trigger_service_paused", "1")
    log.info("trigger_service.paused_by_user")
    return "paused"

async def resume_service(redis) -> str:
    await redis.delete("trigger_service_paused")
    log.info("trigger_service.resumed_by_user")
    return "resumed"

async def service_status(redis) -> dict:
    quiet = is_quiet_hours()
    paused = await is_service_paused(redis)
    return {
        "paused": paused,
        "quiet_hours": quiet,
        "quiet_window": f"{QUIET_HOURS_START:02d}h–{QUIET_HOURS_END:02d}h",
        "active": not paused and not quiet,
    }

EMAIL_SCAN_LIMIT = 15
WA_CHATS_LIMIT = 30

_last_email_check: float = 0.0
_last_wa_check: float = 0.0

def _make_trigger(
    *,
    trigger_id: str,
    channel: str,
    org_id: Optional[int],
    org_name: str,
    contact_name: str,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
    message_preview: str,
    full_message: str,
    subject: Optional[str] = None,
    entry_id: Optional[str] = None,
    in_reply_to_activity_id: Optional[int] = None,
) -> Dict:
    return {
        "trigger_id": trigger_id,
        "channel": channel,
        "org_id": org_id,
        "org_name": org_name,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "message_preview": message_preview[:300],
        "full_message": full_message,
        "subject": subject,
        "entry_id": entry_id,
        "in_reply_to_activity_id": in_reply_to_activity_id,
        "detected_at": datetime.utcnow().isoformat(),
        "status": "pending",
        "suggested_plan": None,
        "analysis": None,
    }

async def get_pending_triggers(redis) -> List[Dict]:
    """Retorna todos os triggers pendentes salvos no Redis."""
    triggers_hash = await redis.hgetall("pending_triggers")
    triggers = []
    for k, v in triggers_hash.items():
        try:
            t = json.loads(v)
            if t.get("status") in ("pending", "suggested", "processing"):
                triggers.append(t)
        except Exception:
            pass
    return triggers

async def get_trigger(redis, trigger_id: str) -> Optional[Dict]:
    val = await redis.hget("pending_triggers", trigger_id)
    if val:
        return json.loads(val)
    return None

async def dismiss_trigger(redis, trigger_id: str) -> bool:
    t = await get_trigger(redis, trigger_id)
    if t:
        t["status"] = "dismissed"
        await redis.hset("pending_triggers", trigger_id, json.dumps(t, ensure_ascii=False))
        await redis.publish("trigger_events", json.dumps({"type": "trigger_update", "trigger": t}, ensure_ascii=False))
        return True
    return False

async def mark_trigger_approved(redis, trigger_id: str) -> bool:
    t = await get_trigger(redis, trigger_id)
    if t:
        t["status"] = "approved"
        await redis.hset("pending_triggers", trigger_id, json.dumps(t, ensure_ascii=False))
        await redis.publish("trigger_events", json.dumps({"type": "trigger_update", "trigger": t}, ensure_ascii=False))
        return True
    return False

async def _notify_trigger(redis, trigger: Dict):
    await redis.publish("trigger_events", json.dumps({"type": "trigger_update", "trigger": trigger}, ensure_ascii=False))


# =============================================================================
# DETECÇÃO DE EMAILS RECEBIDOS
# =============================================================================

async def _detect_email_triggers(session, redis) -> List[Dict]:
    try:
        from modules.communication.service.email.client import EmailClient
        def _scan_in_thread() -> list:
            c = EmailClient(use_outlook_app=True)
            return c.scan_inbound_replies(max_results=EMAIL_SCAN_LIMIT) or []

        unread = await asyncio.to_thread(_scan_in_thread)
        if not unread: return []

        from sqlalchemy import select
        from models.conversation import ActivityLog
        sent_logs_result = await session.execute(
            select(ActivityLog)
            .where(ActivityLog.activity_type.in_(["email_sent", "email_reply_sent"]))
            .where(ActivityLog.status == "awaiting_reply")
            .order_by(ActivityLog.created_at.desc())
            .limit(100)
        )
        sent_logs = sent_logs_result.scalars().all()

        sent_index = {}
        for log_entry in sent_logs:
            payload = log_entry.payload or {}
            to_email = (payload.get("to_email") or "").lower()
            subj = (payload.get("subject") or "").lower().strip()
            base_subj = subj.replace("re: ", "").replace("re:", "").strip()
            key = f"{to_email}|{base_subj}"
            sent_index[key] = log_entry

        triggers_found = []
        for msg in unread:
            msg_id = msg.get("entryId") or msg.get("messageId") or ""
            is_processed = await redis.sismember("processed_email_ids", msg_id)
            if is_processed:
                continue

            sender = (msg.get("sender") or "").lower()
            subject = (msg.get("subject") or "")
            base_subj = subject.lower().replace("re: ", "").replace("re:", "").strip()

            matched_log = sent_index.get(f"{sender}|{base_subj}")
            if not matched_log:
                for key, entry in sent_index.items():
                    if base_subj and base_subj in key:
                        matched_log = entry
                        break

            org_id = matched_log.org_id if matched_log else None
            org_name = "Empresa desconhecida"

            if org_id:
                from models.organization import Organization
                org_result = await session.execute(select(Organization).where(Organization.id == org_id))
                org = org_result.scalar_one_or_none()
                if org: org_name = org.name

            contact_name = sender.split("@")[0].replace(".", " ").title() if "@" in sender else sender
            body_preview = (msg.get("body") or "")[:500]

            import uuid
            trigger = _make_trigger(
                trigger_id=str(uuid.uuid4()),
                channel="email",
                org_id=org_id,
                org_name=org_name,
                contact_name=contact_name,
                contact_email=sender,
                message_preview=body_preview[:200],
                full_message=body_preview,
                subject=subject,
                entry_id=msg.get("entryId"),
                in_reply_to_activity_id=matched_log.id if matched_log else None,
            )
            triggers_found.append(trigger)
            await redis.sadd("processed_email_ids", msg_id)
            # Expira o cache de processados apos 7 dias
            await redis.expire("processed_email_ids", 86400 * 7)

        return triggers_found

    except Exception as e:
        log.warning("trigger.email_scan_error", error=str(e)[:200])
        return []


# =============================================================================
# DETECÇÃO DE MENSAGENS WHATSAPP RECEBIDAS
# =============================================================================

async def _detect_wa_triggers(session, redis) -> List[Dict]:
    wa_base = settings.WHATSAPP_SERVICE_URL
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{wa_base}/chats")
            if resp.status_code != 200: return []
            chats_data = resp.json()
            chats = chats_data if isinstance(chats_data, list) else chats_data.get("chats", [])
    except Exception as e:
        log.debug("trigger.wa_chats_unavailable", error=str(e)[:100])
        return []

    try:
        from sqlalchemy import select
        from models.conversation import ActivityLog
        wa_logs_result = await session.execute(
            select(ActivityLog)
            .where(ActivityLog.activity_type == "whatsapp_sent")
            .order_by(ActivityLog.created_at.desc())
            .limit(100)
        )
        wa_logs = wa_logs_result.scalars().all()
        wa_index = {}
        for entry in wa_logs:
            payload = entry.payload or {}
            phone = (payload.get("to_phone") or payload.get("phone") or "").replace("+", "").replace(" ", "")
            if phone: wa_index[phone] = entry
    except Exception as e:
        log.warning("trigger.wa_log_query_error", error=str(e)[:200])
        wa_index = {}

    triggers_found = []
    now_ts = time.time()
    cutoff_ts = now_ts - (WA_POLL_INTERVAL_SEC * 2)

    for chat in chats[:WA_CHATS_LIMIT]:
        try:
            last_message = chat.get("lastMessage") or {}
            if last_message.get("fromMe", True): continue
            if last_message.get("timestamp", 0) < cutoff_ts: continue

            msg_id = last_message.get("id", {})
            if isinstance(msg_id, dict):
                msg_id = msg_id.get("_serialized") or str(msg_id)
            msg_id = str(msg_id)

            is_processed = await redis.sismember("processed_wa_ids", msg_id)
            if is_processed: continue

            chat_id = chat.get("id", {})
            if isinstance(chat_id, dict): phone = chat_id.get("user", "")
            else: phone = str(chat_id).split("@")[0]

            contact_name = chat.get("name") or chat.get("contact", {}).get("pushname") or phone
            body = last_message.get("body") or last_message.get("caption") or "[mídia]"

            phone_clean = phone.replace("+", "").replace(" ", "")
            matched_log = wa_index.get(phone_clean)
            if not matched_log:
                for key_phone, entry in wa_index.items():
                    if phone_clean.endswith(key_phone[-8:]) or key_phone.endswith(phone_clean[-8:]):
                        matched_log = entry
                        break

            org_id = matched_log.org_id if matched_log else None
            org_name = "Empresa desconhecida"

            if org_id:
                from sqlalchemy import select
                from models.organization import Organization
                org_result = await session.execute(select(Organization).where(Organization.id == org_id))
                org = org_result.scalar_one_or_none()
                if org: org_name = org.name

            import uuid
            trigger = _make_trigger(
                trigger_id=str(uuid.uuid4()),
                channel="whatsapp",
                org_id=org_id,
                org_name=org_name,
                contact_name=contact_name,
                contact_phone=phone,
                message_preview=body[:200],
                full_message=body,
                in_reply_to_activity_id=matched_log.id if matched_log else None,
            )
            triggers_found.append(trigger)
            await redis.sadd("processed_wa_ids", msg_id)
            await redis.expire("processed_wa_ids", 86400 * 7)
        except Exception as e:
            log.debug("trigger.wa_chat_parse_error", error=str(e)[:100])
            continue

    return triggers_found


# =============================================================================
# ANÁLISE ASSÍNCRONA DO TRIGGER PELO AGENTE
# =============================================================================

async def _analyze_trigger(trigger: Dict, session, redis) -> None:
    trigger_id = trigger["trigger_id"]
    trigger["status"] = "processing"
    await redis.hset("pending_triggers", trigger_id, json.dumps(trigger, ensure_ascii=False))

    try:
        from modules.ai.service.context.business_context import get_business_context_for_prompt
        from modules.ai.service.intent.prompts import INCOMING_RESPONSE_ANALYSIS_PROMPT
        from core.llm import ask_llm

        history_summary = "Sem histórico disponível."
        if trigger.get("org_id"):
            try:
                from modules.ai.service.pipeline.data_fetcher import fetch_contextual_data
                ctx = await fetch_contextual_data(
                    {"query_type": "agent_workflow", "data_scope": ["emails", "whatsapp", "activities"]},
                    trigger["org_id"],
                    session
                )
                deals = (ctx.get("pipedrive_details") or {}).get("deals", [])
                acts = (ctx.get("pipedrive_details") or {}).get("activities", [])
                parts = []
                if deals: parts.append(f"Deal ativo: {deals[0].get('title')} ({deals[0].get('stage_name')})")
                if acts: parts.append(f"Última atividade: {acts[0].get('subject')} ({'OK' if acts[0].get('done') else 'PEND'})")
                if parts: history_summary = " | ".join(parts)
            except Exception as he:
                log.debug("trigger.history_error", error=str(he)[:100])

        prompt = INCOMING_RESPONSE_ANALYSIS_PROMPT.format(
            business_context=await get_business_context_for_prompt(),
            company_name=trigger["org_name"],
            history_summary=history_summary,
            channel=trigger["channel"],
            incoming_message=trigger["full_message"],
        )

        from core.llm.base import LLMTier
        result = await ask_llm(prompt, json_mode=True, tier=LLMTier.STANDARD, cacheable=False)

        plan_data = {}
        if result and result.text:
            import json as _json
            try:
                plan_data = _json.loads(result.text)
            except Exception:
                import re
                m = re.search(r'\\{.*\\}', result.text, re.DOTALL)
                if m:
                    try: plan_data = _json.loads(m.group())
                    except Exception: plan_data = {}

        trigger["analysis"] = plan_data.get("analysis", "")
        trigger["sentiment"] = plan_data.get("sentiment", "neutral")
        trigger["client_intent"] = plan_data.get("client_intent", "")
        trigger["urgency"] = plan_data.get("urgency", "media")
        trigger["suggested_plan"] = plan_data.get("plan", [])
        trigger["status"] = "suggested"

        log.info("trigger.analyzed", trigger_id=trigger_id, sentiment=plan_data.get("sentiment"))
        await redis.hset("pending_triggers", trigger_id, json.dumps(trigger, ensure_ascii=False))
        await _notify_trigger(redis, trigger)

    except Exception as e:
        log.warning("trigger.analysis_failed", trigger_id=trigger_id, error=str(e)[:200])
        trigger["status"] = "suggested"
        trigger["analysis"] = "Análise automática indisponível. Verifique a mensagem manualmente."
        trigger["suggested_plan"] = []
        await redis.hset("pending_triggers", trigger_id, json.dumps(trigger, ensure_ascii=False))
        await _notify_trigger(redis, trigger)

async def _safe_analyze(trigger: Dict, redis) -> None:
    try:
        from core.infra.database import async_session
        async with async_session() as new_session:
            await _analyze_trigger(trigger, new_session, redis)
    except Exception as e:
        log.warning("trigger.safe_analyze_error", error=str(e)[:200])


# =============================================================================
# ARQ CRON JOBS
# =============================================================================

async def scan_email_triggers(ctx):
    redis = ctx['redis']
    if await is_service_paused(redis): return
    if is_quiet_hours(): return

    global _last_email_check
    now = time.monotonic()
    if now - _last_email_check < EMAIL_POLL_INTERVAL_SEC - 10:
        return
    _last_email_check = now

    log.info("trigger.cron.scan_email.start")
    try:
        from core.infra.database import async_session
        async with async_session() as session:
            new_triggers = await _detect_email_triggers(session, redis)
            for trigger in new_triggers:
                tid = trigger["trigger_id"]
                await redis.hset("pending_triggers", tid, json.dumps(trigger, ensure_ascii=False))
                asyncio.create_task(_safe_analyze(trigger, redis), name=f"trigger_analyze_{tid[:8]}")
    except Exception as e:
        log.warning("trigger.cron.email_error", error=str(e)[:200])


async def scan_whatsapp_triggers(ctx):
    redis = ctx['redis']
    if await is_service_paused(redis): return
    if is_quiet_hours(): return

    global _last_wa_check
    now = time.monotonic()
    if now - _last_wa_check < WA_POLL_INTERVAL_SEC - 10:
        return
    _last_wa_check = now

    log.info("trigger.cron.scan_wa.start")
    try:
        from core.infra.database import async_session
        async with async_session() as session:
            new_triggers = await _detect_wa_triggers(session, redis)
            for trigger in new_triggers:
                tid = trigger["trigger_id"]
                await redis.hset("pending_triggers", tid, json.dumps(trigger, ensure_ascii=False))
                asyncio.create_task(_safe_analyze(trigger, redis), name=f"trigger_analyze_{tid[:8]}")
    except Exception as e:
        log.warning("trigger.cron.wa_error", error=str(e)[:200])
'''

with open("backend/modules/triggers/service/trigger_service.py", "w", encoding="utf-8") as f:
    f.write(TRIGGER_SERVICE_CONTENT)

# Update backend/modules/triggers/router.py
ROUTER_CONTENT = '''"""
triggers — API de Gatilhos Autônomos

Endpoints para listar, dispensar e aprovar triggers detectados pelo TriggerService.
Também provê um endpoint SSE para notificações em tempo real.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .service.trigger_service import (
    get_pending_triggers,
    get_trigger,
    dismiss_trigger,
    mark_trigger_approved,
    pause_service,
    resume_service,
    service_status,
)
from core.infra.redis_config import redis_settings
from arq.connections import create_pool

router = APIRouter()

async def get_redis():
    return await create_pool(redis_settings)

@router.get("")
async def list_triggers():
    redis = await get_redis()
    triggers = await get_pending_triggers(redis)
    return {"count": len(triggers), "triggers": triggers}


@router.get("/{trigger_id}")
async def get_trigger_detail(trigger_id: str):
    redis = await get_redis()
    trigger = await get_trigger(redis, trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    return trigger


@router.post("/{trigger_id}/dismiss")
async def dismiss_trigger_endpoint(trigger_id: str):
    redis = await get_redis()
    if not await dismiss_trigger(redis, trigger_id):
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    return {"status": "dismissed", "trigger_id": trigger_id}


@router.post("/{trigger_id}/approve")
async def approve_trigger_endpoint(trigger_id: str):
    redis = await get_redis()
    trigger = await get_trigger(redis, trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    await mark_trigger_approved(redis, trigger_id)
    return {"status": "approved", "trigger_id": trigger_id, "suggested_plan": trigger.get("suggested_plan", [])}


@router.get("/stream/events")
async def trigger_events_stream(request: Request):
    """Server-Sent Events — notificações em tempo real de novos triggers assinando via Redis PubSub."""
    redis = await get_redis()
    
    async def event_generator() -> AsyncGenerator[str, None]:
        pubsub = redis.pubsub()
        await pubsub.subscribe("trigger_events")
        try:
            yield "data: {\\\"type\\\": \\\"connected\\\"}\\n\\n"
            pending = await get_pending_triggers(redis)
            if pending:
                for t in pending:
                    yield f"data: {json.dumps({'type': 'trigger_update', 'trigger': t})}\\n\\n"
            
            while True:
                if await request.is_disconnected():
                    break
                
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10.0)
                if message:
                    if isinstance(message['data'], bytes):
                        data = message['data'].decode('utf-8')
                    else:
                        data = message['data']
                    yield f"data: {data}\\n\\n"
                else:
                    yield "data: {\\\"type\\\": \\\"heartbeat\\\"}\\n\\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe("trigger_events")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/service/status")
async def get_service_status():
    redis = await get_redis()
    return await service_status(redis)


@router.post("/service/pause")
async def pause_trigger_service():
    redis = await get_redis()
    return {"status": await pause_service(redis)}


@router.post("/service/resume")
async def resume_trigger_service():
    redis = await get_redis()
    return {"status": await resume_service(redis)}
'''

with open("backend/modules/triggers/router.py", "w", encoding="utf-8") as f:
    f.write(ROUTER_CONTENT)

print("trigger files refactored.")
