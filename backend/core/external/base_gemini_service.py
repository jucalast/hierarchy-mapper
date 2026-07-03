"""
services.external.base_gemini_service
=====================================

Mantido para **retrocompatibilidade**. Toda a lógica real foi movida para
`services.ai.llm` (router unificado com Gemini → Groq → Claude).

A função `ask_gemini(prompt, json_mode, history)` continua existindo com a
MESMA ASSINATURA — apenas agora delega para o LLM Router, que cuida de:
    - escolha do provedor conforme `AI_FALLBACK_CHAIN`;
    - circuit breaker por provedor;
    - cache de respostas idempotentes;
    - métricas Prometheus;
    - logging estruturado.

Os helpers `_is_gemini_available`, `_trip_gemini_circuit`,
`_reset_gemini_circuit` também permanecem (e agora refletem o estado real
do breaker em `core.resilience`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Union

from core.observability.logging_config import get_logger
from core.resilience import get_breaker
from core.llm import LLMTier, ask_llm
from core.llm.base import NoProviderAvailableError

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Compat helpers para código legado
# ---------------------------------------------------------------------------

def _gemini_breaker():
    return get_breaker("llm.gemini")


def _is_gemini_available() -> bool:
    return not _gemini_breaker().is_open


def _trip_gemini_circuit() -> None:
    _gemini_breaker().record_failure(reason="legacy_trip")


def _reset_gemini_circuit() -> None:
    _gemini_breaker().record_success()


# ---------------------------------------------------------------------------
# API pública mantida: ask_gemini
# ---------------------------------------------------------------------------

async def ask_gemini(
    prompt: str,
    json_mode: bool = False,
    max_retries: int = 2,  # mantido por compat; o router já gerencia retries
    history: List[Any] | None = None,
    tier: LLMTier = LLMTier.STANDARD,
) -> Union[str, Dict[str, Any]]:
    """
    Entrada legada. Delega ao LLM Router.

    Retorna:
        - dict se json_mode=True
        - str caso contrário
    """
    try:
        # ask_llm já lê o preferred_model do ContextVar do request atual,
        # então mesmo chamadas legadas via ask_gemini respeitam a preferência do usuário.
        result = await ask_llm(
            prompt=prompt,
            history=history,
            json_mode=json_mode,
            tier=tier,
        )
    except NoProviderAvailableError as e:
        log.warning("ask_gemini.no_provider", error=str(e))
        return {} if json_mode else (
            "Desculpe, ocorreu um erro de cota ou indisponibilidade ao consultar "
            "a Inteligência Artificial."
        )
    except Exception as e:  # defensivo — não deve acontecer
        log.exception("ask_gemini.unexpected", error=str(e))
        return {} if json_mode else (
            "Desculpe, ocorreu um erro inesperado na camada de IA."
        )

    if json_mode:
        return result.json_data if result.json_data is not None else {}
    return result.text


__all__ = [
    "ask_gemini",
    "_is_gemini_available",
    "_trip_gemini_circuit",
    "_reset_gemini_circuit",
]
