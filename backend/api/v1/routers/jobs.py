"""
api.v1.routers.jobs
====================
Endpoints de gerenciamento de background jobs (ARQ + Redis).

POST /jobs/start-scan        → enfileira job de B2B discovery no ARQ
GET  /jobs/status/{job_id}   → consulta estado do job no Redis
POST /jobs/stop/{job_id}     → cancela job em andamento
WS   /jobs/ws/{job_id}       → WebSocket com progresso em tempo real (pub/sub Redis)

O worker que executa os jobs está em services/worker.py.
"""
import asyncio
import json
from typing import Optional

from arq import create_pool
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from core.infra.redis_config import redis_settings
from core.observability.logging_config import get_logger

router = APIRouter()
log = get_logger(__name__)

@router.websocket("/ws/{job_id}")
async def job_websocket(websocket: WebSocket, job_id: str):
    """
    WebSocket que notifica o frontend sobre o progresso de um Job específico.
    Escuta um canal no Redis para este job_id.
    """
    await websocket.accept()
    log.info("jobs.ws.connected", job_id=job_id)

    redis = await create_pool(redis_settings)
    pubsub = redis.pubsub()
    channel_name = f"job_updates_{job_id}"

    await pubsub.subscribe(channel_name)

    try:
        async for message in pubsub.listen():
            if message and message['type'] == 'message':
                data = message['data']
                if isinstance(data, bytes):
                    data = data.decode('utf-8')

                await websocket.send_text(data)

                try:
                    msg_obj = json.loads(data)
                    if msg_obj.get('type') == 'done':
                        log.info("jobs.ws.job_done", job_id=job_id)
                        await asyncio.sleep(0.5)
                        break
                except (json.JSONDecodeError, AttributeError):
                    pass
    except WebSocketDisconnect:
        log.info("jobs.ws.disconnected", job_id=job_id)
    finally:
        await pubsub.unsubscribe(channel_name)

@router.post("/start-scan")
async def start_scan(
    company_name: str,
    domain: Optional[str] = None,
    cnpj: Optional[str] = None,
    confirmed_brand: Optional[str] = None,
    confirmed_logo: Optional[str] = None,
    location: Optional[str] = None,
    product_focus: Optional[str] = None,
    area_focus: Optional[str] = "compras"
):
    """
    Enfileira um novo job de descoberta B2B no Redis/ARQ.
    Retorna o job_id para que o frontend possa monitorar.
    """
    try:
        redis = await create_pool(redis_settings)
        
        # Enfileira a tarefa definida no worker.py
        job = await redis.enqueue_job(
            'run_b2b_discovery_task',
            company_name=company_name,
            domain=domain,
            cnpj=cnpj,
            confirmed_brand=confirmed_brand,
            confirmed_logo=confirmed_logo,
            location=location,
            product_focus=product_focus,
            area_focus=area_focus
        )
        
        return {
            "job_id": job.job_id, 
            "status": "queued",
            "message": f"Scan started for {company_name}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enfileirar job: {str(e)}")

@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Verifica o estado atual de um job no Redis.
    """
    from core.infra.redis_config import redis_settings
    from arq.connections import create_pool
    
    redis = await create_pool(redis_settings)
    
    # Pegamos o job específico
    target_job = None
    from arq.jobs import Job
    target_job = Job(job_id, redis=redis)
    
    try:
        status = await target_job.status()
        if not status or status.value == "not_found":
            raise HTTPException(status_code=404, detail="Job não encontrado.")
        return {
            "job_id": job_id,
            "status": status.value
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")

@router.post("/stop/{job_id}")
async def stop_scan(job_id: str):
    """
    Cancela um job ARQ em andamento.
    """
    from core.infra.redis_config import redis_settings
    from arq.connections import create_pool
    from arq.jobs import Job
    
    try:
        redis = await create_pool(redis_settings)
        job = Job(job_id, redis=redis)
        
        # Define a chave de cancelamento do Redis para o worker escutar
        await redis.set(f"job_cancelled_{job_id}", "true", ex=600)
        
        status = await job.status()
        if not status or status.value == "not_found":
            # Mesmo que não ache no ARQ, publica para limpar o WS e retorna sucesso
            await redis.publish(f"job_updates_{job_id}", json.dumps({
                "type": "error",
                "message": "Operação cancelada com sucesso na interface."
            }))
            return {"status": "aborted", "message": "Job cancelado pelo usuário."}
            
        # Tenta abortar via ARQ
        try:
            await job.abort()
        except Exception as abort_err:
            log.warning("jobs.stop.abort_failed", job_id=job_id, error=str(abort_err))
            
        # Sempre envia a mensagem de erro/cancelado para forçar o WS a fechar
        await redis.publish(f"job_updates_{job_id}", json.dumps({
            "type": "error",
            "message": "Operação cancelada com sucesso na interface."
        }))
        
        return {"job_id": job_id, "status": "aborted", "message": "Scan abortado pelo usuário"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao tentar parar o job: {str(e)}")
