import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.infra.database import Base

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    domain = Column(String, nullable=True, index=True)
    status = Column(String, default="active") # active | suspended
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    business_profiles = relationship("BusinessProfile", back_populates="tenant", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="tenant", cascade="all, delete-orphan")
    reference_clients = relationship("ReferenceClient", back_populates="tenant", cascade="all, delete-orphan")
    integrations = relationship("Integration", back_populates="tenant", cascade="all, delete-orphan")
    icp_configs = relationship("ICPConfig", back_populates="tenant", cascade="all, delete-orphan")
    hierarchy_configs = relationship("HierarchyConfig", back_populates="tenant", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    role = Column(String) # Ex: Representante Comercial
    user_role = Column(String, default="seller") # admin | seller | viewer
    hashed_password = Column(String, nullable=True) # Senha criptografada para login
    phone = Column(String)
    signature_template = Column(String) # Assinatura HTML customizada
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tenant = relationship("Tenant", back_populates="users")
