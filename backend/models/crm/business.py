"""
models.crm.business
===================
Modelos ORM para dados de negocio do Tenant.

Classes:
    BusinessProfile  -- segmento, diferenciais, metodologia, value propositions
    Product          -- produto com nome, descricao e casos de uso
    ReferenceClient  -- cliente de referencia com segmento e dor resolvida
"""
import uuid
from sqlalchemy import Column, String, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from core.infra.database import Base

class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    segment = Column(String) # Ex: Embalagens Manuais
    differentials = Column(JSON) # List of strings
    methodology = Column(Text) # Guia de prospecção do agente
    value_propositions = Column(JSON) # Dictionary of value propositions
    presentation_path = Column(String) # Caminho para o PDF de apresentação
    signature_path = Column(String) # Caminho para a imagem de assinatura

    tenant = relationship("Tenant", back_populates="business_profiles")

class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    use_cases = Column(JSON) # List of strings

    tenant = relationship("Tenant", back_populates="products")

class ReferenceClient(Base):
    __tablename__ = "reference_clients"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    segment = Column(String)
    pain_solved = Column(Text)

    tenant = relationship("Tenant", back_populates="reference_clients")
