"""
Endpoints de persistência de conversas e atividades do agente.

GET  /conversations/{org_id}                   → lista threads da empresa
POST /conversations/{org_id}                   → cria nova thread
GET  /conversations/thread/{thread_id}/messages → mensagens paginadas
DELETE /conversations/thread/{thread_id}        → remove thread + mensagens
GET  /conversations/{org_id}/activities         → timeline de atividades
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.infra.database import get_db
from core.observability.logging_config import get_logger
from models.conversation.conversation import ConversationThread, ConversationMessage, ActivityLog
from models.organization.organization import Organization

router = APIRouter()
log = get_logger(__name__)


# ─────────────────────────────────────────────
# Schemas de resposta (Pydantic)
# ─────────────────────────────────────────────

class ThreadOut(BaseModel):
    id: str
    org_id: Optional[int]
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime]
    message_count: int
    meta: Optional[dict] = None

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: str
    thread_id: str
    role: str
    content: str
    timestamp: datetime
    ui_module: Optional[str] = None
    data: Optional[dict] = None
    logs: Optional[list] = None
    sources: Optional[int] = None

    class Config:
        from_attributes = True


class ActivityOut(BaseModel):
    id: str
    org_id: Optional[int]
    thread_id: Optional[str]
    activity_type: str
    status: str
    payload: Optional[dict] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    external_ref: Optional[str] = None

    class Config:
        from_attributes = True


class CreateThreadBody(BaseModel):
    title: Optional[str] = None
    meta: Optional[dict] = None


# ─────────────────────────────────────────────
# Rotas
# ─────────────────────────────────────────────

async def _resolve_internal_org_id(org_id: int, session: AsyncSession) -> Optional[int]:
    """Resolve o pipedrive_id ou id local para o id interno da organização."""
    if org_id <= 0:
        return None
    stmt = select(Organization.id).where(
        or_(Organization.id == org_id, Organization.pipedrive_id == org_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


@router.get("/{org_id}", response_model=List[ThreadOut])
async def list_threads(
    org_id: int,
    limit: int = Query(20, le=100),
    session: AsyncSession = Depends(get_db),
):
    """Retorna threads da empresa ordenadas pela mais recente."""
    q = select(ConversationThread).order_by(ConversationThread.updated_at.desc()).limit(limit)
    if org_id > 0:
        resolved_id = await _resolve_internal_org_id(org_id, session)
        if resolved_id:
            q = q.where(ConversationThread.org_id == resolved_id)
        else:
            q = q.where(ConversationThread.org_id == org_id)
        
    result = await session.execute(q)
    return result.scalars().all()


@router.post("/{org_id}", response_model=ThreadOut)
async def create_thread(
    org_id: int,
    body: CreateThreadBody,
    session: AsyncSession = Depends(get_db),
):
    """Cria uma nova thread de conversa para a empresa."""
    try:
        resolved_id = await _resolve_internal_org_id(org_id, session)
        if not resolved_id:
            try:
                from modules.crm.service.pipedrive_service import pipedrive_service
                org_data = await pipedrive_service.get_organization_details(org_id)
                if org_data:
                    new_org = Organization(
                        pipedrive_id=org_id,
                        name=org_data.get("name", f"Empresa #{org_id}"),
                        owner_id=org_data.get("owner_id", 0),
                        source="pipedrive"
                    )
                    session.add(new_org)
                    await session.flush()
                    resolved_id = new_org.id
            except Exception as e_pd:
                log.warning("conversations.resolve_org.pipedrive_fallback_failed", org_id=org_id, error=str(e_pd))

        if not resolved_id:
            raise HTTPException(status_code=404, detail="Organização não encontrada no banco local.")

        thread = ConversationThread(
            org_id=resolved_id,
            title=body.title or f"Conversa {datetime.utcnow().strftime('%d/%m %H:%M')}",
            meta=body.meta,
        )
        session.add(thread)
        await session.commit()
        await session.refresh(thread)
        log.info("conversation.thread.created", thread_id=thread.id, org_id=resolved_id)
        return thread
    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        log.exception("conversation.thread.create_failed", org_id=org_id, error=str(e))
        raise HTTPException(status_code=500, detail="Erro ao criar thread de conversa.")


@router.get("/thread/{thread_id}/messages", response_model=List[MessageOut])
async def get_messages(
    thread_id: str,
    limit: int = Query(50, le=200),
    before: Optional[str] = Query(None, description="ISO datetime — paginação cursor"),
    session: AsyncSession = Depends(get_db),
):
    """Retorna mensagens de uma thread, paginadas da mais recente para mais antiga."""
    q = (
        select(ConversationMessage)
        .where(ConversationMessage.thread_id == thread_id)
        .order_by(ConversationMessage.timestamp.asc())
        .limit(limit)
    )
    if before:
        try:
            cursor_dt = datetime.fromisoformat(before)
            q = q.where(ConversationMessage.timestamp < cursor_dt)
        except ValueError:
            pass

    result = await session.execute(q)
    return result.scalars().all()


@router.delete("/thread/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Remove uma thread e todas as suas mensagens."""
    thread = await session.get(ConversationThread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread não encontrada")
    try:
        await session.delete(thread)
        await session.commit()
        log.info("conversation.thread.deleted", thread_id=thread_id)
    except Exception as e:
        await session.rollback()
        log.exception("conversation.thread.delete_failed", thread_id=thread_id, error=str(e))
        raise HTTPException(status_code=500, detail="Erro ao remover thread.")


@router.delete("/threads/bulk", status_code=204)
async def delete_threads_bulk(
    thread_ids: List[str] = Query(..., description="Lista de IDs de threads a remover"),
    session: AsyncSession = Depends(get_db),
):
    """Remove múltiplas threads e todas as suas mensagens de uma vez."""
    q = select(ConversationThread).where(ConversationThread.id.in_(thread_ids))
    result = await session.execute(q)
    threads = result.scalars().all()
    
    if not threads:
        raise HTTPException(status_code=404, detail="Nenhuma thread encontrada para remover")
        
    try:
        for thread in threads:
            await session.delete(thread)
        await session.commit()
        log.info("conversation.threads.bulk_deleted", count=len(threads))
    except Exception as e:
        await session.rollback()
        log.exception("conversation.threads.bulk_delete_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Erro ao remover threads.")



@router.get("/{org_id}/activities", response_model=List[ActivityOut])
async def list_activities(
    org_id: int,
    limit: int = Query(30, le=100),
    activity_type: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    """Retorna timeline de atividades da empresa, mais recentes primeiro."""
    q = select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
    if org_id > 0:
        resolved_id = await _resolve_internal_org_id(org_id, session)
        if resolved_id:
            q = q.where(ActivityLog.org_id == resolved_id)
        else:
            q = q.where(ActivityLog.org_id == org_id)
    if activity_type:
        q = q.where(ActivityLog.activity_type == activity_type)

    result = await session.execute(q)
    return result.scalars().all()


@router.patch("/message/{message_id}/suggested_actions/{action_index}")
async def update_suggested_action_status(
    message_id: str,
    action_index: int,
    payload: dict,
    session: AsyncSession = Depends(get_db)
):
    from sqlalchemy.orm.attributes import flag_modified
    status = payload.get("status")
    logs = payload.get("logs")  # Optional: execution logs to persist
    if not status:
        raise HTTPException(status_code=400, detail="status is required")
        
    res = await session.execute(
        select(ConversationMessage).where(ConversationMessage.id == message_id)
    )
    msg = res.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
        
    msg_data = dict(msg.data or {})
    runs = msg_data.get("suggested_actions_runs", {})
    idx_str = str(action_index)
    if idx_str not in runs:
        runs[idx_str] = {"status": status, "logs": logs or [], "timestamp": datetime.utcnow().isoformat()}
    else:
        runs[idx_str]["status"] = status
        if logs is not None:
            runs[idx_str]["logs"] = logs
        
    msg_data["suggested_actions_runs"] = runs
    msg.data = msg_data
    
    parent_logs = list(msg.logs or [])
    for event in parent_logs:
        if event.get("type") == "suggested_actions":
            actions = event.get("actions", [])
            if 0 <= action_index < len(actions):
                actions[action_index]["status"] = status
    msg.logs = parent_logs
    
    flag_modified(msg, "data")
    flag_modified(msg, "logs")
    session.add(msg)
    await session.commit()
    
    return {"ok": True}


# ─────────────────────────────────────────────
# Helpers usados pelos outros endpoints/services
# ─────────────────────────────────────────────

async def delete_last_assistant_message(
    session: AsyncSession,
    thread_id: str
) -> bool:
    """Remove a última mensagem do assistente na thread (usado para regeneração)."""
    q = (
        select(ConversationMessage)
        .where(ConversationMessage.thread_id == thread_id)
        .where(ConversationMessage.role == "assistant")
        .order_by(ConversationMessage.timestamp.desc())
        .limit(1)
    )
    result = await session.execute(q)
    msg = result.scalar_one_or_none()
    if msg:
        await session.delete(msg)
        # Ajustar contador da thread
        await session.execute(
            update(ConversationThread)
            .where(ConversationThread.id == thread_id)
            .values(
                message_count=ConversationThread.message_count - 1,
            )
        )
        await session.commit()
        log.info("conversation.message.deleted_for_regeneration", thread_id=thread_id, message_id=msg.id)
        return True
    return False


async def get_thread_cached_context(
    session: AsyncSession,
    thread_id: str,
    org_id: Optional[int] = None,
    max_age_minutes: int = 30,
) -> Optional[dict]:
    """
    Recupera o contexto salvo da última mensagem do assistente na thread.
    Usado para evitar re-buscar todos os dados quando a conversa continua.
    
    Retorna o internal_context salvo se:
    - Há uma mensagem de assistant recente na thread
    - O contexto tem menos de max_age_minutos
    - O org_id bate (se fornecido)
    """
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import select, desc
        
        cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        
        # Busca a última mensagem do assistente com data não nulo
        result = await session.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.thread_id == thread_id,
                ConversationMessage.role == "assistant",
                ConversationMessage.data.isnot(None),
                ConversationMessage.timestamp >= cutoff
            )
            .order_by(desc(ConversationMessage.timestamp))
            .limit(1)
        )
        last_msg = result.scalar_one_or_none()
        
        if not last_msg:
            return None
            
        # Extrai o internal_context do campo data
        msg_data = last_msg.data or {}
        cached_context = msg_data.get("_internal_context")
        
        if not cached_context:
            return None
            
        # Verifica se o org_id bate (se fornecido)
        # O dict de organização pode ter "id", "pipedrive_id" ou "_org_id" dependendo da origem
        if org_id:
            org_dict = cached_context.get("organization", {})
            context_org_id = (
                cached_context.get("_org_id")      # campo canônico adicionado na v2
                or org_dict.get("id")               # legacy
                or org_dict.get("pipedrive_id")     # formato atual do data_fetcher
                or org_dict.get("local_id")
            )
            # Compara como int para evitar falha por tipo (str vs int)
            try:
                match = int(context_org_id) == int(org_id)
            except (TypeError, ValueError):
                match = False
            if not match:
                log.debug("chat.context_cache.org_mismatch",
                          context_org_id=context_org_id, payload_org_id=org_id)
                return None
                
        log.info("chat.context_cache.hit", thread_id=thread_id)
        return cached_context
        
    except Exception as e:
        log.warning("chat.context_cache.error", error=str(e))
        return None


async def save_message(
    session: AsyncSession,
    thread_id: str,
    role: str,
    content: str,
    ui_module: Optional[str] = None,
    data: Optional[dict] = None,
    logs: Optional[list] = None,
    sources: Optional[int] = None,
    internal_context: Optional[dict] = None,
) -> ConversationMessage:
    """Salva uma mensagem e atualiza os contadores da thread."""
    # Se houver internal_context, salva no data para reuso futuro
    final_data = data or {}
    if internal_context and role == "assistant":
        # Cria uma cópia para não modificar o dict original
        final_data = {**final_data, "_internal_context": internal_context}
    
    msg = ConversationMessage(
        thread_id=thread_id,
        role=role,
        content=content,
        ui_module=ui_module,
        data=final_data,
        logs=logs,
        sources=sources,
    )
    session.add(msg)

    # Atualizar contadores da thread
    await session.execute(
        update(ConversationThread)
        .where(ConversationThread.id == thread_id)
        .values(
            last_message_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            message_count=ConversationThread.message_count + 1,
        )
    )
    await session.commit()
    return msg


async def log_activity(
    session: AsyncSession,
    org_id: Optional[int],
    activity_type: str,
    payload: dict,
    thread_id: Optional[str] = None,
    status: str = "completed",
    external_ref: Optional[str] = None,
) -> ActivityLog:
    """Registra uma atividade do agente no ActivityLog."""
    resolved_id = org_id
    if org_id and org_id > 0:
        resolved_id = await _resolve_internal_org_id(org_id, session)
        if not resolved_id:
            resolved_id = org_id

    activity = ActivityLog(
        org_id=resolved_id,
        thread_id=thread_id,
        activity_type=activity_type,
        status=status,
        payload=payload,
        external_ref=external_ref,
    )
    session.add(activity)
    await session.commit()
    log.info(
        "activity.logged",
        org_id=resolved_id,
        type=activity_type,
        status=status,
    )
    return activity


async def get_recent_activities_context(
    session: AsyncSession,
    org_id: int,
    limit: int = 10,
) -> List[ActivityLog]:
    """Busca atividades recentes para injeção no prompt do agente."""
    q = select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
    if org_id > 0:
        resolved_id = await _resolve_internal_org_id(org_id, session)
        if resolved_id:
            q = q.where(ActivityLog.org_id == resolved_id)
        else:
            q = q.where(ActivityLog.org_id == org_id)
        
    result = await session.execute(q)
    return result.scalars().all()
