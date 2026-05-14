"""
Endpoint /ai — thin router. Toda a orquestração vive em
services.ai.chat_service.ChatOrchestrator.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logging_config import get_logger
from services.ai.chat_service import ChatOrchestrator
from services.ai.helpers import ChatMessage

router = APIRouter()
log = get_logger(__name__)


class AgentActionRequest(PydanticBaseModel):
    action_id: str
    approved: bool
    thread_id: Optional[str] = None   # para registrar ActivityLog na thread certa


class RefineMessageRequest(PydanticBaseModel):
    action_id: str
    feedback: str


class PreferenceRequest(PydanticBaseModel):
    model: str
    strict_mode: Optional[bool] = False  # Se True, força o modelo com retry agressivo (sem fallback)


@router.post("/preference")
async def update_ai_preference(payload: PreferenceRequest):
    """Atualiza o modelo de IA preferido globalmente."""
    from services.ai.llm.router import set_preferred_model
    set_preferred_model(payload.model, strict_mode=payload.strict_mode or False)
    return {"status": "ok", "preferred_model": payload.model, "strict_mode": payload.strict_mode or False}


@router.get("/preference")
async def get_ai_preference():
    """Retorna o modelo de IA preferido atualmente."""
    from services.ai.llm.router import get_preferred_model, get_strict_mode_preference
    return {"preferred_model": get_preferred_model(), "strict_mode": get_strict_mode_preference()}


@router.get("/quotas")
async def get_live_quotas():
    """Retorna os limites de cota em tempo real (0-100%) para todos os provedores."""
    from services.ai.llm.quota_manager import get_quota_manager
    return get_quota_manager().get_summary()


@router.post("/chat")
async def chat_with_ai(
    payload: ChatMessage,
    session: AsyncSession = Depends(get_db),
):
    """
    Chat com IA usando RAG (Retrieval Augmented Generation).
    Pipeline em 2 estágios extraído para `ChatOrchestrator`.
    Persiste mensagens na ConversationThread se thread_id fornecido.
    """
    try:
        result = await ChatOrchestrator.handle(payload, session)

        # ── Persistência de mensagens ──────────────────────────────
        # Se for stream (Agente), a persistência já foi feita dentro do streamer.
        # Caso contrário, salvamos aqui.
        from fastapi.responses import StreamingResponse
        if not isinstance(result, StreamingResponse):
            thread_id = getattr(payload, "thread_id", None)
            if thread_id:
                from api.v1.endpoints.conversations import save_message
                # Salva a mensagem do usuário
                await save_message(
                    session=session,
                    thread_id=thread_id,
                    role="user",
                    content=payload.message,
                )
                # Salva a resposta do assistente
                resp_content     = result.get("response", "") if isinstance(result, dict) else getattr(result, "response", "")
                ui_module        = result.get("ui_module") if isinstance(result, dict) else getattr(result, "ui_module", None)
                data             = result.get("data") if isinstance(result, dict) else getattr(result, "data", None)
                logs             = result.get("logs") if isinstance(result, dict) else getattr(result, "logs", None)
                internal_context = result.get("_internal_context") if isinstance(result, dict) else getattr(result, "_internal_context", None)

                await save_message(
                    session=session,
                    thread_id=thread_id,
                    role="assistant",
                    content=resp_content,
                    ui_module=ui_module,
                    data=data,
                    logs=logs,
                    internal_context=internal_context,
                )

        return result
    except HTTPException:
        raise
    except Exception as e:
        log.exception("ai.chat.failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Erro ao processar mensagem: {e}"
        )


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """
    Transcreve áudio via Groq Whisper (whisper-large-v3-turbo).
    Aceita webm, ogg, mp4, wav, m4a — qualquer formato que o MediaRecorder produza.
    """
    from core.config import settings
    from core.http_client import get_http_client

    if not settings.GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY não configurada")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Arquivo de áudio vazio")

    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"

    client = get_http_client()
    try:
        resp = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            files={"file": (filename, audio_bytes, content_type)},
            data={"model": "whisper-large-v3-turbo", "language": "pt", "response_format": "json"},
            timeout=30.0,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao chamar Groq Whisper: {e}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Groq Whisper retornou {resp.status_code}: {resp.text[:200]}")

    transcript = resp.json().get("text", "").strip()
    return {"transcript": transcript}


@router.post("/refine-message")
async def refine_message(payload: RefineMessageRequest):
    """Refina a mensagem de uma ação pendente com base no feedback do usuário e atualiza em memória."""
    from services.ai.agent_service import AgentService
    from services.ai.business_context_service import BusinessContextService
    from services.ai.llm.router import ask_llm
    from services.ai.llm.base import LLMTier
    import json

    # V2: _PENDING em agent.py (dict de módulo)
    from services.ai.agent_v2.agent import _PENDING as _V2_PENDING
    pending_v2 = _V2_PENDING.get(payload.action_id)
    pending_v1 = AgentService._pending_actions.get(payload.action_id)
    pending = pending_v2 or pending_v1
    if not pending:
        raise HTTPException(status_code=404, detail="Ação não encontrada ou já expirou.")

    # Extrai campos independente da versão do agente
    if pending_v2:
        args = pending_v2.get("args", {})
        current_message = args.get("message") or args.get("body") or ""
        contact_name = args.get("contact") or args.get("contact_name") or ""
        channel = "email" if "email" in pending_v2.get("tool", "") else "whatsapp"
    else:
        current_message = pending_v1.get("message_preview", "")
        contact_name = pending_v1.get("contact_name", "")
        channel = pending_v1.get("channel", "whatsapp")

    business_context = await BusinessContextService.get_tenant_context()
    biz_data_str = json.dumps(business_context, indent=2, ensure_ascii=False) if business_context else ""

    system_prompt = (
        "Você é um redator comercial B2B sênior. Reescreva a mensagem de vendas abaixo aplicando "
        "exatamente o ajuste solicitado — não altere o que não foi pedido.\n\n"
        f"## CONTEXTO DA EMPRESA (mantenha os diferenciais):\n{biz_data_str}\n\n"
        "REGRAS:\n"
        "- Aplique APENAS o ajuste pedido. Preserve tom, dados concretos (nomes, preços, códigos) e estratégia geral.\n"
        "- Nunca adicione placeholders como [x] ou [y].\n"
        f"- Canal: {channel}. Tom natural e direto.\n"
        "RETORNE APENAS O TEXTO DA MENSAGEM REESCRITA. Sem introdução, sem explicação."
    )
    prompt_user = (
        f"MENSAGEM ORIGINAL:\n{current_message}\n\n"
        f"AJUSTE SOLICITADO: {payload.feedback}\n\n"
        "Reescreva a mensagem aplicando o ajuste."
    )

    try:
        res = await ask_llm(
            prompt=prompt_user,
            system=system_prompt,
            json_mode=False,
            temperature=0.4,
            tier=LLMTier.STANDARD
        )
        refined = res.text.strip()

        # Atualiza o pending em memória para que o envio use a versão refinada
        if pending_v2:
            args = _V2_PENDING[payload.action_id].get("args", {})
            if "message" in args:
                args["message"] = refined
            if "body" in args:
                args["body"] = refined
        else:
            AgentService._pending_actions[payload.action_id]["message_preview"] = refined
            params = AgentService._pending_actions[payload.action_id].get("params", {})
            if "message" in params:
                params["message"] = refined
            if "body" in params:
                params["body"] = refined

        return {"ok": True, "refined_message": refined}
    except Exception as e:
        log.exception("ai.refine_message.failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent-action")
async def handle_agent_action(
    payload: AgentActionRequest,
    session: AsyncSession = Depends(get_db),
):
    """Aprova ou rejeita ações do agente que requerem permissão."""
    from services.ai.agent_service import AgentService
    try:
        if payload.approved:
            result = await AgentService.execute_approved_action(payload.action_id, session)

            # ── Registrar ActivityLog ──────────────────────────────────
            try:
                await _log_approved_action(payload.action_id, payload.thread_id, result, session)
            except Exception as log_err:
                log.warning("ai.agent_action.log_failed", error=str(log_err))

            return result

        result = await AgentService.reject_action(payload.action_id)

        # Registrar cancelamento
        try:
            await _log_rejected_action(payload.action_id, payload.thread_id, session)
        except Exception:
            pass

        return result
    except Exception as e:
        log.exception("ai.agent_action.failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────
# Helpers privados: traduzem a pending_action em ActivityLog
# ─────────────────────────────────────────────────────────────────

async def _log_approved_action(
    action_id: str,
    thread_id: Optional[str],
    result: dict,
    session: AsyncSession,
) -> None:
    """Detecta o tipo de ação aprovada e cria ActivityLog correspondente."""
    from services.ai.agent_service import AgentService
    from api.v1.endpoints.conversations import log_activity

    # Recuperar a pending_action do cache para ter org_id e detalhes
    pending = AgentService._pending_actions.get(action_id)
    if not pending:
        return

    action_type  = pending.get("action_type", "")
    channel      = pending.get("channel", "")
    org_id       = pending.get("org_id")
    contact_name = pending.get("contact_name", "")
    subject      = pending.get("subject", "")
    preview      = pending.get("message_preview", "")
    is_reply     = pending.get("is_reply", False)
    entry_id     = pending.get("email_entry_id")

    # Mapear action_type → activity_type
    if channel == "whatsapp" or action_type in ("send_whatsapp", "whatsapp"):
        atype = "whatsapp_sent"
        payload = {
            "to_name": contact_name,
            "to_phone": pending.get("contact_phone", ""),
            "message_preview": preview,
        }
        await log_activity(
            session=session,
            org_id=org_id,
            activity_type=atype,
            payload=payload,
            thread_id=thread_id,
            status="completed",
        )
        return

    elif channel == "email" or action_type in ("send_email", "reply_email", "email"):
        atype = "email_reply_sent" if is_reply else "email_sent"
        payload = {
            "to_name": contact_name,
            "to_email": pending.get("contact_email", ""),
            "subject": subject,
            "message_preview": preview,
            "is_reply": is_reply,
        }
        ext_ref = entry_id
        # Status especial: email enviado fica "aguardando resposta"
        status = "awaiting_reply" if not is_reply else "completed"
        await log_activity(
            session=session,
            org_id=org_id,
            activity_type=atype,
            payload=payload,
            thread_id=thread_id,
            status=status,
            external_ref=ext_ref,
        )
        return

    elif action_type in ("move_stage", "update_stage", "stage"):
        atype = "stage_changed"
        payload = {
            "from_stage": pending.get("from_stage", ""),
            "to_stage": pending.get("to_stage", subject),
            "deal_title": pending.get("description", ""),
        }
        await log_activity(
            session=session,
            org_id=org_id,
            activity_type=atype,
            payload=payload,
            thread_id=thread_id,
            status="completed",
        )
        return

    else:
        # Ação genérica — registra como tipo literal
        atype = action_type or "unknown"
        payload = {"description": pending.get("description", ""), "preview": preview}
        await log_activity(
            session=session,
            org_id=org_id,
            activity_type=atype,
            payload=payload,
            thread_id=thread_id,
            status="completed",
        )
        return


async def _log_rejected_action(
    action_id: str,
    thread_id: Optional[str],
    session: AsyncSession,
) -> None:
    from services.ai.agent_service import AgentService
    from api.v1.endpoints.conversations import log_activity

    pending = AgentService._pending_actions.get(action_id)
    if not pending:
        return

    await log_activity(
        session=session,
        org_id=pending.get("org_id"),
        activity_type=pending.get("action_type", "unknown"),
        payload={"cancelled": True, "description": pending.get("description", "")},
        thread_id=thread_id,
        status="cancelled",
    )
