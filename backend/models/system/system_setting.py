"""
models.system.system_setting
============================
Configuracoes do sistema em chave-valor JSON sem redeploy.

Usado para: preferencia de modelo LLM, perfil de negocio, ICP, hierarquia.
Campos: key (PK), category (agrupamento), value (JSON livre).
"""
from sqlalchemy import Column, String, JSON
from core.infra.database import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True, index=True)
    category = Column(String, index=True, nullable=False)
    value = Column(JSON, nullable=False)
