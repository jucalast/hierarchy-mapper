from fastapi import APIRouter, Depends, Query, HTTPException, WebSocket, WebSocketDisconnect
from arq import create_pool
from core.redis_config import redis_settings
from typing import Optional
import json
import asyncio

router = APIRouter()

@router.websocket("/ws/{job_id}")
async def job_websocket(websocket: WebSocket, job_id: str):
    """
    WebSocket que notifica o frontend sobre o progresso de um Job específico.
    Escuta um canal no Redis para este job_id.
    """
    await websocket.accept()
    print(f"[WS] Cliente conectado para monitorar Job: {job_id}")
    
    redis = await create_pool(redis_settings)
    pubsub = redis.pubsub()
    channel_name = f"job_updates_{job_id}"
    
    await pubsub.subscribe(channel_name)
    
    try:
        while True:
            # Verifica se há novas mensagens no Redis Pub/Sub
            message = await pubsub.get_message(timeout=1.0)
            if message and message['type'] == 'message':
                data = message['data']
                await websocket.send_text(data.decode('utf-8'))
            
            # Pequeno delay para não fritar o CPU
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        print(f"[WS] Cliente desconectado para Job: {job_id}")
    finally:
        await pubsub.unsubscribe(channel_name)

@router.post("/start-scan")
async def start_scan(
    company_name: str,
    domain: str,
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
    redis = await create_pool(redis_settings)
    job = await redis.all_job_results() # Apenas para debug/listagem se necessário
    
    # Pegamos o job específico
    target_job = None
    from arq.jobs import Job
    target_job = Job(job_id, redis=redis)
    
    try:
        status = await target_job.status()
        result = await target_job.result()
        return {
            "job_id": job_id,
            "status": status,
            "result": result
        }
    except Exception:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")
