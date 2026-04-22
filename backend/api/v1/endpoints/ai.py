"""
Endpoint /ai — thin router. Toda a orquestração vive em
services.ai.chat_service.ChatOrchestrator.
"""
from __future__ import annotations

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


@router.post("/chat")
async def chat_with_ai(
    payload: ChatMessage,
    session: AsyncSession = Depends(get_db),
):
    """
    Chat com IA usando RAG (Retrieval Augmented Generation).
    Pipeline em 2 estágios extraído para `ChatOrchestrator`.
    """
    try:
        return await ChatOrchestrator.handle(payload, session)
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
            return await AgentService.execute_approved_action(payload.action_id, session)
        return await AgentService.reject_action(payload.action_id)
    except Exception as e:
        log.exception("ai.agent_action.failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
