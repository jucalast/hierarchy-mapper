"""
Endpoint /ai — thin router. Toda a orquestração vive em
services.ai.chat_service.ChatOrchestrator.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
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
            resp_content = result.get("response", "") if isinstance(result, dict) else getattr(result, "response", "")
            ui_module    = result.get("ui_module") if isinstance(result, dict) else getattr(result, "ui_module", None)
            data         = result.get("data") if isinstance(result, dict) else getattr(result, "data", None)

            await save_message(
                session=session,
                thread_id=thread_id,
                role="assistant",
                content=resp_content,
                ui_module=ui_module,
                data=data,
            )

        return result
    except HTTPException:
        raise
    except Exception as e:
        log.exception("ai.chat.failed", error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Erro ao processar mensagem: {e}"
        )


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
        ext_ref = None

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
        ext_ref = None

    else:
        # Ação genérica — registra como tipo literal
        atype = action_type or "unknown"
        payload = {"description": pending.get("description", ""), "preview": preview}
        ext_ref = None

    await log_activity(
        session=session,
        org_id=org_id,
        activity_type=atype,
        payload=payload,
        thread_id=thread_id,
        status="completed",
        external_ref=ext_ref,
    )


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
