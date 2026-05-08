import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship
from core.database import Base

class ICPConfig(Base):
    __tablename__ = "icp_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    industries_target = Column(JSON) # List of strings
    company_size_target = Column(JSON) # List of strings
    decision_makers = Column(JSON) # List of strings
    disqualifiers = Column(JSON) # List of strings
    pain_points = Column(JSON) # List of strings

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
