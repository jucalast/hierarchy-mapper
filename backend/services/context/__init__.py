"""
Pacote Context — Re-exporta o ContextService.
Permite imports limpos: `from services.context import ContextService`
"""
from services.context_service import ContextService

__all__ = ["ContextService"]
