"""
models.crm.icp
==============
Ideal Customer Profile com regras de scoring dinamicas por padrao.

ICPConfig define criterios qualitativos (industrias, tamanho, pain points).
ICPScoreRule aplica pesos numericos para calcular icp_score (0-100) por org.

Classes: ICPConfig, ICPScoreRule
"""
import uuid
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from core.infra.database import Base, SafeJSON

class ICPConfig(Base):
    __tablename__ = "icp_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    industries_target = Column(SafeJSON) # List of strings
    company_size_target = Column(SafeJSON) # List of strings
    decision_makers = Column(SafeJSON) # List of strings
    disqualifiers = Column(SafeJSON) # List of strings
    pain_points = Column(SafeJSON) # List of strings

    tenant = relationship("Tenant", back_populates="icp_configs")
    score_rules = relationship("ICPScoreRule", back_populates="icp_config", cascade="all, delete-orphan")

class ICPScoreRule(Base):
    __tablename__ = "icp_score_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    icp_config_id = Column(String(36), ForeignKey("icp_configs.id"), nullable=False, index=True)
    rule_type = Column(String) # segment | size | export | integration
    value_pattern = Column(String) # Regex ou palavra-chave
    weight_score = Column(Integer) # +40, -20
    reason = Column(String) # Motivo exibido no log

    icp_config = relationship("ICPConfig", back_populates="score_rules")
