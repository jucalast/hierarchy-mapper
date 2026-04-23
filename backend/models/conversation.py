"""
Modelos de persistência de conversas e atividades do agente.

ConversationThread  — uma "sessão" de chat por empresa
ConversationMessage — cada mensagem trocada dentro de uma thread
ActivityLog         — registro estruturado de ações executadas pelo agente
"""
from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
)
from sqlalchemy.orm import relationship
from core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────
# ConversationThread
# ─────────────────────────────────────────────

class ConversationThread(Base):
    """Agrupa mensagens de uma conversa por empresa."""
    __tablename__ = "conversation_threads"

    id          = Column(String, primary_key=True, default=_new_uuid)
    org_id      = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    title       = Column(String, nullable=True)          # e.g. "Negociação Atual", ou gerado do 1º msg
    created_at  = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True, index=True)
    message_count   = Column(Integer, default=0)
    meta        = Column(JSON, nullable=True)            # {pipedrive_deal_id, tags, ...}

    # Relacionamentos
    organization = relationship("Organization", lazy="select")
    messages     = relationship(
        "ConversationMessage",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.timestamp",
        lazy="select",
    )
    activities   = relationship(
        "ActivityLog",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ActivityLog.created_at",
        lazy="select",
    )

    __table_args__ = (
        Index("ix_ct_org_updated", "org_id", "updated_at"),
    )


# ─────────────────────────────────────────────
# ConversationMessage
# ─────────────────────────────────────────────

class ConversationMessage(Base):
    """Cada mensagem (user ou assistant) dentro de uma thread."""
    __tablename__ = "conversation_messages"

    id        = Column(String, primary_key=True, default=_new_uuid)
    thread_id = Column(String, ForeignKey("conversation_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    role      = Column(String, nullable=False)          # "user" | "assistant"
    content   = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Dados extras para rerender o módulo UI sem nova chamada
    ui_module = Column(String, nullable=True)           # "EmailThread" | "WhatsAppThread" | ...
    data      = Column(JSON, nullable=True)             # payload do módulo
    logs      = Column(JSON, nullable=True)             # streaming logs (list)
    sources   = Column(Integer, nullable=True)          # contagem de fontes usadas

    # Relacionamento
    thread = relationship("ConversationThread", back_populates="messages")

    __table_args__ = (
        Index("ix_cm_thread_time", "thread_id", "timestamp"),
    )


# ─────────────────────────────────────────────
# ActivityLog
# ─────────────────────────────────────────────

# Tipos de atividade suportados
ACTIVITY_TYPES = (
    "email_sent",
    "email_reply_sent",
    "email_reply_received",   # detectado por polling
    "whatsapp_sent",
    "whatsapp_received",
    "stage_changed",
    "deal_created",
    "note_added",
    "task_created",
)

ACTIVITY_STATUSES = (
    "pending",      # ação aprovada mas ainda não executada (raro)
    "completed",    # executada com sucesso
    "failed",       # erro na execução
    "awaiting_reply",  # email enviado, aguardando resposta
    "replied",      # resposta detectada
    "cancelled",    # rejeitada pelo usuário
)


class ActivityLog(Base):
    """Registro imutável de cada ação executada pelo agente."""
    __tablename__ = "activity_logs"

    id            = Column(String, primary_key=True, default=_new_uuid)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    thread_id     = Column(String, ForeignKey("conversation_threads.id", ondelete="SET NULL"), nullable=True, index=True)

    # Tipo e status
    activity_type = Column(String, nullable=False, index=True)   # ver ACTIVITY_TYPES
    status        = Column(String, default="completed", index=True)

    # Payload estruturado — varia por tipo
    # email_sent:    {to_name, to_email, subject, message_preview, entry_id}
    # whatsapp_sent: {to_name, to_phone, message_preview}
    # stage_changed: {from_stage, to_stage, deal_id, deal_title}
    payload       = Column(JSON, nullable=True)

    # Timestamps
    created_at    = Column(DateTime, default=datetime.utcnow, index=True)
    resolved_at   = Column(DateTime, nullable=True)   # quando status mudou para replied/failed

    # Para emails: id do item no Exchange/Outlook para polling de resposta
    external_ref  = Column(String, nullable=True)    # entryId do Exchange

    # Relacionamentos
    organization  = relationship("Organization", lazy="select")
    thread        = relationship("ConversationThread", back_populates="activities")

    __table_args__ = (
        Index("ix_al_org_type_created", "org_id", "activity_type", "created_at"),
        Index("ix_al_status_type", "status", "activity_type"),  # para polling
    )
