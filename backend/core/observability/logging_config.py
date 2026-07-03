"""
core.logging_config
===================
Logging estruturado (JSON em prod, colorido em dev) com correlation_id.

API pública:
    - configure_logging()             # chamar uma vez no startup
    - get_logger(name)                # use em cada módulo
    - set_request_id(request_id)      # seta correlation id no contexto
    - clear_request_id()              # limpa no fim do request
    - RequestIDMiddleware             # middleware ASGI que injeta request_id

Exemplo:
    from core.logging_config import get_logger
    log = get_logger(__name__)
    log.info("chat.received", user_msg_len=len(msg), org_id=org_id)
"""
from __future__ import annotations

import logging
import logging.config
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Optional

try:
    import structlog
    _STRUCTLOG_AVAILABLE = True
except ImportError:  # pragma: no cover
    _STRUCTLOG_AVAILABLE = False


# Context var para correlation id por request (seguro em asyncio)
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)


def get_request_id() -> Optional[str]:
    return _request_id_ctx.get()


def clear_request_id() -> None:
    _request_id_ctx.set(None)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


# =============================================================================
# Configuração
# =============================================================================

_CONFIGURED = False


def configure_logging(level: str = "INFO", json_mode: bool = False) -> None:
    """Configura logging global. Idempotente — pode ser chamado várias vezes."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_level = getattr(logging, level.upper(), logging.INFO)

    if _STRUCTLOG_AVAILABLE:
        _configure_structlog(log_level, json_mode)
    else:
        _configure_stdlib(log_level, json_mode)

    _CONFIGURED = True


def _add_request_id(_, __, event_dict):  # structlog processor
    rid = get_request_id()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def _configure_structlog(log_level: int, json_mode: bool) -> None:
    import structlog  # re-import local para evitar shadowing

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _add_request_id,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_mode:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Alinha stdlib logging (uvicorn, sqlalchemy) com mesmo formato básico
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    # Silenciar loggers muito verbosos
    for noisy in (
        "httpx", "httpcore", "urllib3", "asyncio",
        "sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.orm",
        "aiohttp", "multipart", "uvicorn.access", "uvicorn.error",
        "apscheduler",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _configure_stdlib(log_level: int, json_mode: bool) -> None:
    """Fallback sem structlog — usa logging.Formatter manual."""
    import json

    class _RequestIDFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            record.request_id = get_request_id() or "-"
            return True

    class _JSONFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            payload = {
                "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
                "request_id": getattr(record, "request_id", "-"),
            }
            if record.exc_info:
                payload["exc"] = self.formatException(record.exc_info)
            return json.dumps(payload, ensure_ascii=False)

    fmt = (
        _JSONFormatter()
        if json_mode
        else logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"
        )
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)
    handler.addFilter(_RequestIDFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "uvicorn.access", "uvicorn.error", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# =============================================================================
# Adaptador stdlib-compatible: get_logger devolve objeto com .info/.warn/.error
# que aceita kwargs arbitrários (para uso padronizado mesmo sem structlog).
# =============================================================================

class _StdlibStructuredAdapter:
    """Permite `log.info("event", key=value)` mesmo quando usamos stdlib puro."""

    def __init__(self, logger: logging.Logger):
        self._log = logger

    def _format(self, event: str, **kw: Any) -> str:
        if not kw:
            return event
        parts = " ".join(f"{k}={v}" for k, v in kw.items())
        return f"{event} {parts}"

    def debug(self, event: str, **kw: Any) -> None:
        self._log.debug(self._format(event, **kw))

    def info(self, event: str, **kw: Any) -> None:
        self._log.info(self._format(event, **kw))

    def warning(self, event: str, **kw: Any) -> None:
        self._log.warning(self._format(event, **kw))

    warn = warning

    def error(self, event: str, **kw: Any) -> None:
        self._log.error(self._format(event, **kw))

    def exception(self, event: str, **kw: Any) -> None:
        self._log.exception(self._format(event, **kw))

    def critical(self, event: str, **kw: Any) -> None:
        self._log.critical(self._format(event, **kw))


def get_logger(name: str = "app"):
    """Retorna logger estruturado. Use em cada módulo com __name__."""
    if _STRUCTLOG_AVAILABLE:
        import structlog
        return structlog.get_logger(name)
    return _StdlibStructuredAdapter(logging.getLogger(name))


# =============================================================================
# Middleware ASGI — injeta X-Request-ID e cronometra a request
# =============================================================================

class RequestIDMiddleware:
    """
    Middleware ASGI puro que:
      1. Lê X-Request-ID do header; gera um novo se ausente.
      2. Guarda no ContextVar para logs.
      3. Cronometra a requisição.
      4. Ecoa o header na resposta.
    """

    # Paths that are called very frequently and produce log noise — logged at DEBUG only
    _SILENT_PATHS: tuple[str, ...] = (
        "/proxy/",
        "/health",
        "/ready",
        "/metrics",
        "/favicon.ico",
        "/cache-status",
        "/triggers",
        "/pending-summary",
        "/ai/preference",
        "/activities",
        "/organizations",
        "/pipedrive_sync",
        "/hierarchy/",
        "/conversations",
    )

    def __init__(self, app, header_name: str = "X-Request-ID",
                 slow_threshold_sec: float = 2.0):
        self.app = app
        self.header_name = header_name.encode("latin-1")
        self.slow_threshold = slow_threshold_sec
        self._log = get_logger("http.request")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        rid_bytes = headers.get(self.header_name.lower())
        rid = rid_bytes.decode("latin-1") if rid_bytes else new_request_id()

        token = _request_id_ctx.set(rid)
        start = time.perf_counter()
        method = scope.get("method", "-")
        path = scope.get("path", "-")
        status_holder: dict[str, int] = {"code": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                existing = list(message.get("headers") or [])
                # Garante/override do header de correlação
                existing = [h for h in existing if h[0].lower() != self.header_name.lower()]
                existing.append((self.header_name, rid.encode("latin-1")))
                message["headers"] = existing
                status_holder["code"] = int(message.get("status", 0))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start
            status_code = status_holder["code"]

            # Determine log level:
            # 1. Error or Slow -> WARNING
            # 2. Frequent/Silent Path -> DEBUG
            # 3. Normal Path -> INFO
            is_slow = duration >= self.slow_threshold
            is_error = status_code >= 400
            is_silent_path = any(p in path for p in self._SILENT_PATHS)

            if is_error or is_slow:
                log_fn = self._log.warning
            elif is_silent_path:
                log_fn = self._log.debug
            else:
                log_fn = self._log.info

            log_fn(
                "http.finished",
                method=method,
                path=path,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
            )
            _request_id_ctx.reset(token)
