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
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logging_config import get_logger
from models.conversation import ConversationThread, ConversationMessage, ActivityLog

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

@router.get("/{org_id}", response_model=List[ThreadOut])
async def list_threads(
    org_id: int,
    limit: int = Query(20, le=100),
    session: AsyncSession = Depends(get_db),
):
    """Retorna threads da empresa ordenadas pela mais recente."""
    result = await session.execute(
        select(ConversationThread)
        .where(ConversationThread.org_id == org_id)
        .order_by(ConversationThread.updated_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/{org_id}", response_model=ThreadOut)
async def create_thread(
    org_id: int,
    body: CreateThreadBody,
    session: AsyncSession = Depends(get_db),
):
    """Cria uma nova thread de conversa para a empresa."""
    thread = ConversationThread(
        org_id=org_id,
        title=body.title or f"Conversa {datetime.utcnow().strftime('%d/%m %H:%M')}",
        meta=body.meta,
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    log.info("conversation.thread.created", thread_id=thread.id, org_id=org_id)
    return thread


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
    await session.delete(thread)
    await session.commit()
    log.info("conversation.thread.deleted", thread_id=thread_id)


@router.get("/{org_id}/activities", response_model=List[ActivityOut])
async def list_activities(
    org_id: int,
    limit: int = Query(30, le=100),
    activity_type: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    """Retorna timeline de atividades da empresa, mais recentes primeiro."""
    q = (
        select(ActivityLog)
        .where(ActivityLog.org_id == org_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    if activity_type:
        q = q.where(ActivityLog.activity_type == activity_type)

    result = await session.execute(q)
    return result.scalars().all()


# ─────────────────────────────────────────────
# Helpers usados pelos outros endpoints/services
# ─────────────────────────────────────────────

async def save_message(
    session: AsyncSession,
    thread_id: str,
    role: str,
    content: str,
    ui_module: Optional[str] = None,
    data: Optional[dict] = None,
    logs: Optional[list] = None,
    sources: Optional[int] = None,
) -> ConversationMessage:
    """Salva uma mensagem e atualiza os contadores da thread."""
    msg = ConversationMessage(
        thread_id=thread_id,
        role=role,
        content=content,
        ui_module=ui_module,
        data=data,
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
    activity = ActivityLog(
        org_id=org_id,
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
        org_id=org_id,
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
    result = await session.execute(
        select(ActivityLog)
        .where(ActivityLog.org_id == org_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()
