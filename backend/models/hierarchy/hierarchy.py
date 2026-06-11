"""
models.hierarchy.hierarchy
===========================
Configuracao de mapeamento de hierarquia organizacional por Tenant.

Define departamento-foco (compras|logistica), keywords proibidas,
whitelist de cargos, regras de senioridade e mapeamento de departamento.
"""
import uuid
from sqlalchemy import Column, String, ForeignKey, JSON
from sqlalchemy.orm import relationship
from core.infra.database import Base

class HierarchyConfig(Base):
    __tablename__ = "hierarchy_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    department_focus = Column(String) # compras | logistica | vendas
    forbidden_keywords = Column(JSON) # Map of department -> list of words
    whitelist_keywords = Column(JSON) # List of strings
    seniority_rules = Column(JSON) # Map of keywords -> score
    department_mapping_rules = Column(JSON) # Map of keywords -> tag

    tenant = relationship("Tenant", back_populates="hierarchy_configs")
