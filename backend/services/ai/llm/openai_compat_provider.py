"""
Provider genérico OpenAI-compatible.
Usado por SambaNova, DeepSeek, Cerebras — todos seguem o mesmo protocolo de chat completions.
"""
from __future__ import annotations

import json
import time
from typing import List, Optional

from core.http_client import get_http_client
from core.logging_config import get_logger
from core.metrics import llm_requests_total, llm_request_duration_seconds, update_circuit_metric
from core.resilience import CircuitOpenError, get_breaker
from services.ai.llm.base import LLMError, LLMMessage, LLMProvider, LLMResult, LLMTier

log = get_logger(__name__)


def _messages_to_openai(messages: List[LLMMessage]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if not m.content:
            continue
        role = "assistant" if m.role == "assistant" else ("system" if m.role == "system" else "user")
        out.append({"role": role, "content": m.content})
    return out


class OpenAICompatProvider(LLMProvider):
    """Provider para qualquer API OpenAI-compatible (SambaNova, DeepSeek, Cerebras...)."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key_fn,        # callable() → str — lê do settings em runtime
        models_fn,         # callable() → list[str]
        timeout_sec: float = 45.0,
        extra_payload: Optional[dict] = None,  # campos extras adicionados ao payload
    ) -> None:
        self.name = name
        self._base_url = base_url
        self._api_key_fn = api_key_fn
        self._models_fn = models_fn
        self._timeout_sec = timeout_sec
        self._extra_payload = extra_payload or {}
        self._breaker = get_breaker(f"llm.{name}")

    @property
    def available(self) -> bool:
        return bool(self._api_key_fn()) and not self._breaker.is_open

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
        key = self._api_key_fn()
        if not key:
            raise LLMError(f"{self.name} API key not configured.")

        try:
            self._breaker.ensure_available()
        except CircuitOpenError as e:
            llm_requests_total.labels(provider=self.name, model="-", outcome="circuit_open").inc()
            update_circuit_metric(self._breaker.name, True)
            raise LLMError(str(e)) from e

        base_messages = _messages_to_openai(messages)
        if json_mode and not any(m["role"] == "system" for m in base_messages):
            base_messages.insert(0, {
                "role": "system",
                "content": "Você é uma IA analítica. Responda obrigatoriamente em JSON válido.",
            })

        all_models = self._models_fn() or []
        
        # Seleção de modelos inteligente com ordenação adaptativa de tamanho
        from services.ai.llm.router import _estimate_tokens, get_model_size, get_model_context_limit
        est_tokens = _estimate_tokens(messages)

        valid_models = []
        for m in all_models:
            ctx_limit = get_model_context_limit(m)
            if est_tokens > ctx_limit:
                log.warning(f"llm.{self.name}.context_limit_skipped", model=m, estimated=est_tokens, limit=ctx_limit)
                continue
            valid_models.append(m)

        if not valid_models:
            valid_models = all_models

        def _compat_size_sort_key(m: str) -> int:
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
            other_models.sort(key=_compat_size_sort_key)
            models = [preferred_model] + other_models
        else:
            valid_models.sort(key=_compat_size_sort_key)
            models = valid_models

        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        timeout = timeout_sec or self._timeout_sec
        client = get_http_client()
        last_error: Optional[str] = None

        for model in models:
            payload: dict = {
                "model": model,
                "messages": base_messages,
                "temperature": temperature,
                **self._extra_payload,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            # --- OTIMIZAÇÃO AVANÇADA PARA CEREBRAS FREE TIER ---
            if self.name == "cerebras":
                # 1. Imposição de limite de tokens preventiva (Evita erro 429 defensivo por alocação MSL)
                if "max_completion_tokens" not in payload and "max_tokens" not in payload:
                    payload["max_completion_tokens"] = 2048  # Default seguro e eficiente para evitar exaustão de TPM

                # 2. Configurações de raciocínio (reasoning_effort / clear_thinking) por modelo
                if "gpt-oss-120b" in model:
                    payload["reasoning_effort"] = "high" if tier == LLMTier.DEEP else "medium"
                elif "zai-glm-4.7" in model:
                    payload["clear_thinking"] = True

                # 3. Roteamento inteligente de Service Tier
                if "service_tier" not in payload:
                    payload["service_tier"] = "auto"

                # 4. Controle de Fila Preemptivo (Fail-fast em 15s para evitar hanging requests)
                headers["queue_threshold"] = "15000"
                headers["Cerebras-Queue-Threshold"] = "15000"

            start = time.perf_counter()
            try:
                resp = await client.post(self._base_url, json=payload, headers=headers, timeout=timeout)
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                log.warning(f"llm.{self.name}.network_error", model=model, error=last_error)
                llm_requests_total.labels(provider=self.name, model=model, outcome="error").inc()
                continue

            latency = time.perf_counter() - start
            llm_request_duration_seconds.labels(provider=self.name, model=model).observe(latency)

            if resp.status_code == 200:
                try:
                    from services.ai.llm.quota_manager import get_quota_manager
                    await get_quota_manager().update_quota_from_headers(self.name, model, resp.headers)
                except Exception as ex:
                    log.warning(f"llm.{self.name}.quota_error", error=str(ex))

                data = resp.json()
                try:
                    text_content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError):
                    last_error = f"empty_response: {json.dumps(data)[:200]}"
                    llm_requests_total.labels(provider=self.name, model=model, outcome="error").inc()
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
                llm_requests_total.labels(provider=self.name, model=model, outcome="success").inc()
                log.info(f"llm.{self.name}.success", model=model,
                         latency_ms=round(latency * 1000, 1), json_mode=json_mode)
                return LLMResult(text=text_content, json_data=json_data, provider=self.name,
                                 model=model, latency_sec=latency)

            if resp.status_code == 429:
                last_error = f"rate_limited_on_{model}"
                llm_requests_total.labels(provider=self.name, model=model, outcome="rate_limited").inc()
                log.warning(f"llm.{self.name}.rate_limit", model=model)
                continue

            if resp.status_code in (401, 402) or (resp.status_code in (400, 403) and any(x in resp.text.lower() for x in ["credit", "balance", "billing", "insufficient"])):
                last_error = f"no_credits_on_{model}"
                try:
                    from services.ai.llm.quota_manager import get_quota_manager
                    await get_quota_manager().record_billing_error(self.name, model)
                except Exception as ex:
                    log.warning(f"llm.{self.name}.quota_error", error=str(ex))
                llm_requests_total.labels(provider=self.name, model=model, outcome="error").inc()
                log.warning(f"llm.{self.name}.no_credits", model=model, error=resp.text[:200])
                continue

            last_error = f"{resp.status_code}_on_{model}: {resp.text[:200]}"
            llm_requests_total.labels(provider=self.name, model=model, outcome="error").inc()
            log.warning(f"llm.{self.name}.error", model=model,
                        status=resp.status_code, body=resp.text[:200])

        self._breaker.record_failure(reason=last_error or "all_models_failed")
        update_circuit_metric(self._breaker.name, True)
        raise LLMError(f"{self.name}: all models failed ({last_error})")
