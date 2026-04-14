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
        # 🎯 Usar listen() em vez de get_message() para garantir que mensagens não sejam perdidas
        async for message in pubsub.listen():
            if message and message['type'] == 'message':
                data = message['data']
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                
                print(f"[WS] Enviando para frontend ({job_id}): {data[:100]}")
                await websocket.send_text(data)
                
                # Se recebeu "done", pode encerrar
                try:
                    msg_obj = json.loads(data)
                    if msg_obj.get('type') == 'done':
                        print(f"[WS] Job {job_id} finished, closing connection.")
                        break
                except:
                    pass
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
    from core.redis_config import redis_settings
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
    from core.redis_config import redis_settings
    from arq.connections import create_pool
    from arq.jobs import Job
    
    try:
        redis = await create_pool(redis_settings)
        job = Job(job_id, redis=redis)
        
        status = await job.status()
        if not status or status.value == "not_found":
            return {"status": "not_found", "message": "Job não encontrado ou já finalizado."}
            
        success = await job.abort()
        if success:
            await redis.publish(f"job_updates_{job_id}", json.dumps({
                "type": "error",
                "message": "Operação cancelada com sucesso na interface."
            }))
            return {"job_id": job_id, "status": "aborted", "message": "Scan abortado pelo usuário"}
        else:
            return {"job_id": job_id, "status": "failed", "message": "Não foi possível abortar o scan"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao tentar parar o job: {str(e)}")
