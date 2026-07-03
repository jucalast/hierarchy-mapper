"""
models.crm.integration
=======================
Credenciais e configuracoes de integracoes externas por Tenant.

O campo credentials_encrypted armazena JSON com tokens/senhas.
Integracoes suportadas: pipedrive | whatsapp | outlook | google_workspace
"""
import uuid
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
from core.infra.database import Base, SafeJSON

class Integration(Base):
    __tablename__ = "integrations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    type = Column(String) # pipedrive | whatsapp | outlook | google_workspace
    credentials_encrypted = Column(SafeJSON) # Tokens e senhas
    custom_settings = Column(SafeJSON) # Mapeamento de campos customizados

    tenant = relationship("Tenant", back_populates="integrations")
