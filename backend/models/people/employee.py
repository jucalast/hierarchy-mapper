"""
models.people.employee
=======================
Model SQLAlchemy para pessoas (funcionários/contatos) vinculadas a organizações.

Campos relevantes para regras de negócio:
    seniority    → nível hierárquico (0=desconhecido, 2=analista, 3=coordenador,
                   4=gerente, 5=diretor, 6=sócio/C-level)
    department   → departamento normalizado ('compras', 'logistica', etc.)
    temperature  → classificação de relacionamento ('cold' | 'warm' | 'hot')
    is_discovery → 1 se o contato foi descoberto via B2B scanner (não do Pipedrive)
    source       → 'pipedrive' | 'discovery' | 'manual'
    matching_score → relevância ICP calculada pelo qualifier
"""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from core.infra.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    pipedrive_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, index=True)
    role = Column(String)
    department = Column(String, index=True, nullable=True)
    seniority = Column(Integer, default=0, index=True)
    linkedin_url = Column(String, unique=True, index=True)
    profile_pic = Column(Text, nullable=True)
    email = Column(String, nullable=True, index=True)
    description = Column(Text, nullable=True)
    location = Column(String, nullable=True)
    phone = Column(String, nullable=True, index=True)
    whatsapp_number = Column(String, nullable=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
    )
    manager_id = Column(String, nullable=True, index=True)
    temperature = Column(String, nullable=True, index=True)
    matching_score = Column(Integer, nullable=True)
    evidence = Column(Text, nullable=True)
    prospecting_context = Column(Text, nullable=True)
    education = Column(Text, nullable=True)
    headline = Column(String, nullable=True)
    is_discovery = Column(Integer, default=0, index=True)
    source = Column(String, default="discovery", index=True)
    last_scanned = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    organization = relationship("Organization", back_populates="employees")

    __table_args__ = (
        # Filtros mais comuns por empresa + departamento e empresa + manager
        Index("ix_emp_company_department", "company_id", "department"),
        Index("ix_emp_company_manager", "company_id", "manager_id"),
        Index("ix_emp_company_seniority", "company_id", "seniority"),
    )
