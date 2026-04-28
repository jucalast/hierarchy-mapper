"""
triggers.py — API de Gatilhos Autônomos

Endpoints para listar, dispensar e aprovar triggers detectados pelo TriggerService.
Também provê um endpoint SSE para notificações em tempo real.
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from services.ai.trigger_service import (
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

# SSE broadcast queue — cada conexão SSE recebe uma ref a este set de queues
_sse_queues: set[asyncio.Queue] = set()


# =============================================================================
# CALLBACK DE BROADCAST (registrado no startup)
# =============================================================================

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


# Registra o callback no TriggerService ao importar o módulo
register_trigger_callback(_broadcast_trigger)


# =============================================================================
# ENDPOINTS REST
# =============================================================================

@router.get("")
async def list_triggers():
    """Lista todos os triggers pendentes (resposta recebida aguardando análise/aprovação)."""
    triggers = get_pending_triggers()
    return {
        "count": len(triggers),
        "triggers": triggers,
    }


@router.get("/{trigger_id}")
async def get_trigger_detail(trigger_id: str):
    """Detalhe de um trigger específico."""
    trigger = get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    return trigger


@router.post("/{trigger_id}/dismiss")
async def dismiss_trigger_endpoint(trigger_id: str):
    """Dispensa um trigger sem tomar ação."""
    if not dismiss_trigger(trigger_id):
        raise HTTPException(status_code=404, detail="Trigger não encontrado")
    return {"status": "dismissed", "trigger_id": trigger_id}


@router.post("/{trigger_id}/approve")
async def approve_trigger_endpoint(trigger_id: str):
    """
    Marca um trigger como aprovado.
    A execução do plano sugerido deve ser feita pelo frontend via /ai/agent-action
    para cada ação do suggested_plan.
    """
    trigger = get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger não encontrado")

    mark_trigger_approved(trigger_id)
    return {
        "status": "approved",
        "trigger_id": trigger_id,
        "suggested_plan": trigger.get("suggested_plan", []),
    }


# =============================================================================
# SSE — NOTIFICAÇÕES EM TEMPO REAL
# =============================================================================

@router.get("/stream/events")
async def trigger_events_stream():
    """
    Server-Sent Events — o frontend conecta aqui para receber notificações
    em tempo real quando um novo trigger é detectado ou atualizado.

    Uso no frontend:
        const es = new EventSource('/api/v1/triggers/stream/events');
        es.onmessage = (e) => {
            const { type, trigger } = JSON.parse(e.data);
            if (type === 'trigger_update') handleNewTrigger(trigger);
        };
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _sse_queues.add(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Envia heartbeat inicial para confirmar conexão
            yield "data: {\"type\": \"connected\"}\n\n"

            # Envia triggers já pendentes ao conectar
            pending = get_pending_triggers()
            if pending:
                for t in pending:
                    payload = json.dumps({"type": "trigger_update", "trigger": t})
                    yield f"data: {payload}\n\n"

            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat para manter conexão viva
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _sse_queues.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# =============================================================================
# CONTROLE DO SERVIÇO (kill switch + status)
# =============================================================================

@router.get("/service/status")
async def get_service_status():
    """
    Retorna o estado atual do TriggerService:
    - paused: se foi pausado manualmente
    - quiet_hours: se está dentro do horário de silêncio (22h-7h)
    - active: se está processando triggers
    """
    return service_status()


@router.post("/service/pause")
async def pause_trigger_service():
    """Para o polling do TriggerService imediatamente (sem reiniciar o servidor)."""
    return {"status": pause_service()}


@router.post("/service/resume")
async def resume_trigger_service():
    """Retoma o polling do TriggerService."""
    return {"status": resume_service()}
