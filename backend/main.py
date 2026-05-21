"""
main.py — FastAPI entrypoint

Melhorias vs. versão antiga:
- `lifespan` moderno (substitui @on_event) com startup/shutdown graceful.
- Inicialização do HTTP client compartilhado; fecho limpo no shutdown.
- Cancelamento controlado do background sync task no shutdown.
- CORS dirigido por settings (não mais hardcoded "*").
- Exception handlers globais (HTTP, Validation, generic) com correlation_id.
- Middleware de logging/correlation (RequestIDMiddleware).
- Endpoints /health, /ready, /metrics.
- RateLimiter e routers preservados.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.v1.router import api_router
from core.config import settings
from core.infra.http_client import close_http_client, init_http_client
from core.observability.logging_config import (
    RequestIDMiddleware,
    configure_logging,
    get_logger,
    get_request_id,
)
from core.observability.metrics import render_metrics
from core.rate_limiter import limiter

log = get_logger(__name__)

# Tasks de background criadas em startup — mantidas para cancelamento em shutdown.
_background_tasks: set[asyncio.Task] = set()


# =============================================================================
# Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida: startup → yield → shutdown."""
    configure_logging()

    # Avisa se o JWT secret padrão está sendo usado em produção
    try:
        from core.security import SECRET_KEY
        _DEFAULT_JWT = "linkb2b-super-secret-jwt-key-for-saas-2026"
        if settings.is_production and SECRET_KEY == _DEFAULT_JWT:
            log.error(
                "security.jwt_secret.default_in_production",
                message="JWT_SECRET está com valor padrão em produção! Defina JWT_SECRET no ambiente.",
            )
    except Exception:
        pass

    log.info(
        "server.startup",
        env=settings.environment,
        debug=settings.debug,
        has_gemini=settings.has_gemini,
        has_groq=settings.has_groq,
        has_claude=settings.has_claude,
        has_sambanova=settings.has_sambanova,
        has_cerebras=settings.has_cerebras,
        has_deepseek=settings.has_deepseek,
    )

    # HTTP client compartilhado
    await init_http_client()
    log.info("http_client.initialized")

    # Database
    try:
        from core.infra.database import init_db
        await init_db()
        log.info("database.initialized")
    except Exception as e:
        log.exception("database.init_failed", error=str(e))

    # Scheduler de e-mail (IMAP)
    try:
        from modules.communication.service.email.scheduler import start_email_scheduler
        await start_email_scheduler()
    except Exception as e:
        log.warning("scheduler.start_failed", error=str(e))

    # Sync hub em background
    try:
        from modules.intelligence.service.sync_hub import SyncIntelligenceHub
        task = asyncio.create_task(
            SyncIntelligenceHub().sync_all(), name="sync_intelligence_hub"
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        log.info("sync_hub.started")
    except Exception as e:
        log.warning("sync_hub.start_failed", error=str(e))

    # Trigger Service — monitora respostas de clientes (email + WhatsApp)
    try:
        from modules.triggers.service.trigger_service import TriggerService
        _trigger_svc = TriggerService()
        trigger_task = asyncio.create_task(
            _trigger_svc.start_polling(), name="trigger_service"
        )
        _background_tasks.add(trigger_task)
        trigger_task.add_done_callback(_background_tasks.discard)
        log.info("trigger_service.started")
    except Exception as e:
        log.warning("trigger_service.start_failed", error=str(e))

    # LLM Proactive Preemptive Healthcheck task
    try:
        from core.llm.router import run_llm_preemptive_healthcheck
        healthcheck_task = asyncio.create_task(
            run_llm_preemptive_healthcheck(), name="llm_preemptive_healthcheck"
        )
        _background_tasks.add(healthcheck_task)
        healthcheck_task.add_done_callback(_background_tasks.discard)
        log.info("llm_healthcheck_task.started")
    except Exception as e:
        log.warning("llm_healthcheck_task.start_failed", error=str(e))

    try:
        yield
    finally:
        # -------- Shutdown graceful --------
        log.info("server.shutdown.begin")

        # Cancela background tasks
        for task in list(_background_tasks):
            if not task.done():
                task.cancel()
        if _background_tasks:
            await asyncio.gather(*_background_tasks, return_exceptions=True)
            log.info("background_tasks.cancelled", count=len(_background_tasks))

        # Para scheduler
        try:
            from modules.communication.service.email.scheduler import stop_email_scheduler
            await stop_email_scheduler()
        except Exception as e:
            log.warning("scheduler.stop_failed", error=str(e))

        # Fecha HTTP client compartilhado
        try:
            await close_http_client()
            log.info("http_client.closed")
        except Exception as e:
            log.warning("http_client.close_failed", error=str(e))

        # Dispose do engine
        try:
            from core.infra.database import engine
            await engine.dispose()
            log.info("database.disposed")
        except Exception as e:
            log.warning("database.dispose_failed", error=str(e))

        log.info("server.shutdown.done")


# =============================================================================
# App
# =============================================================================

app = FastAPI(
    title="Hierarchy API",
    description=(
        "API for fetching company employee hierarchy and building supply chain networks."
    ),
    version="1.1.0",
    lifespan=lifespan,
)

# --- Middleware: correlation_id ---
app.add_middleware(RequestIDMiddleware)

# --- CORS (dirigido por settings) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors.allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[settings.observability.request_id_header],
)

# --- Rate limiter ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# =============================================================================
# Exception handlers globais
# =============================================================================

def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: Any = None,
) -> JSONResponse:
    body: Dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": get_request_id(),
        }
    }
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    log.warning(
        "http.exception",
        status=exc.status_code,
        detail=str(exc.detail)[:300],
        path=request.url.path,
    )
    return _error_response(exc.status_code, f"http_{exc.status_code}", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    log.warning(
        "http.validation_error",
        path=request.url.path,
        errors=str(exc.errors())[:400],
    )
    return _error_response(
        422,
        "validation_error",
        "Validation failed for request payload.",
        details=exc.errors(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception(
        "http.unhandled_exception",
        error=f"{type(exc).__name__}: {exc}",
        path=request.url.path,
    )
    return _error_response(500, "internal_server_error", "An unexpected error occurred.")


# =============================================================================
# Routers
# =============================================================================

app.include_router(api_router, prefix="/api/v1")


# =============================================================================
# Root / Health / Ready / Metrics
# =============================================================================

@app.get("/")
@limiter.limit("10/minute")
def read_root(request: Request):
    return {
        "message": "Welcome to the Hierarchy API",
        "version": app.version,
        "request_id": get_request_id(),
    }


@app.get("/health", include_in_schema=False)
async def health():
    """Liveness check — responde 200 se o processo está vivo."""
    return {"status": "ok", "service": "hierarchy-api"}


@app.get("/ready", include_in_schema=False)
async def ready():
    """Readiness check — valida dependências críticas (DB + LLM)."""
    checks: Dict[str, Any] = {}
    overall_ok = True

    # DB
    try:
        from core.infra.database import async_session
        from sqlalchemy import text

        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as e:
        overall_ok = False
        checks["database"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # LLM — any provider
    checks["llm"] = {
        "ok": settings.any_llm_available,
        "providers": {
            "gemini": settings.has_gemini,
            "groq": settings.has_groq,
            "claude": settings.has_claude,
        },
    }
    if not settings.any_llm_available:
        overall_ok = False

    status_code = 200 if overall_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if overall_ok else "degraded", "checks": checks},
    )


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Endpoint Prometheus."""
    if not settings.observability.metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics_disabled")
    payload, content_type = render_metrics()
    return Response(content=payload, media_type=content_type)
