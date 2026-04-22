"""
Gemini provider (Google Generative Language API).
Fallback interno entre os modelos listados em settings.ai_gemini_models_list.
"""
from __future__ import annotations

import json
import time
from typing import List, Optional

from core.config import settings
from core.http_client import get_http_client
from core.logging_config import get_logger
from core.metrics import (
    llm_requests_total,
    llm_request_duration_seconds,
    update_circuit_metric,
)
from core.resilience import CircuitOpenError, get_breaker
from services.ai.llm.base import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMResult,
    LLMTier,
)

log = get_logger(__name__)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


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
    Obs: Gemini separa `system_instruction` de `contents`.
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

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(settings.GEMINI_API_KEY) and not self._breaker.is_open

    # ------------------------------------------------------------------
    async def complete(
        self,
        messages: List[LLMMessage],
        *,
        json_mode: bool = False,
        temperature: float = 0.1,
        timeout_sec: Optional[float] = None,
        tier: LLMTier = LLMTier.STANDARD,
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
        models = settings.ai_gemini_models_list or ["gemini-flash-latest"]

        last_error: Optional[str] = None
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
                    latency_ms=round(latency * 1000, 1),
                    json_mode=json_mode,
                )
                return LLMResult(
                    text=text_content,
                    json_data=json_data,
                    provider=self.name,
                    model=model,
                    latency_sec=latency,
                )

            if resp.status_code == 429:
                last_error = f"rate_limited_on_{model}"
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="rate_limited"
                ).inc()
                log.warning("llm.gemini.rate_limit", model=model)
                # continua tentando próximo modelo

            elif resp.status_code in (503, 404):
                last_error = f"{resp.status_code}_on_{model}"
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="unavailable"
                ).inc()
                log.warning("llm.gemini.unavailable", model=model, status=resp.status_code)

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

        # todos os modelos falharam — trip circuit breaker
        self._breaker.record_failure(reason=last_error or "all_models_failed")
        update_circuit_metric(self._breaker.name, True)
        raise LLMError(f"Gemini: all models failed ({last_error})")
