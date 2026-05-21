"""
triggers — API de Gatilhos Autônomos

Endpoints para listar, dispensar e aprovar triggers detectados pelo TriggerService.
Também provê um endpoint SSE para notificações em tempo real.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .service import (
    get_pending_triggers,
    get_trigger,
    dismiss_trigger,
    mark_trigger_approved,
    register_trigger_callback,
    pause_service,
    resume_service,
    service_status,
)

router = APIRouter()

_sse_queues: set[asyncio.Queue] = set()


async def _broadcast_trigger(trigger: dict):
    """Enviado quando um novo trigger é detectado ou atualizado."""
    payload = json.dumps({"type": "trigger_update", "trigger": trigger})
    dead_queues = set()
    for q in list(_sse_queues):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead_queues.add(q)
    _sse_queues.difference_update(dead_queues)


register_trigger_callback(_broadcast_trigger)


@router.get("")
async def list_triggers():
    triggers = get_pending_triggers()
    return {"count": len(triggers), "triggers": triggers}


@router.get("/{trigger_id}")
async def get_trigger_detail(trigger_id: str):
    trigger = get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    return trigger


@router.post("/{trigger_id}/dismiss")
async def dismiss_trigger_endpoint(trigger_id: str):
    if not dismiss_trigger(trigger_id):
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    return {"status": "dismissed", "trigger_id": trigger_id}


@router.post("/{trigger_id}/approve")
async def approve_trigger_endpoint(trigger_id: str):
    trigger = get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    mark_trigger_approved(trigger_id)
    return {"status": "approved", "trigger_id": trigger_id, "suggested_plan": trigger.get("suggested_plan", [])}


@router.get("/stream/events")
async def trigger_events_stream():
    """Server-Sent Events — notificações em tempo real de novos triggers."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_queues.add(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            yield "data: {\"type\": \"connected\"}\n\n"
            pending = get_pending_triggers()
            if pending:
                for t in pending:
                    yield f"data: {json.dumps({'type': 'trigger_update', 'trigger': t})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _sse_queues.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/service/status")
async def get_service_status():
    return service_status()


@router.post("/service/pause")
async def pause_trigger_service():
    return {"status": pause_service()}


@router.post("/service/resume")
async def resume_trigger_service():
    return {"status": resume_service()}
