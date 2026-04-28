"""
Scheduler de background (APScheduler) para varreduras IMAP.

Diferenças vs versão antiga:
- A varredura IMAP (bloqueante) é executada em `asyncio.to_thread` para
  NÃO travar o event loop principal do FastAPI/Uvicorn.
- O scheduler é construído "lazy" no startup, permitindo que `main.py`
  faça `await start_email_scheduler()` com o loop já rodando.
- Intervalo e pasta configuráveis por settings (defaults mantidos).
- Logging estruturado com correlation_id separado por ciclo.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import settings
from core.logging_config import get_logger, set_request_id
from services.communication.email_client import EmailClient

log = get_logger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def _check_inbox_blocking(folder: str) -> list[dict]:
    """Executa a varredura IMAP. É BLOQUEANTE — roda em worker thread."""
    client = EmailClient()
    return client.scan_inbound_replies(folder=folder) or []


async def check_inbox_async() -> None:
    """Job assíncrono do APScheduler — offload do IMAP para thread pool."""
    # Respeita o mesmo horário de silêncio do TriggerService
    try:
        from services.ai.trigger_service import is_quiet_hours, _service_paused
        if _service_paused or is_quiet_hours():
            log.debug("scheduler.imap.skipped_quiet_or_paused")
            return
    except Exception:
        pass

    cycle_id = uuid.uuid4().hex[:12]
    set_request_id(f"imap-{cycle_id}")
    folder = settings.email.scan_folder
    log.info("scheduler.imap.start", folder=folder)
    try:
        unreads = await asyncio.to_thread(_check_inbox_blocking, folder)
    except Exception as e:
        log.exception("scheduler.imap.failed", error=str(e))
        return

    if unreads:
        log.info("scheduler.imap.found", count=len(unreads))
        for reply in unreads:
            log.info(
                "scheduler.imap.reply",
                sender=reply.get("sender"),
                subject=(reply.get("subject") or "")[:120],
            )
    else:
        log.debug("scheduler.imap.no_replies")


def _get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def start_email_scheduler() -> None:
    """Inicia o scheduler (idempotente)."""
    scheduler = _get_scheduler()
    if scheduler.running:
        log.debug("scheduler.already_running")
        return

    interval = max(1, settings.email.scan_interval_min)
    # `check_inbox_async` é corrotina — APScheduler suporta awaitables no AsyncIOScheduler
    scheduler.add_job(
        check_inbox_async,
        "interval",
        minutes=interval,
        id="imap_scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("scheduler.started", minutes=interval, folder=settings.email.scan_folder)


async def stop_email_scheduler() -> None:
    """Para o scheduler de forma limpa (usado no shutdown do FastAPI)."""
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        return
    try:
        _scheduler.shutdown(wait=False)
        log.info("scheduler.stopped")
    except Exception as e:
        log.warning("scheduler.stop_failed", error=str(e))
    finally:
        _scheduler = None


# Compat: variável `scheduler` antiga ainda exportada para quem importar por nome
scheduler = _get_scheduler()


__all__ = [
    "scheduler",
    "start_email_scheduler",
    "stop_email_scheduler",
    "check_inbox_async",
]
