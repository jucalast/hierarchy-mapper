"""
Endpoint do Agente V2.

POST /ai/v2/chat    — inicia uma sessão do agente (StreamingResponse NDJSON)
POST /ai/v2/confirm — aprova ou rejeita uma ação pendente (StreamingResponse NDJSON)
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()


class V2ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    org_id: Optional[int] = None
    thread_id: Optional[str] = None
    model: Optional[str] = None
    direct_action: Optional[bool] = False
    parent_message_id: Optional[str] = None
    action_index: Optional[int] = None


class V2ConfirmRequest(BaseModel):
    action_id: str
    approved: bool
    thread_id: Optional[str] = None


@router.post("/v2/chat")
async def agent_v2_chat(payload: V2ChatRequest):
    """Executa o loop do agente V2 com streaming NDJSON."""
    from services.ai.agent_v2.agent import run_agent
    from services.ai.llm.router import set_preferred_model
    from services.ai.llm.router import get_strict_mode_preference

    preferred = getattr(payload, "model", None)
    # Respeita o strict mode global definido pelo usuário via UI (cadeado)
    strict = get_strict_mode_preference()
    set_preferred_model(preferred, strict_mode=strict)

    is_regeneration = False
    # 🔄 Detecção de Regeneração (Limpeza do DB e do Histórico)
    if payload.thread_id and payload.history and len(payload.history) >= 2:
        last_msg = payload.history[-1]
        prev_msg = payload.history[-2]
        if last_msg.get("role") == "assistant" and prev_msg.get("role") == "user":
            if prev_msg.get("content") == payload.message:
                is_regeneration = True
                from core.database import async_session as _async_session
                from api.v1.endpoints.conversations import delete_last_assistant_message
                from sqlalchemy import select
                from models.conversation import ConversationMessage
                
                async with _async_session() as db:
                    # Se for uma ação sugerida, precisamos limpar o estado no pai
                    if payload.parent_message_id and payload.action_index is not None:
                        res = await db.execute(
                            select(ConversationMessage).where(ConversationMessage.id == payload.parent_message_id)
                        )
                        parent_msg = res.scalar_one_or_none()
                        if parent_msg:
                            msg_data = dict(parent_msg.data or {})
                            runs = msg_data.get("suggested_actions_runs", {})
                            idx_str = str(payload.action_index)
                            if idx_str in runs:
                                del runs[idx_str]
                                msg_data["suggested_actions_runs"] = runs
                                parent_msg.data = msg_data
                                
                                # Também reseta o status no log original
                                parent_logs = list(parent_msg.logs or [])
                                for event in parent_logs:
                                    if event.get("type") == "suggested_actions":
                                        actions = event.get("actions", [])
                                        if 0 <= payload.action_index < len(actions):
                                            actions[payload.action_index]["status"] = "pending"
                                            if "logs" in actions[payload.action_index]:
                                                del actions[payload.action_index]["logs"]
                                parent_msg.logs = parent_logs
                                
                                db.add(parent_msg)
                                await db.commit()
                                log.info("agent.regeneration.parent_cleared", parent_id=payload.parent_message_id, idx=payload.action_index)
                    
                    # Deleta a última mensagem do assistente (comportamento padrão)
                    await delete_last_assistant_message(db, payload.thread_id)
                
                # Remove a última resposta do assistente do histórico
                payload.history = payload.history[:-1]

    async def streamer():
        async for chunk in run_agent(
            message=payload.message,
            history=payload.history or [],
            org_id=payload.org_id,
            preferred=preferred,
            strict_mode=strict,
            thread_id=payload.thread_id,
            direct_action=payload.direct_action or False,
            parent_message_id=payload.parent_message_id,
            action_index=payload.action_index,
            is_regeneration=is_regeneration,
        ):
            yield chunk

    return StreamingResponse(streamer(), media_type="application/x-ndjson")


@router.post("/v2/confirm")
async def agent_v2_confirm(payload: V2ConfirmRequest):
    """Retoma o agente após confirmação de uma ação de escrita."""
    from services.ai.agent_v2.agent import resume_after_confirmation

    async def streamer():
        async for chunk in resume_after_confirmation(
            action_id=payload.action_id,
            approved=payload.approved,
            thread_id=payload.thread_id,
        ):
            yield chunk

    return StreamingResponse(streamer(), media_type="application/x-ndjson")
