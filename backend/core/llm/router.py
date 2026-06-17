"""
LLM Router — executa a fallback chain com cache de respostas idempotentes.

Uso:
    from core.llm import ask_llm, LLMTier

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

from core.infra.cache import cache_key_for, get_cache
from core.config import settings
from core.observability.logging_config import get_logger
from core.llm.base import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMResult,
    LLMTier,
    NoProviderAvailableError,
)
from core.llm.providers.claude import ClaudeProvider
from core.llm.providers.gemini import GeminiProvider, GeminiDailyQuotaExhaustedError
from core.llm.providers.groq import GroqProvider
from core.llm.gemini_quota import get_quota_tracker
from core.llm.providers.openai_compat import OpenAICompatProvider
from core.llm.providers.ollama import OllamaProvider

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

_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PREFERENCE_FILE = os.path.join(_backend_dir, "ai_preference.json")

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


# ContextVar para strict mode no request atual — Optional[bool] para distinguir
# "não definido" (None) de "explicitamente False" (fallback permitido)
_request_strict_mode: ContextVar[Optional[bool]] = ContextVar(
    "request_strict_mode", default=None
)

def set_preferred_model(model: Optional[str], strict_mode: bool = False) -> None:
    """
    Registra o modelo preferido para o request atual e persiste globalmente.

    Args:
        model: ID do modelo (ex: 'gemini-2.5-flash', 'claude-sonnet-4-5').
               None limpa a preferência do request atual (usa o global).
        strict_mode: Se True, desativa fallback — usa somente o modelo escolhido.
                     Útil para cenários onde o usuário explicitamente selecionou um modelo.
    """
    _request_preferred_model.set(model or None)
    _request_strict_mode.set(strict_mode)
    if model:
        global _app_global_preferred_model, _app_global_strict_mode
        _app_global_preferred_model = model
        _app_global_strict_mode = strict_mode
        _save_global_preference(model, strict_mode)

def get_preferred_model() -> Optional[str]:
    """
    Retorna o modelo preferido para a chamada LLM atual.

    Prioridade: preferência do request atual (ContextVar) → última escolha global
    persistida dinamicamente em ai_preference.json.
    """
    req = _request_preferred_model.get()
    if req:
        return req
    
    # Recarrega do arquivo em tempo de execução para sincronia com processos em background (workers)
    model, _ = _load_global_preference()
    return model or _app_global_preferred_model

def get_strict_mode_preference() -> bool:
    """Retorna se o strict mode está ativo no request ou globalmente.

    O ContextVar tem prioridade sobre o global — se o request explicitamente
    definiu False, respeita mesmo que o global seja True.
    """
    request_val = _request_strict_mode.get()
    if request_val is not None:
        return request_val
    
    # Recarrega do arquivo em tempo de execução para sincronia com processos em background (workers)
    _, strict = _load_global_preference()
    return strict

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
_MIN_CALL_GAP_SEC: float = 3.0  

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
# Classificação de Tamanhos de Modelo e Limites de Contexto (Ordenação Adaptativa)
# ---------------------------------------------------------------------------
# Mapeamento de modelos para seu ranking de tamanho (1=Menor/Mais barato, 2=Médio, 3=Maior/Deep/Raciocínio pesado)
# e limites de contexto reais (tokens)
MODEL_SPECS = {
    # Gemini
    "gemini-2.5-flash-lite":                     {"size": 1, "context_limit": 1_048_576},
    "gemini-2.5-flash":                          {"size": 2, "context_limit": 1_048_576},
    "gemini-2.5-pro":                            {"size": 3, "context_limit": 1_048_576},
    "gemini-2.0-flash-exp":                      {"size": 2, "context_limit": 1_048_576},
    "gemini-1.5-flash":                          {"size": 2, "context_limit": 1_048_576},
    "gemini-flash-latest":                       {"size": 2, "context_limit": 1_048_576},

    # Groq
    "llama-3.1-8b-instant":                      {"size": 1, "context_limit": 131_072},
    "llama-3.3-70b-versatile":                   {"size": 3, "context_limit": 131_072},
    "llama-3.1-70b-versatile":                   {"size": 3, "context_limit": 131_072},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"size": 2, "context_limit": 131_072},
    "qwen/qwen3-32b":                            {"size": 2, "context_limit": 131_072},
    "llama-3.2-11b-vision-preview":              {"size": 1, "context_limit": 131_072},
    "mixtral-8x7b-32768":                        {"size": 2, "context_limit": 32_768},
    "groq/compound":                             {"size": 3, "context_limit": 131_072},

    # Claude
    "claude-3-5-haiku-latest":                   {"size": 1, "context_limit": 200_000},
    "claude-3-5-sonnet-latest":                  {"size": 3, "context_limit": 200_000},
    "claude-sonnet-4-5":                         {"size": 3, "context_limit": 200_000},

    # Cerebras
    "llama3.1-8b":                               {"size": 1, "context_limit": 8_192},
    "llama-3.3-70b":                             {"size": 3, "context_limit": 8_192},
    "qwen-3-235b-a22b-instruct-2507":            {"size": 3, "context_limit": 64_000},
    "gpt-oss-120b":                              {"size": 3, "context_limit": 32_000},
    "zai-glm-4.7":                               {"size": 2, "context_limit": 32_000},

    # SambaNova
    "Llama-4-Scout-17B-16E-Instruct":            {"size": 2, "context_limit": 128_000},
    "Meta-Llama-3.3-70B-Instruct":               {"size": 3, "context_limit": 128_000},

    # DeepSeek
    "deepseek-chat":                             {"size": 3, "context_limit": 64_000},

    # Ollama
    "qwen2.5:3b":                                {"size": 1, "context_limit": 32_768},
    "qwen2.5:14b":                               {"size": 2, "context_limit": 128_000},
    "llama3.2":                                  {"size": 1, "context_limit": 128_000},
    "llama3":                                    {"size": 1, "context_limit": 8_192},
}

def get_model_size(model_name: str) -> int:
    """Retorna o ranking de tamanho do modelo (1=Small, 2=Medium, 3=Large/Deep)."""
    if model_name in MODEL_SPECS:
        return MODEL_SPECS[model_name]["size"]
    # Busca heurística por substrings se o modelo não estiver explicitamente mapeado
    model_lower = model_name.lower()
    if any(x in model_lower for x in ["lite", "8b", "haiku", "3b", "scout"]):
        return 1
    if any(x in model_lower for x in ["flash", "14b", "mixtral", "17b"]):
        return 2
    if any(x in model_lower for x in ["pro", "70b", "sonnet", "deep", "chat"]):
        return 3
    return 2  # default para médio

def get_model_context_limit(model_name: str) -> int:
    """Retorna o limite de contexto estimado do modelo em tokens."""
    if model_name in MODEL_SPECS:
        return MODEL_SPECS[model_name]["context_limit"]
    model_lower = model_name.lower()
    if "8b" in model_lower or "70b" in model_lower:
        if "cerebras" in model_lower:
            return 8_192
        return 128_000
    if "gemini" in model_lower:
        return 1_048_576
    if "claude" in model_lower:
        return 200_000
    return 32_768  # default seguro

def _estimate_tokens(messages: List[LLMMessage]) -> int:
    """Estima a quantidade de tokens total no prompt usando tiktoken ou fallback de caracteres."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for m in messages:
            total += len(enc.encode(m.content or "")) + 4
        return total
    except Exception:
        total_chars = sum(len(m.content or "") for m in messages)
        return max(total_chars // 4, 1)


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
            "sambanova": OpenAICompatProvider(
                name="sambanova",
                base_url="https://api.sambanova.ai/v1/chat/completions",
                api_key_fn=lambda: settings.SAMBANOVA_API_KEY,
                models_fn=lambda: settings.ai_sambanova_models_list,
                timeout_sec=60.0,
            ),
            "deepseek": OpenAICompatProvider(
                name="deepseek",
                base_url="https://api.deepseek.com/v1/chat/completions",
                api_key_fn=lambda: settings.DEEPSEEK_API_KEY,
                models_fn=lambda: settings.ai_deepseek_models_list,
                timeout_sec=45.0,
            ),
            "cerebras": OpenAICompatProvider(
                name="cerebras",
                base_url="https://api.cerebras.ai/v1/chat/completions",
                api_key_fn=lambda: settings.CEREBRAS_API_KEY,
                models_fn=lambda: settings.ai_cerebras_models_list,
                timeout_sec=30.0,
            ),
            "ollama": OllamaProvider(),
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
        if "ollama" not in base_order:
            base_order.append("ollama")
        
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
                elif preferred in settings.ai_sambanova_models_list:
                    target_provider = "sambanova"
                elif preferred in settings.ai_deepseek_models_list:
                    target_provider = "deepseek"
                elif preferred in settings.ai_cerebras_models_list:
                    target_provider = "cerebras"
                elif preferred in settings.ai_ollama_models_list:
                    target_provider = "ollama"
        
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
        cache_prefix: Optional[str] = None,
        bypass_throttle: bool = False,
    ) -> LLMResult:
        """
        Tenta cada provider em sequência. Retorna no primeiro sucesso.
        Se `preferred_model` for passado, ele lidera a chain (com fallback nos demais).
        Se `strict_model=True`, força o modelo selecionado com retry agressivo (sem fallback).
        Usa cache de respostas se cacheable e temperature <= 0.2.
        `cache_prefix` particiona o cache por contexto (ex: org_id) — evita vazamento entre clientes.
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
                cache_prefix or "",
                json_mode,
                round(temp, 2),
                tier.value,
                preferred_model or "",
                [(m.role, m.content) for m in messages],
            )
            cached = self._cache.get(key)
            if isinstance(cached, LLMResult):
                log.debug("llm.cache.hit", tier=tier.value, prefix=cache_prefix or "global")
                return cached

        # Se strict_model=True, força o provider do modelo selecionado como prioridade absoluta,
        # mas adiciona um fallback interno de segurança (gemini) para evitar 503/429 fatais.
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
            elif preferred_model in settings.ai_sambanova_models_list:
                target_provider = "sambanova"
            elif preferred_model in settings.ai_deepseek_models_list:
                target_provider = "deepseek"
            elif preferred_model in settings.ai_cerebras_models_list:
                target_provider = "cerebras"
            elif preferred_model in settings.ai_ollama_models_list:
                target_provider = "ollama"
            
            # Heurística caso não ache na lista exata do config
            if not target_provider:
                pm_lower = preferred_model.lower()
                if "gemini" in pm_lower: target_provider = "gemini"
                elif "claude" in pm_lower: target_provider = "claude"
                elif "qwen-3-235b" in pm_lower: target_provider = "cerebras"
                elif "llama-3.3" in pm_lower: target_provider = "groq"
                elif "deepseek" in pm_lower: target_provider = "deepseek"
                elif "qwen2.5" in pm_lower: target_provider = "ollama"
            
            if target_provider and target_provider in self._providers:
                target_p = self._providers[target_provider]
                providers = [target_p]
                log.info("llm.strict_mode.enforced", primary=target_provider, model=preferred_model)
            else:
                providers = self.chain(preferred=preferred_model)
        else:
            providers = self.chain(preferred=preferred_model)
            
        # Reordena provedores adaptativamente baseado no tamanho do contexto se não for strict_model
        if not strict_model:
            est_tokens = _estimate_tokens(messages)
            base_prov_names = [p.name for p in providers]
            if est_tokens < 15_000:
                # Menos tokens -> Prioriza provedores leves/rápidos: gemini, groq, cerebras
                lightweight = ["gemini", "groq", "cerebras"]
                sorted_prov_names = [p for p in lightweight if p in base_prov_names] + [p for p in base_prov_names if p not in lightweight]
                providers = [self._providers[name] for name in sorted_prov_names if name in self._providers]
            elif est_tokens > 100_000:
                # Mais de 100k tokens -> Prioriza provedores com contextos massivos: gemini, claude, sambanova
                heavyweight = ["gemini", "claude", "sambanova"]
                sorted_prov_names = [p for p in heavyweight if p in base_prov_names] + [p for p in base_prov_names if p not in heavyweight]
                providers = [self._providers[name] for name in sorted_prov_names if name in self._providers]
            
        if not providers:
            raise NoProviderAvailableError("No LLM providers registered.")

        any_available = False
        last_error: Optional[str] = None
        daily_quota_exhausted_error: Optional[GeminiDailyQuotaExhaustedError] = None

        # Throttle global: serializa chamadas LLM e garante gap mínimo entre elas.
        global _last_llm_call_time
        
        # Função interna para executar a tentativa nos provedores
        async def _run_providers():
            nonlocal any_available, last_error, daily_quota_exhausted_error
            for provider in providers:
                if not provider.available:
                    log.debug("llm.provider.unavailable", provider=provider.name)
                    continue

                # Skip rápido se o provider foi rate-limitado recentemente
                cooldown_until = _provider_rate_limited_until.get(provider.name, 0)
                if time.monotonic() < cooldown_until:
                    # Se for o provider preferido ou se estivermos em strict_model, NÃO pula!
                    is_preferred = False
                    if preferred_model:
                        if preferred_model == provider.name:
                            is_preferred = True
                        elif hasattr(provider, "models") and preferred_model in provider.models:
                            is_preferred = True
                        elif provider.name == "gemini" and "gemini" in preferred_model:
                            is_preferred = True
                        elif provider.name == "groq" and preferred_model in (settings.ai_groq_models_list or []):
                            is_preferred = True
                        elif provider.name == "claude" and preferred_model in (settings.ai_claude_models_list or []):
                            is_preferred = True

                    if not strict_model and not is_preferred:
                        remaining = round(cooldown_until - time.monotonic())
                        log.debug("llm.provider.skipped_cooldown", provider=provider.name, remaining_sec=remaining)
                        continue

                any_available = True

                # Retry loop para o provedor atual
                max_provider_retries = 15 if strict_model else 3
                for attempt in range(1, max_provider_retries + 1):
                    try:
                        result = await provider.complete(
                            messages,
                            json_mode=json_mode,
                            temperature=temp,
                            tier=tier,
                            preferred_model=preferred_model,
                        )
                        _provider_rate_limited_until.pop(provider.name, None)
                        if cache_enabled and key:
                            self._cache.set(key, result)
                        return result

                    except GeminiDailyQuotaExhaustedError as e:
                        daily_quota_exhausted_error = e
                        last_error = f"gemini_daily_quota_exhausted"
                        log.warning("llm.gemini.daily_quota_exhausted_router", strict_mode=strict_model)
                        if strict_model:
                            raise e
                        break

                    except LLMError as e:
                        last_error = f"{provider.name}: {e}"
                        is_rate_limit = "rate_limit" in str(e).lower() or "429" in str(e).lower()

                        if not strict_model:
                            next_provider_idx = providers.index(provider) + 1
                            if next_provider_idx < len(providers):
                                next_p = providers[next_provider_idx]
                                log.warning("llm.fallback", reason=f"Falha no {provider.name} ({str(e)[:100]})", next_attempt=next_p.name)

                        if is_rate_limit:
                            import re as _re
                            m = _re.search(r"retry_after[=:]\s*(\d+)", str(e).lower())
                            if strict_model:
                                base_wait = int(m.group(1)) if m else 5
                                cooldown = min(base_wait * (2 ** (attempt - 1)), 120)
                                log.warning("llm.strict.retry", provider=provider.name, attempt=attempt, wait_sec=cooldown)
                                if attempt < max_provider_retries:
                                    await asyncio.sleep(cooldown)
                                    continue
                            else:
                                cooldown = int(m.group(1)) if m else (30 * attempt)
                                _provider_rate_limited_until[provider.name] = time.monotonic() + cooldown
                                log.warning("llm.provider.rate_limit_aborting_for_fallback", provider=provider.name, wait_sec=cooldown)
                                break  # SAI DO LOOP DE RETRY IMEDIATAMENTE PARA ACIONAR O FALLBACK!

                        log.warning("llm.provider.failed", provider=provider.name, error=str(e)[:200])
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
            return None

        if bypass_throttle:
            # Executa sem o _llm_semaphore e sem sleep
            result = await _run_providers()
            if result:
                return result
        else:
            async with _llm_semaphore:
                now = time.monotonic()
                gap = _MIN_CALL_GAP_SEC - (now - _last_llm_call_time)
                if gap > 0:
                    log.debug("llm.throttle.wait", gap_ms=round(gap * 1000))
                    await asyncio.sleep(gap)
                _last_llm_call_time = time.monotonic()
                result = await _run_providers()
                if result:
                    return result

        if not any_available:
            raise NoProviderAvailableError(
                "No LLM provider is available (missing keys or circuit open)."
            )

    async def stream_complete(
        self,
        messages: List[LLMMessage],
        *,
        temperature: float = 0.1,
        timeout_sec: Optional[float] = None,
        tier: LLMTier = LLMTier.STANDARD,
        preferred_model: Optional[str] = None,
        bypass_throttle: bool = False,
        strict_model: bool = False,
        target_provider: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        async def _run_providers() -> AsyncGenerator[str, None]:
            providers = self.chain(preferred_model)
            if target_provider and target_provider in self._providers:
                providers = [self._providers[target_provider]]
            providers = [p for p in providers if p.name not in _provider_rate_limited_until or time.monotonic() > _provider_rate_limited_until[p.name]]
            if not providers:
                raise NoProviderAvailableError("Nenhum provider disponível para stream.")

            last_error = ""
            for provider in providers:
                if not provider.available:
                    continue
                try:
                    async for chunk in provider.stream(
                        messages=messages,
                        temperature=temperature,
                        timeout_sec=timeout_sec,
                        tier=tier,
                        preferred_model=preferred_model,
                    ):
                        yield chunk
                    return
                except Exception as e:
                    last_error = str(e)
                    if "429" in str(e).lower() or "rate limit" in str(e).lower():
                        break
                    break
            raise LLMError(f"Stream falhou em todos os providers. Último erro: {last_error}")

        if bypass_throttle:
            async for chunk in _run_providers():
                yield chunk
        else:
            global _last_llm_call_time
            async with _llm_semaphore:
                now = time.monotonic()
                gap = _MIN_CALL_GAP_SEC - (now - _last_llm_call_time)
                if gap > 0:
                    await asyncio.sleep(gap)
                _last_llm_call_time = time.monotonic()
                
                async for chunk in _run_providers():
                    yield chunk


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
    cache_prefix: Optional[str] = None,
    bypass_throttle: bool = False,
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
        cache_prefix=cache_prefix,
        bypass_throttle=bypass_throttle,
    )


# ---------------------------------------------------------------------------
# Healthcheck Proativo em Background (Heartbeat de Latência/Fidelidade)
# ---------------------------------------------------------------------------

async def run_llm_preemptive_healthcheck() -> None:
    """
    Roda um healthcheck proativo periódico (a cada 5 minutos) que faz ping em todos os providers ativos.
    Se falhar, coloca o provider em cooldown imediato, evitando latências de retries no chat.
    """
    from core.llm.base import LLMMessage
    
    # Mensagem de teste super barata e curta (1 token)
    ping_messages = [LLMMessage(role="user", content="1")]
    
    # Aguarda o servidor sinalizar readiness antes de disparar chamadas a LLMs externos.
    # Background tasks nunca devem competir com o tráfego de startup.
    await asyncio.sleep(45.0)
    
    while True:
        try:
            router = get_router()
            providers = list(router._providers.values())
            
            for provider in providers:
                if not provider.available:
                    continue
                
                # Se for ollama e não houver modelos locais baixados, pula para não travar
                if provider.name == "ollama":
                    from core.config import settings
                    if not settings.ai_ollama_models_list:
                        continue
                
                start_time = time.monotonic()
                try:
                    # Usamos um timeout de 15 segundos para o ping de saúde (Gemini free tier pode demorar)
                    timeout_val = 15.0 if provider.name == "gemini" else 8.0
                    await asyncio.wait_for(
                        provider.complete(
                            ping_messages,
                            temperature=0.0,
                            timeout_sec=timeout_val,
                        ),
                        timeout=timeout_val + 2.0
                    )
                    # Sucesso — se estava em cooldown, remove!
                    if provider.name in _provider_rate_limited_until:
                        _provider_rate_limited_until.pop(provider.name, None)
                        log.info("llm.healthcheck.recovered", provider=provider.name, latency_sec=round(time.monotonic() - start_time, 2))
                    else:
                        log.debug("llm.healthcheck.healthy", provider=provider.name, latency_sec=round(time.monotonic() - start_time, 2))
                except Exception as e:
                    if provider.name != "ollama":
                        _provider_rate_limited_until[provider.name] = time.monotonic() + 60.0
                        log.warning("llm.healthcheck.failed", provider=provider.name, error=str(e)[:150], action="cooldown_applied_60s")
                    else:
                        log.warning("llm.healthcheck.ollama_failed", error=str(e)[:150])

                # Pausa entre providers — evita flood de conexões no event loop.
                await asyncio.sleep(2.0)

        except Exception as e:
            log.exception("llm.healthcheck.loop_error", error=str(e))
            
        await asyncio.sleep(300.0)
