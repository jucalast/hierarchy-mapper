"""
LLM Router — executa a fallback chain com cache de respostas idempotentes.

Uso:
    from services.ai.llm import ask_llm, LLMTier

    result = await ask_llm(
        prompt="Qual a capital?",
        json_mode=False,
        tier=LLMTier.FAST,
    )
    print(result.text, result.provider, result.model)

Ou com histórico:
    result = await ask_llm(
        prompt="...",
        history=[{"role":"user","content":"oi"}, ...],
        system="Você é um assistente B2B.",
        json_mode=True,
    )
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable, List, Optional, Union

from core.cache import cache_key_for, get_cache
from core.config import settings
from core.logging_config import get_logger
from services.ai.llm.base import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMResult,
    LLMTier,
    NoProviderAvailableError,
)
from services.ai.llm.claude_provider import ClaudeProvider
from services.ai.llm.gemini_provider import GeminiProvider
from services.ai.llm.groq_provider import GroqProvider

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Throttler global — serializa chamadas LLM para não explodir o rate limit
# ---------------------------------------------------------------------------
# Permite no máximo 1 chamada LLM simultânea no sistema inteiro.
# Garante também um intervalo mínimo de 1.2s entre chamadas consecutivas.
_llm_semaphore = asyncio.Semaphore(1)
_last_llm_call_time: float = 0.0
_MIN_CALL_GAP_SEC: float = 1.2  # Intervalo mínimo entre chamadas (ajuste conforme cota)


# ---------------------------------------------------------------------------
# Normalização de input → List[LLMMessage]
# ---------------------------------------------------------------------------

def _normalize_history(history: Any) -> List[LLMMessage]:
    if not history:
        return []
    out: List[LLMMessage] = []
    for m in history:
        if isinstance(m, LLMMessage):
            out.append(m)
            continue
        if hasattr(m, "role") and hasattr(m, "content"):
            out.append(LLMMessage(role=str(m.role), content=str(m.content or "")))
            continue
        if isinstance(m, dict):
            out.append(
                LLMMessage(
                    role=str(m.get("role", "user")),
                    content=str(m.get("content") or ""),
                )
            )
    return out


def _build_messages(
    prompt: str,
    system: Optional[str],
    history: Any,
) -> List[LLMMessage]:
    msgs: List[LLMMessage] = []
    if system:
        msgs.append(LLMMessage(role="system", content=system))
    msgs.extend(_normalize_history(history))
    msgs.append(LLMMessage(role="user", content=prompt))
    return msgs


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class LLMRouter:
    """Orquestra a fallback chain entre providers LLM."""

    _instance: Optional["LLMRouter"] = None

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {
            "gemini": GeminiProvider(),
            "groq": GroqProvider(),
            "claude": ClaudeProvider(),
        }
        self._cache = get_cache(
            "llm.responses",
            ttl_sec=settings.ai.response_cache_ttl_sec,
            max_entries=settings.ai.response_cache_max_entries,
        )

    # ------------------------------------------------------------------
    @classmethod
    def instance(cls) -> "LLMRouter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    def chain(self) -> List[LLMProvider]:
        """Retorna providers na ordem de tentativa (filtrando inexistentes)."""
        order = settings.ai_fallback_providers or ["gemini", "groq"]
        return [self._providers[n] for n in order if n in self._providers]

    # ------------------------------------------------------------------
    async def complete(
        self,
        messages: List[LLMMessage],
        *,
        json_mode: bool = False,
        temperature: Optional[float] = None,
        tier: LLMTier = LLMTier.STANDARD,
        cacheable: bool = True,
    ) -> LLMResult:
        """
        Tenta cada provider em sequência. Retorna no primeiro sucesso.
        Usa cache de respostas se cacheable e temperature <= 0.2.
        """
        temp = temperature if temperature is not None else settings.ai.temperature_default
        cache_enabled = (
            cacheable
            and settings.ai.response_cache_enabled
            and temp <= 0.21
        )

        key: Optional[str] = None
        if cache_enabled:
            key = cache_key_for(
                "llm.v1",
                json_mode,
                round(temp, 2),
                tier.value,
                [(m.role, m.content) for m in messages],
            )
            cached = self._cache.get(key)
            if isinstance(cached, LLMResult):
                log.debug("llm.cache.hit", tier=tier.value)
                return cached

        providers = self.chain()
        if not providers:
            raise NoProviderAvailableError("No LLM providers registered.")

        any_available = False
        last_error: Optional[str] = None

        # Throttle global: serializa chamadas LLM e garante gap mínimo entre elas.
        # Isso evita disparar múltiplas chamadas simultâneas que explodem o rate limit
        # das APIs gratuitas (Gemini free: ~15 req/min, Groq free: ainda mais restrito).
        global _last_llm_call_time
        async with _llm_semaphore:
            now = time.monotonic()
            gap = _MIN_CALL_GAP_SEC - (now - _last_llm_call_time)
            if gap > 0:
                log.debug("llm.throttle.wait", gap_ms=round(gap * 1000))
                await asyncio.sleep(gap)
            _last_llm_call_time = time.monotonic()

            for provider in providers:
                if not provider.available:
                    log.debug("llm.provider.unavailable", provider=provider.name)
                    continue
                any_available = True

                # Retry loop para o provedor atual (backoff progressivo em 429)
                max_provider_retries = 3
                for attempt in range(1, max_provider_retries + 1):
                    try:
                        result = await provider.complete(
                            messages,
                            json_mode=json_mode,
                            temperature=temp,
                            tier=tier,
                        )
                        if cache_enabled and key:
                            self._cache.set(key, result)
                        return result
                    except LLMError as e:
                        last_error = f"{provider.name}: {e}"
                        if "rate_limit" in str(e).lower() or "429" in str(e).lower():
                            if attempt < max_provider_retries:
                                wait_time = 2.5 * attempt
                                log.warning("llm.provider.rate_limit_retry",
                                            provider=provider.name, attempt=attempt, wait_sec=wait_time)
                                await asyncio.sleep(wait_time)
                                continue
                        log.warning("llm.provider.failed",
                                    provider=provider.name, error=str(e)[:200])
                        break
                    except Exception as e:
                        last_error = f"{provider.name}: {type(e).__name__}: {e}"
                        log.exception("llm.provider.unexpected", provider=provider.name)
                        break

        if not any_available:
            raise NoProviderAvailableError(
                "No LLM provider is available (missing keys or circuit open)."
            )
        raise NoProviderAvailableError(
            f"All LLM providers failed. Last error: {last_error}"
        )


def get_router() -> LLMRouter:
    return LLMRouter.instance()


# ---------------------------------------------------------------------------
# Helper funcional — substituto direto de `ask_gemini`
# ---------------------------------------------------------------------------

async def ask_llm(
    prompt: str,
    *,
    system: Optional[str] = None,
    history: Any = None,
    json_mode: bool = False,
    temperature: Optional[float] = None,
    tier: LLMTier = LLMTier.STANDARD,
    cacheable: bool = True,
) -> LLMResult:
    messages = _build_messages(prompt, system, history)
    return await get_router().complete(
        messages,
        json_mode=json_mode,
        temperature=temperature,
        tier=tier,
        cacheable=cacheable,
    )
