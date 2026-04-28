"""
Groq provider (OpenAI-compatible API).
Fallback interno entre os modelos listados em settings.ai_groq_models_list.
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

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _timeout_for(tier: LLMTier) -> float:
    if tier == LLMTier.FAST:
        return settings.ai.timeout_fast_sec
    if tier == LLMTier.DEEP:
        return settings.ai.timeout_deep_sec
    return settings.ai.timeout_standard_sec


def _messages_to_openai(messages: List[LLMMessage]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if not m.content:
            continue
        role = "assistant" if m.role == "assistant" else ("system" if m.role == "system" else "user")
        out.append({"role": role, "content": m.content})
    return out


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self) -> None:
        self._breaker = get_breaker("llm.groq")

    @property
    def available(self) -> bool:
        return bool(settings.GROQ_API_KEY) and not self._breaker.is_open

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
        key = settings.GROQ_API_KEY
        if not key:
            raise LLMError("Groq API key not configured.")

        try:
            self._breaker.ensure_available()
        except CircuitOpenError as e:
            llm_requests_total.labels(
                provider=self.name, model="-", outcome="circuit_open"
            ).inc()
            update_circuit_metric(self._breaker.name, True)
            raise LLMError(str(e)) from e

        base_messages = _messages_to_openai(messages)
        if json_mode and not any(m["role"] == "system" for m in base_messages):
            base_messages.insert(
                0,
                {
                    "role": "system",
                    "content": "Você é uma IA analítica. Responda obrigatoriamente em JSON válido.",
                },
            )

        timeout = timeout_sec or _timeout_for(tier)
        client = get_http_client()
        
        # Seleção de modelos inteligente por Tier e Preferência
        all_models = settings.ai_groq_models_list or ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        
        if preferred_model and preferred_model in all_models:
            # Coloca o preferido no topo
            models = [preferred_model] + [m for m in all_models if m != preferred_model]
        elif tier == LLMTier.FAST:
            # Para tarefas rápidas, prioriza modelos 8b
            models = [m for m in all_models if "8b" in m] + [m for m in all_models if "8b" not in m]
        else:
            models = all_models
            
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

        last_error: Optional[str] = None
        for model in models:
            payload: dict = {
                "model": model,
                "messages": base_messages,
                "temperature": temperature,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            start = time.perf_counter()
            try:
                resp = await client.post(
                    _GROQ_URL, json=payload, headers=headers, timeout=timeout
                )
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                log.warning("llm.groq.network_error", model=model, error=last_error)
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
                    text_content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError):
                    last_error = f"empty_response: {json.dumps(data)[:200]}"
                    llm_requests_total.labels(
                        provider=self.name, model=model, outcome="error"
                    ).inc()
                    continue

                json_data = None
                if json_mode:
                    try:
                        cleaned = text_content.strip()
                        if cleaned.startswith("```"):
                            cleaned = cleaned.split("```", 2)[-1].lstrip("json").strip()
                            cleaned = cleaned.rsplit("```", 1)[0].strip()
                        json_data = json.loads(cleaned)
                    except json.JSONDecodeError:
                        json_data = {"response": text_content}

                self._breaker.record_success()
                update_circuit_metric(self._breaker.name, False)
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="success"
                ).inc()
                log.info(
                    "llm.groq.success",
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
                # Respeita o header Retry-After se presente, senão passa pro próximo modelo
                retry_after = resp.headers.get("retry-after") or resp.headers.get("x-ratelimit-reset-requests")
                if retry_after:
                    try:
                        wait = float(retry_after)
                        log.warning("llm.groq.rate_limit", model=model, retry_after_sec=wait)
                    except (ValueError, TypeError):
                        pass
                else:
                    log.warning("llm.groq.rate_limit", model=model)
                # Não tenta o mesmo modelo de novo — passa direto pro próximo (router faz o retry externo)
                continue

            last_error = f"{resp.status_code}_on_{model}: {resp.text[:200]}"
            llm_requests_total.labels(
                provider=self.name, model=model, outcome="error"
            ).inc()
            log.warning(
                "llm.groq.error",
                model=model,
                status=resp.status_code,
                body=resp.text[:200],
            )

        self._breaker.record_failure(reason=last_error or "all_models_failed")
        update_circuit_metric(self._breaker.name, True)
        raise LLMError(f"Groq: all models failed ({last_error})")
