"""
models.organization.organization
==================================
Model SQLAlchemy para empresas descobertas/sincronizadas do Pipedrive ou B2B scanner.

Nota sobre campos:
    source       → origem do registro ('pipedrive' | 'outlook' | 'manual' | 'discovery')
    icp_score    → score de 0 a 100 calculado pelo ICPConfig do Tenant
    icp_tier     → classificação derivada do score (A | B | C)
    is_excluded  → 1 = oculta do UI (soft-delete)
    last_enrichment → timestamp do último enriquecimento de dados
"""
from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from core.infra.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    pipedrive_id = Column(Integer, unique=True, index=True)
    name = Column(String, index=True)
    cnpj = Column(String, unique=True, index=True, nullable=True)
    domain = Column(String, index=True, nullable=True)
    address = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    owner_id = Column(Integer, index=True)
    category = Column(String, nullable=True, index=True)            # Ex: "Compras", "Logística"
    product_focus = Column(String, nullable=True, index=True)       # Ex: "Embalagens", "TI"
    linkedin_url = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    photo_url = Column(Text, nullable=True)  # Foto da empresa (Google Places), cacheada em base64
    icp_score = Column(Integer, nullable=True)                      # Score de 0 a 100
    icp_tier = Column(String, nullable=True)                       # A | B | C
    is_excluded = Column(Integer, server_default="0", index=True)   # 1 = Excluída/Oculta
    source = Column(String, default="pipedrive", index=True)        # Ex: pipedrive, outlook, manual
    temperature = Column(String, nullable=True, index=True)         # cold, warm, hot, contacted
    prospecting_context = Column(Text, nullable=True)               # Detalhes descritivos da origem e relação
    last_enrichment = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
    )

    # Relacionamento — habilita selectinload para evitar N+1
    employees = relationship(
        "Employee",
        back_populates="organization",
        lazy="select",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # Listagem comum: somente não-excluídas, ordenadas por enriquecimento
        Index("ix_org_active_recent", "is_excluded", "last_enrichment"),
        # Busca por categoria/foco em filtros
        Index("ix_org_category_focus", "category", "product_focus"),
    )
