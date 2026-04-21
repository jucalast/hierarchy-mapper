from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base
from datetime import datetime

class AutomatedAction(Base):
    __tablename__ = "automated_actions"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    task_type = Column(String)  # 'whatsapp_followup', 'email_reminder', 'pipedrive_sync'
    status = Column(String, default="pending")  # 'pending', 'completed', 'failed', 'cancelled'
    
    payload = Column(JSON)  # Dados da tarefa (mensagem, destinatário, etc)
    
    execute_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)
    
    last_error = Column(String, nullable=True)

    # Relacionamento opcional
    organization = relationship("Organization")
