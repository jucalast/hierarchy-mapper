"""
services.ai.llm — LLM Gateway unificado.

Arquitetura:
    base.py            → Interfaces (LLMMessage, LLMProvider, LLMResult)
    gemini_provider.py → Google Gemini (primário)
    groq_provider.py   → Groq (fallback)
    claude_provider.py → Anthropic Claude (preparado; ativa com ANTHROPIC_API_KEY)
    router.py          → Executa fallback chain com circuit breaker e cache
    metrics.py         → (reexporta de core.metrics para conveniência)

API pública:
    from services.ai.llm import ask_llm, LLMTier
    answer = await ask_llm(prompt, json_mode=True, tier=LLMTier.STANDARD)
"""
from services.ai.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResult,
    LLMTier,
    LLMError,
    NoProviderAvailableError,
)
from services.ai.llm.router import (
    ask_llm, LLMRouter, get_router,
    set_preferred_model, get_preferred_model, get_strict_mode_preference
)

__all__ = [
    "LLMMessage",
    "LLMProvider",
    "LLMResult",
    "LLMTier",
    "LLMError",
    "NoProviderAvailableError",
    "ask_llm",
    "LLMRouter",
    "get_router",
    "set_preferred_model",
    "get_preferred_model",
    "get_strict_mode_preference",
]
