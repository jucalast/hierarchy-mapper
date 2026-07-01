"""
Endpoint do Agente.

POST /agent/chat    — inicia uma sessão do agente (StreamingResponse NDJSON)
POST /agent/confirm — aprova ou rejeita uma ação pendente (StreamingResponse NDJSON)
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from core.observability.logging_config import get_logger

router = APIRouter()
log = get_logger(__name__)


class AgentChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    org_id: Optional[int] = None
    thread_id: Optional[str] = None
    model: Optional[str] = None
    direct_action: Optional[bool] = False
    parent_message_id: Optional[str] = None
    action_index: Optional[int] = None


class AgentConfirmRequest(BaseModel):
    action_id: str
    approved: bool
    thread_id: Optional[str] = None
    attachment_path: Optional[str] = None


@router.post("/chat")
async def agent_chat(payload: AgentChatRequest):
    """Executa o loop do Agente com streaming NDJSON via Worker ARQ."""
    from core.llm.router import set_preferred_model
    from core.llm.router import get_strict_mode_preference
    import uuid
    import json
    import asyncio
    from core.infra.redis_config import redis_settings
    from arq.connections import create_pool

    preferred = getattr(payload, "model", None)
    strict = get_strict_mode_preference()
    set_preferred_model(preferred, strict_mode=strict)

    is_regeneration = False
    if payload.thread_id and payload.history and len(payload.history) >= 2:
        last_msg = payload.history[-1]
        prev_msg = payload.history[-2]
        if last_msg.get("role") == "assistant" and prev_msg.get("role") == "user":
            if prev_msg.get("content") == payload.message:
                is_regeneration = True
                from core.infra.database import async_session as _async_session
                from api.v1.routers.conversations import delete_last_assistant_message
                from sqlalchemy import select
                from models.conversation.conversation import ConversationMessage

                async with _async_session() as db:
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

                                parent_logs = list(parent_msg.logs or [])
                                for event in parent_logs:
                                    if event.get("type") == "suggested_actions":
                                        actions = event.get("actions", [])
                                        if 0 <= payload.action_index < len(actions):
                                            actions[payload.action_index]["status"] = "pending"
                                            if "logs" in actions[payload.action_index]:
                                                del actions[payload.action_index]["logs"]
                                parent_msg.logs = parent_logs

                                from sqlalchemy.orm.attributes import flag_modified
                                flag_modified(parent_msg, "data")
                                flag_modified(parent_msg, "logs")

                                db.add(parent_msg)
                                await db.commit()

                    await delete_last_assistant_message(db, payload.thread_id)

                payload.history = payload.history[:-1]

    job_id = f"agent_chat_{uuid.uuid4().hex[:8]}"

    payload_dict = {
        "job_id": job_id,
        "message": payload.message,
        "history": payload.history or [],
        "org_id": payload.org_id,
        "preferred": preferred,
        "strict_mode": strict,
        "thread_id": payload.thread_id,
        "direct_action": payload.direct_action or False,
        "parent_message_id": payload.parent_message_id,
        "action_index": payload.action_index,
        "is_regeneration": is_regeneration,
    }

    redis = await create_pool(redis_settings)
    await redis.enqueue_job("run_agent_task", payload_dict=payload_dict)

    async def streamer():
        pubsub = redis.pubsub()
        channel_name = f"agent_updates_{job_id}"
        await pubsub.subscribe(channel_name)
        finished = False
        try:
            async for message in pubsub.listen():
                if message and message['type'] == 'message':
                    data = message['data']
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')

                    try:
                        msg_obj = json.loads(data)
                        if msg_obj.get('type') == 'job_done':
                            finished = True
                            break
                        if msg_obj.get('type') == 'error':
                            # O evento de erro pode trazer a mensagem em "error" (exceção do worker)
                            # OU em "content" (falha de tool emitida pelo runner). Preserva a real.
                            error_msg = msg_obj.get("error") or msg_obj.get("content") or "Erro interno no worker"
                            yield json.dumps({"type": "error", "content": error_msg, "recoverable": msg_obj.get("recoverable", False)}) + "\n"
                            finished = True
                            break
                    except (json.JSONDecodeError, AttributeError):
                        pass
                    
                    yield data if data.endswith('\n') else data + '\n'
        finally:
            await pubsub.unsubscribe(channel_name)
            # Não aborta o job: o agente continua rodando no worker ARQ mesmo
            # se o cliente recarregar a página. Os resultados são salvos no banco
            # e ficam disponíveis quando o usuário voltar à conversa.
            if not finished:
                log.info("agent.stream.client_disconnected", job_id=job_id)

    return StreamingResponse(streamer(), media_type="application/x-ndjson")


@router.post("/confirm")
async def agent_confirm(payload: AgentConfirmRequest):
    """Retoma o agente após confirmação de uma ação de escrita via Worker ARQ."""
    import uuid
    import json
    from core.infra.redis_config import redis_settings
    from arq.connections import create_pool

    job_id = f"agent_resume_{uuid.uuid4().hex[:8]}"

    payload_dict = {
        "job_id": job_id,
        "action_id": payload.action_id,
        "approved": payload.approved,
        "thread_id": payload.thread_id,
        "attachment_path": payload.attachment_path,
    }

    redis = await create_pool(redis_settings)
    await redis.enqueue_job("resume_agent_task", payload_dict=payload_dict)

    async def streamer():
        pubsub = redis.pubsub()
        channel_name = f"agent_updates_{job_id}"
        await pubsub.subscribe(channel_name)
        finished = False
        try:
            async for message in pubsub.listen():
                if message and message['type'] == 'message':
                    data = message['data']
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')

                    try:
                        msg_obj = json.loads(data)
                        if msg_obj.get('type') == 'job_done':
                            finished = True
                            break
                        if msg_obj.get('type') == 'error':
                            # O evento de erro pode trazer a mensagem em "error" (exceção do worker)
                            # OU em "content" (falha de tool emitida pelo runner). Preserva a real.
                            error_msg = msg_obj.get("error") or msg_obj.get("content") or "Erro interno no worker"
                            yield json.dumps({"type": "error", "content": error_msg, "recoverable": msg_obj.get("recoverable", False)}) + "\n"
                            finished = True
                            break
                    except (json.JSONDecodeError, AttributeError):
                        pass
                    
                    yield data if data.endswith('\n') else data + '\n'
        finally:
            await pubsub.unsubscribe(channel_name)
            if not finished:
                log.info("agent.stream.client_disconnected", job_id=job_id)

    return StreamingResponse(streamer(), media_type="application/x-ndjson")


@router.post("/upload")
async def agent_upload(file: __import__("fastapi").UploadFile = __import__("fastapi").File(...)):
    """Faz upload de um arquivo para ser anexado em uma ação do agente."""
    import os
    import uuid
    from pathlib import Path
    
    upload_dir = Path("backend/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitizar o nome do arquivo e adicionar UUID para evitar colisões
    safe_name = "".join(c for c in file.filename if c.isalnum() or c in " ._-")
    file_id = uuid.uuid4().hex[:8]
    final_name = f"{file_id}_{safe_name}"
    
    file_path = upload_dir / final_name
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    return {"ok": True, "attachment_path": str(file_path.absolute())}
