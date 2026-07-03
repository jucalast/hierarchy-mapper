"""
core.metrics
============
Camada fina de métricas compatível com Prometheus.

Usa prometheus_client quando disponível; se não, expõe no-ops (safe).
Expor `/metrics` em main.py apenas quando obs.metrics_enabled = True.
"""
from __future__ import annotations

from typing import Any, Optional

from core.config import settings

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    _PROM_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROM_AVAILABLE = False

    class _Noop:
        def __init__(self, *a, **kw): ...
        def labels(self, *a, **kw): return self
        def inc(self, *a, **kw): ...
        def dec(self, *a, **kw): ...
        def set(self, *a, **kw): ...
        def observe(self, *a, **kw): ...
        def time(self):
            import contextlib
            return contextlib.nullcontext()

    Counter = Gauge = Histogram = _Noop  # type: ignore[assignment,misc]
    CONTENT_TYPE_LATEST = "text/plain"

    def generate_latest(*_a, **_kw) -> bytes:  # type: ignore[no-redef]
        return b""


# =============================================================================
# Definições globais
# =============================================================================

METRICS_ENABLED = bool(_PROM_AVAILABLE and getattr(settings.observability, "metrics_enabled", True))

# HTTP
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# LLM
llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM calls",
    ["provider", "model", "outcome"],  # outcome: success|error|circuit_open|timeout
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM call duration in seconds",
    ["provider", "model"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 45.0, 90.0),
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens processed by LLMs",
    ["provider", "direction"],  # direction: input|output
)

# Circuit breaker
circuit_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open)",
    ["name"],
)

# External integrations
external_api_requests_total = Counter(
    "external_api_requests_total",
    "Calls to external APIs (Pipedrive, LinkedIn, etc.)",
    ["integration", "endpoint", "status"],
)

external_api_duration_seconds = Histogram(
    "external_api_duration_seconds",
    "External API call duration",
    ["integration"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# Cache
cache_hits_total = Counter(
    "cache_hits_total", "Cache hits", ["cache"],
)
cache_misses_total = Counter(
    "cache_misses_total", "Cache misses", ["cache"],
)


def render_metrics() -> tuple[bytes, str]:
    """Retorna (payload, content_type) para o endpoint /metrics."""
    if not METRICS_ENABLED:
        return b"# metrics disabled\n", "text/plain"
    return generate_latest(), CONTENT_TYPE_LATEST


def update_circuit_metric(name: str, is_open: bool) -> None:
    circuit_state.labels(name=name).set(1 if is_open else 0)
