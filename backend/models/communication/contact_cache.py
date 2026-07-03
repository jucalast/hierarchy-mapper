"""
models.communication.contact_cache
====================================
Cache de conversas com contatos externos (WhatsApp e Email).

Cada linha representa o snapshot mais recente das mensagens trocadas com um
contato em um canal específico. Populado automaticamente toda vez que o
agente busca mensagens — evita re-fetches caros ao CRM/email.

ContactConversationCache — snapshot de conversa por (contact_identifier, channel)
"""
from __future__ import annotations

import json
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, Index
from core.infra.database import Base

CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_EMAIL = "email"


class ContactConversationCache(Base):
    """Snapshot persistido de uma conversa com um contato externo."""
    __tablename__ = "contact_conversation_cache"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    contact_identifier    = Column(String, nullable=False, index=True)  # phone (digits) ou email
    contact_name          = Column(String, nullable=False)
    channel               = Column(String, nullable=False)              # "whatsapp" | "email"
    org_id                = Column(Integer, nullable=True, index=True)  # FK organizations (sem FK constraint para resiliência)
    org_name              = Column(String, nullable=True)
    chat_id               = Column(String, nullable=True)               # WhatsApp: "5519...@c.us" ou LID@lid
    messages_json         = Column(Text, nullable=False, default="[]")  # JSON array de mensagens
    message_count         = Column(Integer, nullable=False, default=0)
    fetched_at            = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_message_preview  = Column(String, nullable=True)              # primeiros 120 chars da última msg
    has_unread            = Column(Integer, nullable=False, default=0)  # 1 = chegou mensagem nova desde o último acesso à UI
    is_key_contact        = Column(Integer, nullable=False, default=0)  # 1 = decisor/alta senioridade (detectado via Employee)

    __table_args__ = (
        UniqueConstraint("contact_identifier", "channel", name="uq_contact_conv_cache"),
        Index("ix_ccc_fetched_at", "fetched_at"),
        Index("ix_ccc_org_channel", "org_id", "channel"),
    )

    def get_messages(self) -> list:
        try:
            return json.loads(self.messages_json or "[]")
        except Exception:
            return []

    def set_messages(self, msgs: list) -> None:
        self.messages_json = json.dumps(msgs, ensure_ascii=False)
        self.message_count = len(msgs)
        if msgs:
            # E-mails são ordenados decrescente (mais novo primeiro),
            # WhatsApp e outros são ordenados crescente (mais novo por último).
            last = msgs[0] if self.channel == CHANNEL_EMAIL else msgs[-1]
            body = last.get("body") or last.get("preview") or last.get("content") or ""
            self.last_message_preview = body[:120] if body else None
        self.fetched_at = datetime.utcnow()
