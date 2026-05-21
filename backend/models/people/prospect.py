import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from core.infra.database import Base


class ProspectSession(Base):
    __tablename__ = "prospect_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Localização da busca
    lat = Column(String, nullable=True)          # latitude do centro da busca
    lng = Column(String, nullable=True)          # longitude do centro da busca
    radius_km = Column(Integer, nullable=True)   # raio em km
    city_name = Column(String, nullable=True)    # cidade resolvida por geocoding reverso
    # Segmentos buscados (JSON list)
    segments_searched = Column(JSON, nullable=True)
    status = Column(String, default="running", index=True)  # running | completed | failed
    total_found = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    leads = relationship(
        "ProspectLead",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ProspectLead.icp_score.desc()",
    )


class ProspectLead(Base):
    __tablename__ = "prospect_leads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("prospect_sessions.id", ondelete="CASCADE"), index=True)

    # Dados da empresa
    name = Column(String, index=True)
    cnpj = Column(String, nullable=True)
    domain = Column(String, nullable=True)
    address = Column(String, nullable=True)
    segment = Column(String, nullable=True)
    size_label = Column(String, nullable=True)      # pequena | média | grande
    employee_count = Column(String, nullable=True)  # "100-500" estimativa
    exports = Column(Integer, default=0)            # 0=não, 1=sim
    linkedin_url = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    # Contatos-chave encontrados via LinkedIn
    contacts = Column(JSON, nullable=True)          # [{name, role, linkedin_url, department}]

    # Qualificação ICP
    icp_score = Column(Integer, default=0, index=True)
    icp_tier = Column(String, nullable=True, index=True)    # A | B | C
    icp_reasons = Column(JSON, nullable=True)
    icp_penalties = Column(JSON, nullable=True)
    icp_recommendation = Column(Text, nullable=True)
    outreach_angle = Column(Text, nullable=True)
    relevance_signal = Column(Text, nullable=True)

    # Status no Pipedrive global
    pipedrive_status = Column(String, default="new")  # new | lost_deal | stale | active
    pipedrive_org_id = Column(Integer, nullable=True)
    pipedrive_last_activity = Column(DateTime(timezone=True), nullable=True)
    pipedrive_deal_info = Column(JSON, nullable=True)  # {title, status, stage, value, days_inactive}

    # Coordenadas para o mapa
    lat = Column(String, nullable=True)
    lng = Column(String, nullable=True)

    # Ação do usuário
    status = Column(String, default="pending", index=True)  # pending | approved | rejected | created
    pipedrive_created_id = Column(Integer, nullable=True)
    pipedrive_deal_id = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ProspectSession", back_populates="leads")

    __table_args__ = (
        Index("ix_prospect_session_score", "session_id", "icp_score"),
        Index("ix_prospect_tier_status", "icp_tier", "status"),
    )
