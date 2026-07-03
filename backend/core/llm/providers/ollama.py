"""
Provider dedicado para Ollama local.
Usa a API nativa /api/chat (não OpenAI-compat) para suportar options.num_gpu=0,
garantindo execução na CPU mesmo quando a GPU não suporta CUDA moderno.
"""
from __future__ import annotations

import time
from typing import List, Optional

from core.config import settings
from core.infra.http_client import get_http_client
from core.observability.logging_config import get_logger
from core.observability.metrics import llm_requests_total, llm_request_duration_seconds, update_circuit_metric
from core.resilience import CircuitOpenError, get_breaker
from core.llm.base import LLMError, LLMMessage, LLMProvider, LLMResult, LLMTier

log = get_logger(__name__)

_OLLAMA_BASE = "http://localhost:11434"


def _to_ollama_messages(messages: List[LLMMessage]) -> list[dict]:
    out = []
    for m in messages:
        if not m.content:
            continue
        role = m.role if m.role in ("system", "assistant", "user") else "user"
        out.append({"role": role, "content": m.content})
    return out


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        self._breaker = get_breaker("llm.ollama")

    @property
    def available(self) -> bool:
        return not self._breaker.is_open

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
        try:
            self._breaker.ensure_available()
        except CircuitOpenError as e:
            llm_requests_total.labels(provider=self.name, model="-", outcome="circuit_open").inc()
            update_circuit_metric(self._breaker.name, True)
            raise LLMError(str(e)) from e

        # Seleção de modelos inteligente com ordenação adaptativa de tamanho
        all_models = settings.ai_ollama_models_list or ["qwen2.5:1.5b"]
        
        from core.llm.router import _estimate_tokens, get_model_size, get_model_context_limit
        est_tokens = _estimate_tokens(messages)

        valid_models = []
        for m in all_models:
            ctx_limit = get_model_context_limit(m)
            if est_tokens > ctx_limit:
                log.warning("llm.ollama.context_limit_skipped", model=m, estimated=est_tokens, limit=ctx_limit)
                continue
            valid_models.append(m)

        if not valid_models:
            valid_models = all_models

        def _ollama_size_sort_key(m: str) -> int:
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
            other_models.sort(key=_ollama_size_sort_key)
            models = [preferred_model] + other_models
        else:
            valid_models.sort(key=_ollama_size_sort_key)
            models = valid_models

        ollama_messages = _to_ollama_messages(messages)
        timeout = timeout_sec or 120.0
        client = get_http_client()
        last_error: Optional[str] = None

        for model in models:
            payload: dict = {
                "model": model,
                "messages": ollama_messages,
                "stream": False,
                "options": {
                    "num_gpu": 0,
                    "temperature": temperature,
                },
            }
            if json_mode:
                payload["format"] = "json"

            url = f"{_OLLAMA_BASE}/api/chat"
            start = time.perf_counter()
            try:
                resp = await client.post(url, json=payload, timeout=timeout)
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                log.warning("llm.ollama.network_error", model=model, error=last_error)
                llm_requests_total.labels(provider=self.name, model=model, outcome="error").inc()
                continue

            latency = time.perf_counter() - start
            llm_request_duration_seconds.labels(provider=self.name, model=model).observe(latency)

            if resp.status_code == 200:
                data = resp.json()
                try:
                    text_content = data["message"]["content"]
                except (KeyError, TypeError):
                    last_error = f"empty_response: {str(data)[:200]}"
                    llm_requests_total.labels(provider=self.name, model=model, outcome="error").inc()
                    continue

                self._breaker.record_success()
                update_circuit_metric(self._breaker.name, False)
                llm_requests_total.labels(provider=self.name, model=model, outcome="success").inc()
                log.info("llm.ollama.success", model=model,
                         latency_ms=round(latency * 1000, 1), json_mode=json_mode)
                return LLMResult(
                    text=text_content,
                    json_data=None,
                    provider=self.name,
                    model=model,
                    latency_sec=latency,
                )

            last_error = f"{resp.status_code}_on_{model}: {resp.text[:200]}"
            llm_requests_total.labels(provider=self.name, model=model, outcome="error").inc()
            log.warning("llm.ollama.error", model=model,
                        status=resp.status_code, body=resp.text[:200])

        self._breaker.record_failure(reason=last_error or "all_models_failed")
        update_circuit_metric(self._breaker.name, True)
        raise LLMError(f"ollama: all models failed ({last_error})")
