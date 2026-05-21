"""
trigger_service.py — Gatilhos Autônomos de Resposta de Clientes

Monitora em background os canais de comunicação (Email + WhatsApp) em busca de
novas respostas de clientes. Quando detectada, dispara o workflow do agente em
modo "sugerir + aprovar" — a resposta sugerida fica pendente de confirmação.

Uso (registrar no lifespan do FastAPI):
    from modules.triggers.service.trigger_service import TriggerService
    trigger = TriggerService()
    asyncio.create_task(trigger.start_polling())
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

# Intervalo de polling para cada canal
EMAIL_POLL_INTERVAL_SEC = 120   # 2 minutos
WA_POLL_INTERVAL_SEC = 60       # 1 minuto

# ── Horário de silêncio ───────────────────────────────────────────────────────
# Fora desse intervalo o polling não dispara nenhuma análise nem envio.
# Configurável por variável de ambiente: TRIGGER_QUIET_START / TRIGGER_QUIET_END
QUIET_HOURS_START: int = int(getattr(settings, "TRIGGER_QUIET_START", 22))  # 22h
QUIET_HOURS_END: int   = int(getattr(settings, "TRIGGER_QUIET_END",   7))   #  7h

# ── Kill switch em memória ────────────────────────────────────────────────────
# Pode ser alternado via POST /api/v1/trigger/pause e /resume sem reiniciar o servidor.
_service_paused: bool = False


def is_quiet_hours() -> bool:
    """Retorna True se o horário atual está dentro do período de silêncio."""
    hour = datetime.now().hour
    if QUIET_HOURS_START > QUIET_HOURS_END:
        # Período que cruza a meia-noite (ex: 22h → 7h)
        return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END
    else:
        return QUIET_HOURS_START <= hour < QUIET_HOURS_END


def pause_service() -> str:
    global _service_paused
    _service_paused = True
    log.info("trigger_service.paused_by_user")
    return "paused"


def resume_service() -> str:
    global _service_paused
    _service_paused = False
    log.info("trigger_service.resumed_by_user")
    return "resumed"


def service_status() -> dict:
    quiet = is_quiet_hours()
    return {
        "paused": _service_paused,
        "quiet_hours": quiet,
        "quiet_window": f"{QUIET_HOURS_START:02d}h–{QUIET_HOURS_END:02d}h",
        "active": not _service_paused and not quiet,
    }

# Quantos emails / chats escanear por ciclo
EMAIL_SCAN_LIMIT = 15
WA_CHATS_LIMIT = 30

# In-memory store de triggers detectados (também persistido via ActivityLog)
# key = trigger_id, value = TriggerEvent dict
_pending_triggers: Dict[str, Dict] = {}
_trigger_callbacks: List = []   # callables para notificar o frontend via SSE

# Marca o tempo da última verificação para cada canal
_last_email_check: float = 0.0
_last_wa_check: float = 0.0

# IDs de emails/mensagens já processados para evitar re-trigger
_processed_email_ids: set = set()
_processed_wa_ids: set = set()


# =============================================================================
# ESTRUTURA DE TRIGGER
# =============================================================================

def _make_trigger(
    *,
    trigger_id: str,
    channel: str,                   # "email" | "whatsapp"
    org_id: Optional[int],
    org_name: str,
    contact_name: str,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
    message_preview: str,
    full_message: str,
    subject: Optional[str] = None,
    entry_id: Optional[str] = None,  # email_entry_id para reply
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
        "status": "pending",       # pending → processing → suggested → approved/dismissed
        "suggested_plan": None,    # preenchido após análise do agente
        "analysis": None,
    }


# =============================================================================
# ACESSO AOS TRIGGERS
# =============================================================================

def get_pending_triggers() -> List[Dict]:
    """Retorna todos os triggers pendentes (status pending ou suggested)."""
    return [t for t in _pending_triggers.values() if t["status"] in ("pending", "suggested", "processing")]


def get_trigger(trigger_id: str) -> Optional[Dict]:
    return _pending_triggers.get(trigger_id)


def dismiss_trigger(trigger_id: str) -> bool:
    if trigger_id in _pending_triggers:
        _pending_triggers[trigger_id]["status"] = "dismissed"
        return True
    return False


def mark_trigger_approved(trigger_id: str) -> bool:
    if trigger_id in _pending_triggers:
        _pending_triggers[trigger_id]["status"] = "approved"
        return True
    return False


def register_trigger_callback(fn):
    """Registra uma função que será chamada quando um novo trigger for detectado."""
    _trigger_callbacks.append(fn)


def _notify_callbacks(trigger: Dict):
    for fn in _trigger_callbacks:
        try:
            if asyncio.iscoroutinefunction(fn):
                asyncio.create_task(fn(trigger))
            else:
                fn(trigger)
        except Exception as e:
            log.warning("trigger.callback_error", error=str(e))


# =============================================================================
# DETECÇÃO DE EMAILS RECEBIDOS
# =============================================================================

async def _detect_email_triggers(session) -> List[Dict]:
    """
    Varre a caixa de entrada do Outlook em busca de respostas a emails que o
    agente enviou. Cruza com ActivityLog para identificar org_id e contexto.
    """
    try:
        # Roda a chamada bloqueante do EmailClient em thread separada
        from modules.communication.service.email.client import EmailClient
        import concurrent.futures

        client = EmailClient(use_outlook_app=True)
        loop = asyncio.get_event_loop()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            unread = await loop.run_in_executor(
                pool,
                lambda: client.scan_inbound_replies(max_results=EMAIL_SCAN_LIMIT)
            )

        if not unread:
            return []

        # Busca ActivityLogs de emails enviados para fazer o match
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

        # Index por assunto (normalizado) e email do destinatário
        sent_index = {}
        for log_entry in sent_logs:
            payload = log_entry.payload or {}
            to_email = (payload.get("to_email") or "").lower()
            subj = (payload.get("subject") or "").lower().strip()
            # Remove "Re: " prefixo para normalizar
            base_subj = subj.replace("re: ", "").replace("re:", "").strip()
            key = f"{to_email}|{base_subj}"
            sent_index[key] = log_entry

        triggers_found = []
        for msg in unread:
            msg_id = msg.get("entryId") or msg.get("messageId") or ""
            if msg_id in _processed_email_ids:
                continue

            sender = (msg.get("sender") or "").lower()
            subject = (msg.get("subject") or "")
            # Normaliza assunto para match
            base_subj = subject.lower().replace("re: ", "").replace("re:", "").strip()

            # Tenta encontrar o ActivityLog correspondente
            matched_log = sent_index.get(f"{sender}|{base_subj}")

            # Se não encontrou por email exato, tenta só pelo assunto
            if not matched_log:
                for key, entry in sent_index.items():
                    if base_subj and base_subj in key:
                        matched_log = entry
                        break

            org_id = matched_log.org_id if matched_log else None
            org_name = "Empresa desconhecida"

            if org_id:
                # Busca nome da org
                from models.organization import Organization
                org_result = await session.execute(
                    select(Organization).where(Organization.id == org_id)
                )
                org = org_result.scalar_one_or_none()
                if org:
                    org_name = org.name

            # Extrai nome do remetente (parte antes do @)
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
            _processed_email_ids.add(msg_id)

        return triggers_found

    except Exception as e:
        log.warning("trigger.email_scan_error", error=str(e)[:200])
        return []


# =============================================================================
# DETECÇÃO DE MENSAGENS WHATSAPP RECEBIDAS
# =============================================================================

async def _detect_wa_triggers(session) -> List[Dict]:
    """
    Consulta o WPP Connect por mensagens novas (fromMe=False) em chats ativos.
    Cruza com ActivityLog de whatsapp_sent para identificar contexto.
    """
    wa_base = settings.WHATSAPP_SERVICE_URL

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{wa_base}/chats")
            if resp.status_code != 200:
                return []

            chats_data = resp.json()
            chats = chats_data if isinstance(chats_data, list) else chats_data.get("chats", [])

    except Exception as e:
        log.debug("trigger.wa_chats_unavailable", error=str(e)[:100])
        return []

    # Busca ActivityLogs de WA enviados para contextualizar
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

        # Index por número de telefone
        wa_index: Dict[str, ActivityLog] = {}
        for entry in wa_logs:
            payload = entry.payload or {}
            phone = (payload.get("to_phone") or payload.get("phone") or "").replace("+", "").replace(" ", "")
            if phone:
                wa_index[phone] = entry
    except Exception as e:
        log.warning("trigger.wa_log_query_error", error=str(e)[:200])
        wa_index = {}

    triggers_found = []
    now_ts = time.time()
    # Considera mensagens recebidas nos últimos WA_POLL_INTERVAL_SEC * 2 segundos
    cutoff_ts = now_ts - (WA_POLL_INTERVAL_SEC * 2)

    for chat in chats[:WA_CHATS_LIMIT]:
        try:
            last_message = chat.get("lastMessage") or {}
            from_me = last_message.get("fromMe", True)
            msg_ts = last_message.get("timestamp", 0)

            # Só processa mensagens recebidas (não enviadas por nós)
            if from_me:
                continue

            # Só mensagens recentes
            if msg_ts < cutoff_ts:
                continue

            msg_id = last_message.get("id", {})
            if isinstance(msg_id, dict):
                msg_id = msg_id.get("_serialized") or str(msg_id)
            msg_id = str(msg_id)

            if msg_id in _processed_wa_ids:
                continue

            # Extrai dados do chat
            chat_id = chat.get("id", {})
            if isinstance(chat_id, dict):
                phone = chat_id.get("user", "")
            else:
                phone = str(chat_id).split("@")[0]

            contact_name = chat.get("name") or chat.get("contact", {}).get("pushname") or phone
            body = last_message.get("body") or last_message.get("caption") or "[mídia]"

            # Match com ActivityLog
            phone_clean = phone.replace("+", "").replace(" ", "")
            matched_log = wa_index.get(phone_clean)
            if not matched_log:
                # Tenta match sem DDI
                for key_phone, entry in wa_index.items():
                    if phone_clean.endswith(key_phone[-8:]) or key_phone.endswith(phone_clean[-8:]):
                        matched_log = entry
                        break

            org_id = matched_log.org_id if matched_log else None
            org_name = "Empresa desconhecida"

            if org_id:
                from sqlalchemy import select
                from models.organization import Organization
                org_result = await session.execute(
                    select(Organization).where(Organization.id == org_id)
                )
                org = org_result.scalar_one_or_none()
                if org:
                    org_name = org.name

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
            _processed_wa_ids.add(msg_id)

        except Exception as e:
            log.debug("trigger.wa_chat_parse_error", error=str(e)[:100])
            continue

    return triggers_found


# =============================================================================
# ANÁLISE ASSÍNCRONA DO TRIGGER PELO AGENTE
# =============================================================================

async def _analyze_trigger(trigger: Dict, session) -> None:
    """
    Roda o INCOMING_RESPONSE_ANALYSIS_PROMPT para o trigger detectado.
    Atualiza o trigger com o plano sugerido (não executa — aguarda aprovação).
    """
    trigger_id = trigger["trigger_id"]
    _pending_triggers[trigger_id]["status"] = "processing"

    try:
        from modules.ai.service.context.business_context import get_business_context_for_prompt
        from modules.ai.service.intent.prompts import INCOMING_RESPONSE_ANALYSIS_PROMPT
        from core.llm import ask_llm

        # Busca histórico resumido da org
        history_summary = "Sem histórico disponível."
        if trigger.get("org_id"):
            try:
                from modules.ai.service.pipeline.data_fetcher import fetch_contextual_data
                ctx = await fetch_contextual_data(
                    {"query_type": "agent_workflow", "data_scope": ["emails", "whatsapp", "activities"]},
                    trigger["org_id"],
                    session
                )
                # Resumo compacto
                deals = (ctx.get("pipedrive_details") or {}).get("deals", [])
                acts = (ctx.get("pipedrive_details") or {}).get("activities", [])
                parts = []
                if deals:
                    parts.append(f"Deal ativo: {deals[0].get('title')} ({deals[0].get('stage_name')})")
                if acts:
                    parts.append(f"Última atividade: {acts[0].get('subject')} ({'OK' if acts[0].get('done') else 'PEND'})")
                if parts:
                    history_summary = " | ".join(parts)
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
                # Tenta extrair JSON do texto
                import re
                m = re.search(r'\{.*\}', result.text, re.DOTALL)
                if m:
                    try:
                        plan_data = _json.loads(m.group())
                    except Exception:
                        plan_data = {}

        _pending_triggers[trigger_id]["analysis"] = plan_data.get("analysis", "")
        _pending_triggers[trigger_id]["sentiment"] = plan_data.get("sentiment", "neutral")
        _pending_triggers[trigger_id]["client_intent"] = plan_data.get("client_intent", "")
        _pending_triggers[trigger_id]["urgency"] = plan_data.get("urgency", "media")
        _pending_triggers[trigger_id]["suggested_plan"] = plan_data.get("plan", [])
        _pending_triggers[trigger_id]["status"] = "suggested"

        log.info("trigger.analyzed", trigger_id=trigger_id, sentiment=plan_data.get("sentiment"))

        # Notifica callbacks (SSE listeners)
        _notify_callbacks(_pending_triggers[trigger_id])

    except Exception as e:
        log.warning("trigger.analysis_failed", trigger_id=trigger_id, error=str(e)[:200])
        _pending_triggers[trigger_id]["status"] = "suggested"
        _pending_triggers[trigger_id]["analysis"] = "Análise automática indisponível. Verifique a mensagem manualmente."
        _pending_triggers[trigger_id]["suggested_plan"] = []
        _notify_callbacks(_pending_triggers[trigger_id])


# =============================================================================
# LOOP PRINCIPAL DE POLLING
# =============================================================================

class TriggerService:
    """
    Serviço de background que monitora email e WhatsApp por respostas de clientes.

    Registre no lifespan do FastAPI:
        task = asyncio.create_task(TriggerService().start_polling())
    """

    def __init__(self):
        self._running = False

    async def start_polling(self):
        """Loop principal de monitoramento. Roda indefinidamente."""
        self._running = True
        log.info("trigger_service.started")

        # Aguarda 30s no startup para não concorrer com inicialização
        await asyncio.sleep(30)

        while self._running:
            try:
                await self._poll_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("trigger_service.poll_error", error=str(e)[:300])

            # Intervalo entre ciclos completos
            await asyncio.sleep(min(EMAIL_POLL_INTERVAL_SEC, WA_POLL_INTERVAL_SEC))

        log.info("trigger_service.stopped")

    async def stop(self):
        self._running = False

    async def _poll_cycle(self):
        """Executa um ciclo de detecção em todos os canais."""
        global _last_email_check, _last_wa_check

        # ── Guards: kill switch ou horário de silêncio ────────────────────────
        if _service_paused:
            log.debug("trigger_service.skipped_paused")
            return
        if is_quiet_hours():
            log.debug("trigger_service.skipped_quiet_hours",
                      hour=datetime.now().hour,
                      window=f"{QUIET_HOURS_START}h-{QUIET_HOURS_END}h")
            return

        now = time.monotonic()

        # Abre sessão DB para cada ciclo
        try:
            from core.infra.database import async_session
            async with async_session() as session:
                tasks = []

                if now - _last_email_check >= EMAIL_POLL_INTERVAL_SEC:
                    tasks.append(("email", _detect_email_triggers(session)))
                    _last_email_check = now

                if now - _last_wa_check >= WA_POLL_INTERVAL_SEC:
                    tasks.append(("wa", _detect_wa_triggers(session)))
                    _last_wa_check = now

                if not tasks:
                    return

                results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)

                new_triggers = []
                for (channel, _), result in zip(tasks, results):
                    if isinstance(result, Exception):
                        log.warning("trigger_service.channel_error", channel=channel, error=str(result)[:200])
                        continue
                    new_triggers.extend(result)

                if new_triggers:
                    log.info("trigger_service.new_triggers", count=len(new_triggers))

                for trigger in new_triggers:
                    tid = trigger["trigger_id"]
                    _pending_triggers[tid] = trigger
                    asyncio.create_task(
                        self._safe_analyze(trigger, session),
                        name=f"trigger_analyze_{tid[:8]}"
                    )

        except Exception as e:
            log.warning("trigger_service.session_error", error=str(e)[:200])

    @staticmethod
    async def _safe_analyze(trigger: Dict, session) -> None:
        """Wrapper seguro para _analyze_trigger."""
        try:
            from core.infra.database import async_session
            async with async_session() as new_session:
                await _analyze_trigger(trigger, new_session)
        except Exception as e:
            log.warning("trigger_service.analyze_error", error=str(e)[:200])
