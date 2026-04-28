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
import json
import os
import time
from contextvars import ContextVar
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
from services.ai.llm.gemini_provider import GeminiProvider, GeminiDailyQuotaExhaustedError
from services.ai.llm.groq_provider import GroqProvider
from services.ai.llm.gemini_quota import get_quota_tracker

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# ContextVar & Global Preference — preferência de modelo persistente
# ---------------------------------------------------------------------------
# Definido no início do request (chat_service.handle).
# Se estivermos fora de um request (ex: background triggers), cai para a última 
# escolha global do usuário persistida em disco.
_request_preferred_model: ContextVar[Optional[str]] = ContextVar(
    "request_preferred_model", default=None
)

_PREFERENCE_FILE = "ai_preference.json"

def _load_global_preference() -> tuple[Optional[str], bool]:
    if os.path.exists(_PREFERENCE_FILE):
        try:
            with open(_PREFERENCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("preferred_model"), data.get("strict_mode", False)
        except Exception:
            pass
    return None, False

def _save_global_preference(model: str, strict_mode: bool = False):
    try:
        with open(_PREFERENCE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "preferred_model": model, 
                "strict_mode": strict_mode,
                "updated_at": time.time()
            }, f)
    except Exception:
        pass

# Estado global persistente
_pref_model, _pref_strict = _load_global_preference()
_app_global_preferred_model: Optional[str] = _pref_model
_app_global_strict_mode: bool = _pref_strict


# ContextVar para strict mode no request atual
_request_strict_mode: ContextVar[bool] = ContextVar(
    "request_strict_mode", default=False
)

def set_preferred_model(model: Optional[str], strict_mode: bool = False) -> None:
    """Registra o modelo preferido e persiste como padrão global."""
    _request_preferred_model.set(model or None)
    _request_strict_mode.set(strict_mode)
    if model:
        global _app_global_preferred_model, _app_global_strict_mode
        _app_global_preferred_model = model
        _app_global_strict_mode = strict_mode
        _save_global_preference(model, strict_mode)

def get_preferred_model() -> Optional[str]:
    """Retorna o modelo preferido do request atual ou a última escolha global."""
    return _request_preferred_model.get() or _app_global_preferred_model

def get_strict_mode_preference() -> bool:
    """Retorna se o strict mode está ativo no request ou globalmente."""
    return _request_strict_mode.get() or _app_global_strict_mode

# ---------------------------------------------------------------------------
# Throttler global — serializa chamadas LLM para não explodir o rate limit
# ---------------------------------------------------------------------------
# Permite no máximo 1 chamada LLM simultânea no sistema inteiro.
# Garante também um intervalo mínimo de 2s entre chamadas consecutivas.
# Gemini free: ~15 req/min → 1 req a cada 4s é seguro.
# Groq free: quota muito menor — o circuit breaker cuida do resto.
# Permite no máximo 2 chamadas LLM simultâneas no sistema inteiro.
# Garante também um intervalo mínimo de 1.0s entre chamadas consecutivas.
# Gemini free: ~15 req/min → 1 req a cada 4s é seguro, mas com 2.0-flash-lite e fallback, 1s é aceitável.
_llm_semaphore = asyncio.Semaphore(2)
_last_llm_call_time: float = 0.0
_MIN_CALL_GAP_SEC: float = 1.0  

# Rastreia o tempo do último rate-limit por provider para skip rápido
_provider_rate_limited_until: dict[str, float] = {}


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
    def chain(self, preferred: Optional[str] = None) -> List[LLMProvider]:
        """
        Retorna providers na ordem de tentativa.
        Se `preferred` for fornecido (ex: 'gemini', 'groq', 'claude' OU um model_id específico),
        coloca o provider correspondente no início da chain sem remover os outros como fallback.
        """
        base_order = list(settings.ai_fallback_providers or ["gemini", "groq"])
        
        # 1. Tenta identificar o provider se 'preferred' for um model_id (ex: 'gemini-2.0-flash')
        target_provider = None
        if preferred:
            if preferred in self._providers:
                target_provider = preferred
            else:
                # Busca qual provider contém esse modelo
                if preferred in settings.ai_gemini_models_list:
                    target_provider = "gemini"
                elif preferred in settings.ai_groq_models_list:
                    target_provider = "groq"
                elif preferred in settings.ai_claude_models_list:
                    target_provider = "claude"
        
        # 2. Constrói a ordem com o provider alvo no topo
        if target_provider:
            order = [target_provider] + [p for p in base_order if p != target_provider]
        else:
            order = base_order
            
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
        preferred_model: Optional[str] = None,
        strict_model: bool = False,
    ) -> LLMResult:
        """
        Tenta cada provider em sequência. Retorna no primeiro sucesso.
        Se `preferred_model` for passado, ele lidera a chain (com fallback nos demais).
        Se `strict_model=True`, força o modelo selecionado com retry agressivo (sem fallback).
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
                preferred_model or "",
                [(m.role, m.content) for m in messages],
            )
            cached = self._cache.get(key)
            if isinstance(cached, LLMResult):
                log.debug("llm.cache.hit", tier=tier.value)
                return cached

        # Se strict_model=True, força apenas o provider do modelo selecionado
        if strict_model and preferred_model:
            target_provider = None
            if preferred_model in self._providers:
                target_provider = preferred_model
            elif preferred_model in settings.ai_gemini_models_list:
                target_provider = "gemini"
            elif preferred_model in settings.ai_groq_models_list:
                target_provider = "groq"
            elif preferred_model in settings.ai_claude_models_list:
                target_provider = "claude"
            
            if target_provider and target_provider in self._providers:
                providers = [self._providers[target_provider]]
                log.info("llm.strict_mode", provider=target_provider, model=preferred_model)
            else:
                providers = []
        else:
            providers = self.chain(preferred=preferred_model)
            
        if not providers:
            raise NoProviderAvailableError("No LLM providers registered.")

        any_available = False
        last_error: Optional[str] = None
        daily_quota_exhausted_error: Optional[GeminiDailyQuotaExhaustedError] = None

        # Throttle global: serializa chamadas LLM e garante gap mínimo entre elas.
        # Isso evita disparar múltiplas chamadas simultâneas que explodem o rate limit
        # das APIs gratuitas (Gemini free tier, Groq free: mais restrito ainda).
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

                # Skip rápido se o provider foi rate-limitado recentemente
                cooldown_until = _provider_rate_limited_until.get(provider.name, 0)
                if time.monotonic() < cooldown_until:
                    remaining = round(cooldown_until - time.monotonic())
                    log.debug("llm.provider.skipped_cooldown", provider=provider.name, remaining_sec=remaining)
                    continue

                any_available = True

                # Retry loop para o provedor atual
                # Em strict mode: retry agressivo (até 10x) com backoff exponencial
                max_provider_retries = 10 if strict_model else 3
                for attempt in range(1, max_provider_retries + 1):
                    try:
                        result = await provider.complete(
                            messages,
                            json_mode=json_mode,
                            temperature=temp,
                            tier=tier,
                            preferred_model=preferred_model,
                        )
                        # Sucesso — limpa cooldown do provider
                        _provider_rate_limited_until.pop(provider.name, None)
                        if cache_enabled and key:
                            self._cache.set(key, result)
                        return result

                    except GeminiDailyQuotaExhaustedError as e:
                        # Cota diária do Gemini esgotada — não adianta retry
                        daily_quota_exhausted_error = e
                        last_error = f"gemini_daily_quota_exhausted"
                        log.warning("llm.gemini.daily_quota_exhausted_router",
                                    strict_mode=strict_model)
                        if strict_model:
                            # Em strict mode: não cai em outro provider — avisa o usuário
                            raise e
                        # Em modo normal: tenta próximo provider
                        break

                    except LLMError as e:
                        last_error = f"{provider.name}: {e}"
                        is_rate_limit = "rate_limit" in str(e).lower() or "429" in str(e).lower()

                        # LOG DE FALLBACK: Avisa que vamos tentar o próximo (apenas se não for strict mode)
                        if not strict_model:
                            next_provider_idx = providers.index(provider) + 1
                            if next_provider_idx < len(providers):
                                next_p = providers[next_provider_idx]
                                log.warning("llm.fallback",
                                            reason=f"Falha no {provider.name} ({str(e)[:100]})",
                                            next_attempt=next_p.name)

                        if is_rate_limit:
                            import re as _re
                            m = _re.search(r"retry_after[=:]\s*(\d+)", str(e).lower())

                            if strict_model:
                                # Strict mode: backoff exponencial, sempre retry
                                base_wait = int(m.group(1)) if m else 2
                                cooldown = min(base_wait * (2 ** (attempt - 1)), 60)
                                log.warning("llm.strict.retry",
                                            provider=provider.name, attempt=attempt, wait_sec=cooldown)
                                if attempt < max_provider_retries:
                                    await asyncio.sleep(cooldown)
                                    continue
                            else:
                                cooldown = int(m.group(1)) if m else (30 * attempt)
                                _provider_rate_limited_until[provider.name] = time.monotonic() + cooldown
                                log.warning("llm.provider.rate_limit_retry",
                                            provider=provider.name, attempt=attempt, wait_sec=min(cooldown, 10))
                                if attempt < max_provider_retries:
                                    await asyncio.sleep(min(cooldown, 5))
                                    continue

                        log.warning("llm.provider.failed",
                                    provider=provider.name, error=str(e)[:200])
                        break

                    except Exception as e:
                        last_error = f"{provider.name}: {type(e).__name__}: {e}"
                        log.exception("llm.provider.unexpected", provider=provider.name)

                        if not strict_model:
                            next_provider_idx = providers.index(provider) + 1
                            if next_provider_idx < len(providers):
                                next_p = providers[next_provider_idx]
                                log.warning("llm.fallback.unexpected", next_attempt=next_p.name)
                        break

        if not any_available:
            raise NoProviderAvailableError(
                "No LLM provider is available (missing keys or circuit open)."
            )

        # Se a única falha foi cota diária esgotada, re-levanta para o chat_service tratar
        if daily_quota_exhausted_error and last_error == "gemini_daily_quota_exhausted":
            raise daily_quota_exhausted_error

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
    preferred_model: Optional[str] = None,
    strict_model: bool = False,
) -> LLMResult:
    # Se o chamador não especificou um modelo, usa o preferido do request atual
    effective_model = preferred_model or get_preferred_model()
    # Se não explicitou strict, verifica preferência global
    effective_strict = strict_model or get_strict_mode_preference()
    messages = _build_messages(prompt, system, history)
    return await get_router().complete(
        messages,
        json_mode=json_mode,
        temperature=temperature,
        tier=tier,
        cacheable=cacheable,
        preferred_model=effective_model,
        strict_model=effective_strict,
    )
