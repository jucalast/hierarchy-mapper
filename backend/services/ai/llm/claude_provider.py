"""
Claude provider (Anthropic Messages API).

Dormant enquanto ANTHROPIC_API_KEY não estiver configurada: `available` retorna
False e o router o ignora no fallback chain.

Quando a chave for adicionada no .env, este provider entra automaticamente
no router se você incluir "claude" em AI_FALLBACK_CHAIN (ex: "claude,gemini,groq").

Implementação usa httpx direto (sem exigir o SDK anthropic), mas o SDK
também pode ser usado trivialmente — basta trocar `_call_http` por
`anthropic.AsyncAnthropic(...).messages.create(...)`.
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

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"


def _timeout_for(tier: LLMTier) -> float:
    if tier == LLMTier.FAST:
        return settings.ai.timeout_fast_sec
    if tier == LLMTier.DEEP:
        return settings.ai.timeout_deep_sec
    return settings.ai.timeout_standard_sec


def _split_system(messages: List[LLMMessage]) -> tuple[str, list[dict]]:
    """Extrai mensagens 'system' (Claude trata separado) e retorna restante."""
    system_parts: list[str] = []
    convo: list[dict] = []
    for m in messages:
        if m.role == "system":
            if m.content:
                system_parts.append(m.content)
            continue
        if not m.content:
            continue
        role = "assistant" if m.role == "assistant" else "user"
        convo.append({"role": role, "content": m.content})
    # Claude exige início com "user"
    if convo and convo[0]["role"] != "user":
        convo.insert(0, {"role": "user", "content": "Ok."})
    return ("\n\n".join(system_parts), convo)


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self) -> None:
        self._breaker = get_breaker("llm.claude")

    @property
    def available(self) -> bool:
        return bool(settings.ANTHROPIC_API_KEY) and not self._breaker.is_open

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
        key = settings.ANTHROPIC_API_KEY
        if not key:
            raise LLMError("Anthropic API key not configured.")

        try:
            self._breaker.ensure_available()
        except CircuitOpenError as e:
            llm_requests_total.labels(
                provider=self.name, model="-", outcome="circuit_open"
            ).inc()
            update_circuit_metric(self._breaker.name, True)
            raise LLMError(str(e)) from e

        system_text, convo = _split_system(messages)
        if json_mode:
            json_hint = (
                "Responda OBRIGATORIAMENTE com um único objeto JSON válido, "
                "sem texto fora das chaves, sem markdown, sem backticks."
            )
            system_text = f"{system_text}\n\n{json_hint}".strip()

        timeout = timeout_sec or _timeout_for(tier)
        client = get_http_client()
        
        # Seleção de modelos inteligente com ordenação adaptativa de tamanho
        all_models = settings.ai_claude_models_list or ["claude-sonnet-4-5", "claude-3-5-haiku-latest"]
        
        from services.ai.llm.router import _estimate_tokens, get_model_size, get_model_context_limit
        est_tokens = _estimate_tokens(messages)

        valid_models = []
        for m in all_models:
            ctx_limit = get_model_context_limit(m)
            if est_tokens > ctx_limit:
                log.warning("llm.claude.context_limit_skipped", model=m, estimated=est_tokens, limit=ctx_limit)
                continue
            valid_models.append(m)

        if not valid_models:
            valid_models = all_models

        def _claude_size_sort_key(m: str) -> int:
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
            other_models.sort(key=_claude_size_sort_key)
            models = [preferred_model] + other_models
        else:
            valid_models.sort(key=_claude_size_sort_key)
            models = valid_models
        headers = {
            "x-api-key": key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        last_error: Optional[str] = None
        for model in models:
            payload = {
                "model": model,
                "max_tokens": 4096,
                "temperature": temperature,
                "system": system_text,
                "messages": convo,
            }

            start = time.perf_counter()
            try:
                resp = await client.post(
                    _ANTHROPIC_URL, json=payload, headers=headers, timeout=timeout
                )
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                log.warning("llm.claude.network_error", model=model, error=last_error)
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="error"
                ).inc()
                continue
            latency = time.perf_counter() - start
            llm_request_duration_seconds.labels(
                provider=self.name, model=model
            ).observe(latency)

            if resp.status_code == 200:
                try:
                    from services.ai.llm.quota_manager import get_quota_manager
                    await get_quota_manager().update_quota_from_headers(self.name, model, resp.headers)
                except Exception as ex:
                    log.warning("llm.claude.quota_error", error=str(ex))

                data = resp.json()
                try:
                    blocks = data.get("content", [])
                    text_content = "".join(
                        b.get("text", "") for b in blocks if b.get("type") == "text"
                    )
                except Exception:
                    text_content = ""
                if not text_content:
                    last_error = f"empty_response: {json.dumps(data)[:200]}"
                    llm_requests_total.labels(
                        provider=self.name, model=model, outcome="error"
                    ).inc()
                    continue

                json_data = None
                if json_mode:
                    try:
                        cleaned = text_content.strip()
                        # Remove blocos de código markdown (```json ... ``` ou ``` ...)
                        if "```" in cleaned:
                            import re as _re
                            match = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, _re.DOTALL)
                            if match:
                                cleaned = match.group(1)
                            else:
                                # Fallback: tenta pegar entre a primeira { e a última }
                                match = _re.search(r"(\{.*\})", cleaned, _re.DOTALL)
                                if match:
                                    cleaned = match.group(1)
                        
                        json_data = json.loads(cleaned)
                    except json.JSONDecodeError:
                        # Se falhou mas o texto parece JSON, tenta uma última limpeza
                        try:
                            import re as _re
                            match = _re.search(r"(\{.*\})", text_content, _re.DOTALL)
                            if match:
                                json_data = json.loads(match.group(1))
                            else:
                                json_data = {"response": text_content}
                        except:
                            json_data = {"response": text_content}

                usage = data.get("usage") or {}
                self._breaker.record_success()
                update_circuit_metric(self._breaker.name, False)
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="success"
                ).inc()
                log.info(
                    "llm.claude.success",
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
                    tokens_input=usage.get("input_tokens"),
                    tokens_output=usage.get("output_tokens"),
                )

            if resp.status_code == 429:
                last_error = f"rate_limited_on_{model}"
                llm_requests_total.labels(
                    provider=self.name, model=model, outcome="rate_limited"
                ).inc()
                log.warning("llm.claude.rate_limit", model=model)
                continue

            last_error = f"{resp.status_code}_on_{model}: {resp.text[:200]}"
            llm_requests_total.labels(
                provider=self.name, model=model, outcome="error"
            ).inc()
            log.warning(
                "llm.claude.error",
                model=model,
                status=resp.status_code,
                body=resp.text[:200],
            )

        self._breaker.record_failure(reason=last_error or "all_models_failed")
        update_circuit_metric(self._breaker.name, True)
        raise LLMError(f"Claude: all models failed ({last_error})")
