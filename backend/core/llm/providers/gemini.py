"""
Gemini provider (Google Generative Language API).

Modelos disponíveis (free tier, abril 2026):
  gemini-2.5-pro        → 100 RPD  | DEEP   (raciocínio pesado, agent workflow)
  gemini-2.5-flash      → 250 RPD  | STANDARD (resposta final, deal status)
  gemini-2.5-flash-lite → 1000 RPD | FAST   (intent, destilação — workhorse)

Seleção por Tier:
  FAST     → flash-lite → flash (overflow)
  STANDARD → flash → flash-lite → pro (overflow)
  DEEP     → pro → flash (overflow)

Quando a cota diária de um modelo se esgota, o sistema transparentemente
usa o próximo modelo do tier. Quando TODOS os modelos Gemini esgotam,
lança GeminiDailyQuotaExhaustedError para o router tratar.
"""
from __future__ import annotations

import json
import time
from typing import List, Optional

from core.config import settings
from core.infra.http_client import get_http_client
from core.observability.logging_config import get_logger
from core.observability.metrics import (
    llm_requests_total,
    llm_request_duration_seconds,
    update_circuit_metric,
)
from core.resilience import CircuitOpenError, get_breaker
from core.llm.base import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMResult,
    LLMTier,
)
from core.llm.gemini_quota import (
    DAILY_LIMITS,
    get_quota_tracker,
)

log = get_logger(__name__)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiDailyQuotaExhaustedError(LLMError):
    """
    Todos os modelos Gemini esgotaram a cota diária.
    Resetará à meia-noite Pacific Time.
    """
    def __init__(self, summary: dict):
        self.summary = summary
        reset_msg = "A cota diária do Gemini foi esgotada. Ela renova automaticamente à meia-noite (horário do Pacífico)."
        super().__init__(reset_msg)


def _timeout_for(tier: LLMTier) -> float:
    if tier == LLMTier.FAST:
        return settings.ai.timeout_fast_sec
    if tier == LLMTier.DEEP:
        return settings.ai.timeout_deep_sec
    return settings.ai.timeout_standard_sec


def _messages_to_gemini(messages: List[LLMMessage]) -> tuple[list, Optional[str]]:
    """
    Converte mensagens neutras para o formato do Gemini.
    Retorna (contents, system_instruction).
    """
    system_parts: list[str] = []
    contents = []
    for m in messages:
        if m.role == "system":
            if m.content:
                system_parts.append(m.content)
            continue
        role = "model" if m.role == "assistant" else "user"
        if m.content:
            contents.append({"role": role, "parts": [{"text": m.content}]})
    system_text = "\n\n".join(system_parts) if system_parts else None
    return contents, system_text


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        self._breaker = get_breaker("llm.gemini")

    @property
    def available(self) -> bool:
        return bool(settings.GEMINI_API_KEY) and not self._breaker.is_open

    async def complete(
        self,
        messages: List[LLMMessage],
        *,
        json_mode: bool = False,
        temperature: float = 0.1,
        timeout_sec: Optional[float] = None,
        tier: LLMTier = LLMTier.STANDARD,
        preferred_model: Optional[str] = None,
    ) -> LLMResult:
        key = settings.GEMINI_API_KEY
        if not key:
            raise LLMError("Gemini API key not configured.")

        try:
            self._breaker.ensure_available()
        except CircuitOpenError as e:
            llm_requests_total.labels(
                provider=self.name, model="-", outcome="circuit_open"
            ).inc()
            update_circuit_metric(self._breaker.name, True)
            raise LLMError(str(e)) from e

        contents, system_text = _messages_to_gemini(messages)
        payload: dict = {
            "contents": contents,
            "generationConfig": {
                "responseMimeType": "application/json" if json_mode else "text/plain",
                "temperature": temperature,
            },
        }
        if system_text:
            payload["system_instruction"] = {"parts": [{"text": system_text}]}

        timeout = timeout_sec or _timeout_for(tier)
        client = get_http_client()
        quota = get_quota_tracker()

        # Seleciona a lista de modelos a tentar para este tier,
        # respeitando a cota diária de cada um.
        models = quota.models_for_tier(tier, preferred_model=preferred_model)

        if not models:
            # Fallback de emergência: qualquer modelo conhecido
            models = list(DAILY_LIMITS.keys())

        # Estima tokens do request atual para ordenação adaptativa de tamanho
        from core.llm.router import _estimate_tokens, get_model_size, get_model_context_limit
        est_tokens = _estimate_tokens(messages)
        
        # Filtra e ordena modelos com base no tamanho do contexto
        valid_models = []
        for model in models:
            ctx_limit = get_model_context_limit(model)
            if est_tokens > ctx_limit:
                log.warning("llm.gemini.context_limit_skipped", model=model, estimated=est_tokens, limit=ctx_limit)
                continue
            valid_models.append(model)
            
        if not valid_models:
            valid_models = models # fallback
            
        # Ordenação inteligente de tamanho:
        # Se est_tokens é pequeno (<15k), prioriza Size 1 (flash-lite) -> Size 2 (flash) -> Size 3 (pro)
        # Se est_tokens é médio (15k-100k), prioriza Size 2 (flash) -> Size 1 (flash-lite) -> Size 3 (pro)
        # Se est_tokens é grande (>100k), prioriza Size 3 (pro) -> Size 2 (flash) -> Size 1 (flash-lite)
        def _gemini_size_sort_key(m: str) -> int:
            sz = get_model_size(m)
            if est_tokens < 15_000:
                return sz
            elif est_tokens < 100_000:
                if sz == 2: return 0
                if sz == 1: return 1
                return 2
            else:
                return -sz
                
        if preferred_model and preferred_model in valid_models:
            other_models = [m for m in valid_models if m != preferred_model]
            other_models.sort(key=_gemini_size_sort_key)
            models = [preferred_model] + other_models
        else:
            valid_models.sort(key=_gemini_size_sort_key)
            models = valid_models

        last_error: Optional[str] = None
        rate_limited_models: list[str] = []   # 429 de RPM (temporário)
        quota_exhausted_models: list[str] = []  # 429 de RPD (diário)

        for model in models:
            url = f"{_GEMINI_BASE}/{model}:generateContent?key={key}"
            start = time.perf_counter()
            try:
                resp = await client.post(url, json=payload, timeout=timeout)
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                log.warning("llm.gemini.network_error", model=model, error=last_error)
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="error"
                ).inc()
                continue

            latency = time.perf_counter() - start
            llm_request_duration_seconds.labels(
                provider=self.name, model=model
            ).observe(latency)

            if resp.status_code == 200:
                data = resp.json()
                try:
                    text_content = data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    llm_requests_total.labels(
                        provider=self.name, model=model, outcome="error"
                    ).inc()
                    last_error = f"empty_response: {json.dumps(data)[:200]}"
                    continue

                # Contabiliza uso na cota diária
                await quota.record(model)

                json_data = None
                if json_mode:
                    try:
                        json_data = json.loads(text_content)
                    except json.JSONDecodeError:
                        json_data = {"response": text_content}

                self._breaker.record_success()
                update_circuit_metric(self._breaker.name, False)
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="success"
                ).inc()
                log.info(
                    "llm.gemini.success",
                    model=model,
                    tier=tier.value,
                    latency_ms=round(latency * 1000, 1),
                    json_mode=json_mode,
                    quota_remaining=quota.get_remaining(model),
                )
                return LLMResult(
                    text=text_content,
                    json_data=json_data,
                    provider=self.name,
                    model=model,
                    latency_sec=latency,
                )

            if resp.status_code == 429:
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="rate_limited"
                ).inc()

                # Tenta distinguir RPM (temporário) de RPD (diário esgotado)
                body_text = resp.text[:500].lower()
                is_daily_exhausted = (
                    "daily" in body_text
                    or "daily limit" in body_text
                    or quota.is_exhausted(model)
                )

                if is_daily_exhausted:
                    # Registra na cota para refletir o esgotamento
                    await quota.record(model)
                    quota_exhausted_models.append(model)
                    log.warning("llm.gemini.daily_quota_exhausted",
                                model=model,
                                used=quota.get_usage(model),
                                limit=quota.get_limit(model))
                else:
                    # Rate limit de RPM — temporário, tenta próximo modelo
                    rate_limited_models.append(model)
                    log.warning("llm.gemini.rpm_limit", model=model,
                                retrying_next=True)

                last_error = f"429_on_{model}"
                # Tenta próximo modelo da lista
                continue

            elif resp.status_code in (404, 403):
                last_error = f"{resp.status_code}_on_{model}"
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="unavailable"
                ).inc()
                log.warning("llm.gemini.model_not_found_or_forbidden", model=model, status=resp.status_code)
                # Pula este modelo permanentemente neste request e tenta o próximo
                continue

            elif resp.status_code == 503:
                last_error = f"503_on_{model}"
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="unavailable"
                ).inc()
                log.warning("llm.gemini.service_unavailable", model=model)
                continue

            else:
                last_error = f"{resp.status_code}_on_{model}: {resp.text[:200]}"
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="error"
                ).inc()
                log.warning(
                    "llm.gemini.error",
                    model=model,
                    status=resp.status_code,
                    body=resp.text[:200],
                )

        # ----------------------------------------------------------------
        # Todos os modelos falharam. Determina a causa:
        # ----------------------------------------------------------------
        summary = quota.summary()

        # Se todos os modelos conhecidos esgotaram cota diária → erro especial
        if quota.all_exhausted():
            log.error("llm.gemini.all_daily_quotas_exhausted", summary=summary)
            raise GeminiDailyQuotaExhaustedError(summary)

        # Se a maioria das falhas foi por cota diária (mas não todas)
        if quota_exhausted_models and len(quota_exhausted_models) >= len(models) - len(rate_limited_models):
            log.error("llm.gemini.quota_exhausted_for_tier",
                      tier=tier.value, exhausted=quota_exhausted_models, summary=summary)
            raise GeminiDailyQuotaExhaustedError(summary)

        # Falhas por outros motivos → trip circuit breaker normalmente
        self._breaker.record_failure(reason=last_error or "all_models_failed")
        update_circuit_metric(self._breaker.name, True)
        raise LLMError(f"Gemini: all models failed ({last_error})")
