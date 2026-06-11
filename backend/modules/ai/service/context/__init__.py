"""Serviços de contexto de negócio para o agente."""
from .business_context_service import BusinessContextService
from . import business_context
from .business_context import (
    ICP, load_db_setting,
    get_icp_score, get_cold_outreach_angle, get_business_context_for_prompt,
)

__all__ = [
    "BusinessContextService", "business_context", "ICP", "load_db_setting",
    "get_icp_score", "get_cold_outreach_angle", "get_business_context_for_prompt",
]
