"""
triggers — API de Gatilhos Autônomos

Endpoints para listar, dispensar e aprovar triggers detectados pelo TriggerService.
Também provê um endpoint SSE para notificações em tempo real.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from .service.trigger_service import (
    get_pending_triggers,
    get_trigger,
    dismiss_trigger,
    mark_trigger_approved,
    pause_service,
    resume_service,
    service_status,
)
from core.infra.redis_config import redis_settings
from arq.connections import create_pool

router = APIRouter()

async def get_redis():
    return await create_pool(redis_settings)

@router.get("")
async def list_triggers():
    redis = await get_redis()
    triggers = await get_pending_triggers(redis)
    return {"count": len(triggers), "triggers": triggers}


@router.get("/{trigger_id}")
async def get_trigger_detail(trigger_id: str):
    redis = await get_redis()
    trigger = await get_trigger(redis, trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    return trigger


@router.post("/{trigger_id}/dismiss")
async def dismiss_trigger_endpoint(trigger_id: str):
    redis = await get_redis()
    if not await dismiss_trigger(redis, trigger_id):
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    return {"status": "dismissed", "trigger_id": trigger_id}


@router.post("/{trigger_id}/approve")
async def approve_trigger_endpoint(trigger_id: str):
    redis = await get_redis()
    trigger = await get_trigger(redis, trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    await mark_trigger_approved(redis, trigger_id)
    return {"status": "approved", "trigger_id": trigger_id, "suggested_plan": trigger.get("suggested_plan", [])}


@router.get("/stream/events")
async def trigger_events_stream(request: Request):
    """Server-Sent Events — notificações em tempo real de novos triggers assinando via Redis PubSub."""
    redis = await get_redis()
    
    async def event_generator() -> AsyncGenerator[str, None]:
        pubsub = redis.pubsub()
        await pubsub.subscribe("trigger_events")
        try:
            yield "data: {\"type\": \"connected\"}\n\n"
            pending = await get_pending_triggers(redis)
            if pending:
                for t in pending:
                    yield f"data: {json.dumps({'type': 'trigger_update', 'trigger': t})}\n\n"
            
            while True:
                if await request.is_disconnected():
                    break
                
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=10.0)
                if message:
                    if isinstance(message['data'], bytes):
                        data = message['data'].decode('utf-8')
                    else:
                        data = message['data']
                    yield f"data: {data}\n\n"
                else:
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe("trigger_events")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("/service/status")
async def get_service_status():
    redis = await get_redis()
    return await service_status(redis)


@router.post("/service/pause")
async def pause_trigger_service():
    redis = await get_redis()
    return {"status": await pause_service(redis)}


@router.post("/service/resume")
async def resume_trigger_service():
    redis = await get_redis()
    return {"status": await resume_service(redis)}
