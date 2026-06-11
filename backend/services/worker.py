"""
services.worker
===============
ARQ worker — executor de background jobs pesados de B2B discovery.

Para iniciar o worker:
    python -m arq services.worker.WorkerSettings

Fluxo de run_b2b_discovery_task():
    1. Check rápido no banco (nós imediatos via pub/sub)
    2. Descoberta de marca institucional (se necessária)
    3. Streaming de funcionários via b2b_scanner
    4. Publicação de progresso no canal Redis `job_updates_{job_id}`

O frontend conecta ao WebSocket /api/v1/jobs/ws/{job_id} para receber as atualizações.
"""
import asyncio
import json
import traceback
from typing import Optional

from arq import create_pool
from arq.connections import RedisSettings
from arq.cron import cron

from core.infra.redis_config import redis_settings
from core.observability.logging_config import get_logger, configure_logging
from modules.hierarchy.service.b2b_scanner import discover_employees_stream
from modules.triggers.service.trigger_service import scan_email_triggers, scan_whatsapp_triggers


log = get_logger(__name__)


async def run_b2b_discovery_task(
    ctx, 
    company_name: str, 
    domain: str, 
    cnpj: Optional[str] = None,
    confirmed_brand: Optional[str] = None, 
    confirmed_logo: Optional[str] = None,
    location: Optional[str] = None, 
    product_focus: Optional[str] = None, 
    area_focus: Optional[str] = "compras",
    email_api_key: str = None, 
    max_results: int = 100,
    model: Optional[str] = None,
    strict_mode: bool = False
):
    import urllib.parse
    log.info("worker.task.started", company=company_name, domain=domain, area=area_focus, model=model, strict_mode=strict_mode)
    
    if model:
        from core.llm import set_preferred_model
        set_preferred_model(model, strict_mode)
    
    # 🕵️ Passo 0: Check Rápido no Banco (Para resposta instantânea)
    from core.infra.database import async_session
    from models import Organization, Employee
    from sqlalchemy import select
    
    fast_nodes = []
    async with async_session() as session:
        # Busca por CNPJ normalizado ou Nome
        norm_cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "") if cnpj else None
        stmt_fast = select(Organization)
        if norm_cnpj:
            stmt_fast = stmt_fast.where(Organization.cnpj == norm_cnpj)
        else:
            from sqlalchemy import func
            stmt_fast = stmt_fast.where(func.lower(Organization.name) == company_name.lower())
        
        res_fast = await session.execute(stmt_fast)
        db_org = res_fast.scalars().first()
        
        # 🛑 VALIDAÇÃO DE SEGURANÇA NO WORKER: Evita Grupo Penha atrelado a Spcom
        if db_org:
            cached_name = db_org.name.lower()
            requested_name = company_name.lower()
            is_valid = (requested_name in cached_name or cached_name in requested_name)
            
            # Se já temos no banco mas o nome mudou visivelmente ou falta o logo, atualiza
            if db_org and ((confirmed_logo and not db_org.logo_url) or (confirmed_brand and db_org.name != confirmed_brand)):
                log.info("worker.org.metadata_update", org=db_org.name, new_brand=confirmed_brand)
                
                # Se o nome mudou na mão, vamos atualizar também no Pipedrive para não duplicar!
                if confirmed_brand and db_org.name != confirmed_brand and db_org.pipedrive_id:
                    from modules.crm.service.pipedrive_service import PipedriveService
                    svc = PipedriveService()
                    try:
                        import asyncio
                        asyncio.create_task(svc.update_organization(db_org.pipedrive_id, {"name": confirmed_brand}))
                    except Exception as pe:
                        log.warning("worker.pipedrive.name_sync_failed", error=str(pe))

                async with async_session() as session:
                    target = await session.get(Organization, db_org.id)
                    if target:
                        if confirmed_logo: target.logo_url = confirmed_logo
                        if confirmed_brand: target.name = confirmed_brand
                        await session.commit()
                if confirmed_logo: db_org.logo_url = confirmed_logo
                if confirmed_brand: db_org.name = confirmed_brand
            else:
                if not is_valid:
                    log.debug("worker.org_cache.name_divergence", cached=db_org.name, requested=company_name)
                else:
                    log.info("worker.org_cache.hit", org=db_org.name)

            logo_url = confirmed_logo or db_org.logo_url
            if logo_url and "http" in logo_url and "ui-avatars" not in logo_url:
                # Codificação correta para evitar quebra de URL (especialmente links do LinkedIn)
                encoded_url = urllib.parse.quote(logo_url, safe='')
                logo_url = f"http://127.0.0.1:8000/api/v1/proxy/image?url={encoded_url}"
                
            fast_nodes.append({
                "id": "root_company",
                "name": confirmed_brand or db_org.name,
                "role": "Entidade Principal",
                "department": "Supply Chain (Matriz)",
                "manager_id": None,
                "level": 0,
                "domain": db_org.domain or domain,
                "logo": logo_url,
                "logo_url": logo_url,
                "company_logo": logo_url,
                "image": logo_url,
                "type": "initial"
            })
            # Sócios salvos
            stmt_p = select(Employee).where(Employee.company_id == db_org.id, Employee.department == "Quadro de Sócios (QSA)")
            res_p = await session.execute(stmt_p)
            for p in res_p.scalars().all():
                fast_nodes.append({
                    "id": f"partner_{p.id}",
                    "name": p.name,
                    "role": p.role,
                    "department": "Quadro de Sócios (QSA)",
                    "manager_id": "root_company",
                    "level": 6, # Top Level (QSA)
                    "type": "initial"
                })
            
            if fast_nodes:
                await ctx['redis'].publish(
                    f"job_updates_{ctx['job_id']}", 
                    json.dumps({"type": "initial", "nodes": fast_nodes}, ensure_ascii=False)
                )

    # 🕵️ 1. Descoberta Completa (PULA se já tivermos a confirmação do usuário)
    from modules.intelligence.service.brand_discovery import discover_company_brand
    
    # Se o frontend mandou confirmed_brand, NÃO PRECISAMOS de descoberta de perfil. 
    needs_discovery = (db_org is None) and (confirmed_brand is None)

    if not needs_discovery:
        display_name = confirmed_brand or (db_org.name if db_org else "Empresa Selecionada")
        log.info("worker.brand_discovery.skipped", brand=display_name)
    
    if needs_discovery:
        try:
            log.info("worker.brand_discovery.started", company=company_name)
            brand_data = await discover_company_brand(cnpj=cnpj or "", domain=domain, raw_name=company_name)
            if brand_data:
                # Se achamos a marca, vamos garantir que ela está vinculada agora
                async with async_session() as session:
                    stmt_o = select(Organization).where(Organization.name == brand_data.get("brand"))
                    res_o = await session.execute(stmt_o)
                    db_org = res_o.scalars().first()
                    
                    if not db_org:
                        db_org = Organization(
                            name=brand_data.get("brand"),
                            domain=brand_data.get("detected_domain") or domain,
                            cnpj=cnpj.replace(".", "").replace("/", "").replace("-", "") if cnpj else None,
                            logo_url=brand_data.get("logo"),
                            linkedin_url=brand_data.get("linkedin_url")
                        )
                        session.add(db_org)
                    else:
                        # Atualiza logo/url se vieram novos
                        if not db_org.logo_url: db_org.logo_url = brand_data.get("logo")
                        if not db_org.linkedin_url: db_org.linkedin_url = brand_data.get("linkedin_url")
                    
                    await session.commit()
                    await session.refresh(db_org)

                # Transmite os sócios (se houver) encontrados pela descoberta de marca
                partners = brand_data.get("partners", [])
                logo_url = db_org.logo_url
                if logo_url and "http" in logo_url and "ui-avatars" not in logo_url:
                    logo_url = f"http://127.0.0.1:8000/api/v1/proxy/image?url={logo_url}"

                update_nodes = [{
                    "id": "root_company",
                    "name": db_org.name,
                    "logo": logo_url,
                    "type": "initial",
                    "level": 0
                }]
                
                async with async_session() as session:
                    for p in partners:
                        stmt_p = select(Employee).where(Employee.name == p.get("name"), Employee.company_id == db_org.id)
                        res_p = await session.execute(stmt_p)
                        db_p = res_p.scalars().first()
                        if not db_p:
                            db_p = Employee(
                                name=p.get("name"),
                                role=p.get("role", "Sócio"),
                                department="Quadro de Sócios (QSA)",
                                seniority=6,
                                company_id=db_org.id
                            )
                            session.add(db_p)
                            await session.flush()
                        
                        update_nodes.append({
                            "id": f"partner_{db_p.id}",
                            "name": p.get("name"),
                            "role": p.get("role", "Sócio"),
                            "department": "Quadro de Sócios (QSA)",
                            "level": 6,
                            "type": "initial"
                        })
                    await session.commit()
                
                await ctx['redis'].publish(
                    f"job_updates_{ctx['job_id']}", 
                    json.dumps({"type": "initial", "nodes": update_nodes}, ensure_ascii=False)
                )
        except Exception as e:
            log.exception("worker.brand_discovery.failed", company=company_name, error=str(e))
    else:
        display_name = confirmed_brand or (db_org.name if db_org else "Empresa Selecionada")
        log.info("worker.brand_confirmed.using_existing", brand=display_name)
        
        # Se temos o logo (confirmado ou no banco), vamos enviar uma atualização final para garantir que o UI tenha ele
        target_logo = confirmed_logo or (db_org.logo_url if db_org else None)
        if target_logo:
            logo_proxy = f"http://127.0.0.1:8000/api/v1/proxy/image?url={target_logo}" if "http" in target_logo else target_logo
            await ctx['redis'].publish(
                f"job_updates_{ctx['job_id']}", 
                json.dumps({"type": "initial", "nodes": [{"id": "root_company", "logo": logo_proxy}]}, ensure_ascii=False)
            )

    count = 0
    async for batch in discover_employees_stream(
        company_name=company_name,
        domain=domain,
        cnpj=cnpj,
        confirmed_brand=confirmed_brand,
        location=location,
        product_focus=product_focus,
        area_focus=area_focus,
        email_api_key=email_api_key,
        max_results=max_results,
        job_id=ctx['job_id']
    ):
        # Publica o progresso via Redis Pub/Sub para o WebSocket
        if isinstance(batch, list) and len(batch) > 0:
            if batch[0].get("type") == "done":
                await ctx['redis'].publish(f"job_updates_{ctx['job_id']}", json.dumps({"type": "done"}))
                break
            
            # Envia o lote de novos nós para o frontend
            msg_type = batch[0].get("type", "batch")
            await ctx['redis'].publish(
                f"job_updates_{ctx['job_id']}", 
                json.dumps({"type": msg_type, "nodes": batch}, ensure_ascii=False)
            )
            
            count += len(batch)

    log.info("worker.task.completed", company=company_name, total=count)
    
    # 🏁 ÚLTIMO ESFORÇO: Garante que o Front-End saiba que ACABOU, 
    # mesmo que o loop tenha vindo vazio.
    try:
        await ctx['redis'].publish(f"job_updates_{ctx['job_id']}", json.dumps({"type": "done"}))
    except Exception as e:
        log.warning("worker.task.final_publish_failed", error=str(e))

    return {"status": "completed", "count": count}


async def startup(ctx):
    """Hook executado quando o worker ARQ inicia."""
    configure_logging()
    log.info("worker.started")


async def shutdown(ctx):
    """Hook executado quando o worker ARQ encerra."""
    log.info("worker.shutdown")

async def run_agent_task(ctx, payload_dict: dict):
    from modules.agent import run_agent
    job_id = payload_dict["job_id"]
    try:
        log.info("worker.agent_task.started", job_id=job_id)
        async for chunk in run_agent(
            message=payload_dict["message"],
            history=payload_dict.get("history", []),
            org_id=payload_dict.get("org_id"),
            preferred=payload_dict.get("preferred"),
            strict_mode=payload_dict.get("strict_mode", False),
            thread_id=payload_dict.get("thread_id"),
            direct_action=payload_dict.get("direct_action", False),
            parent_message_id=payload_dict.get("parent_message_id"),
            action_index=payload_dict.get("action_index"),
            is_regeneration=payload_dict.get("is_regeneration", False),
        ):
            await ctx['redis'].publish(f"agent_updates_{job_id}", chunk)
        
        await ctx['redis'].publish(f"agent_updates_{job_id}", json.dumps({"type": "job_done"}))
        log.info("worker.agent_task.completed", job_id=job_id)
    except Exception as e:
        log.exception("worker.agent_task.failed", job_id=job_id, error=str(e))
        await ctx['redis'].publish(f"agent_updates_{job_id}", json.dumps({"type": "error", "error": str(e)}))

async def resume_agent_task(ctx, payload_dict: dict):
    from modules.agent import resume_after_confirmation
    job_id = payload_dict["job_id"]
    try:
        log.info("worker.resume_agent_task.started", job_id=job_id)
        async for chunk in resume_after_confirmation(
            action_id=payload_dict["action_id"],
            approved=payload_dict["approved"],
            thread_id=payload_dict.get("thread_id"),
            attachment_path=payload_dict.get("attachment_path"),
        ):
            await ctx['redis'].publish(f"agent_updates_{job_id}", chunk)
            
        await ctx['redis'].publish(f"agent_updates_{job_id}", json.dumps({"type": "job_done"}))
        log.info("worker.resume_agent_task.completed", job_id=job_id)
    except Exception as e:
        log.exception("worker.resume_agent_task.failed", job_id=job_id, error=str(e))
        await ctx['redis'].publish(f"agent_updates_{job_id}", json.dumps({"type": "error", "error": str(e)}))


async def run_smart_reschedule_task(ctx):
    import json
    from modules.crm.service.pipedrive_service import pipedrive_service
    job_id = ctx.get('job_id')
    redis = ctx.get('redis')
    
    log.info("worker.smart_reschedule.started", job_id=job_id)
    try:
        while True:
            res = await pipedrive_service.smart_reschedule_activities()
            if res.get("status") == "error":
                log.error("worker.smart_reschedule.error", error=res.get("message"))
                await asyncio.sleep(10)
                continue
                
            updated = res.get("stats", {}).get("updated", 0)
            if updated == 0:
                log.info("worker.smart_reschedule.finished_clean", job_id=job_id)
                if job_id and redis:
                    await redis.publish(f"job_updates_{job_id}", json.dumps({"type": "job_done", "message": "Tarefas reorganizadas!"}))
                break
                
            log.info("worker.smart_reschedule.batch_done", updated=updated)
            await asyncio.sleep(2)
    except Exception as e:
        log.exception("worker.smart_reschedule.fatal", error=str(e), job_id=job_id)
        if job_id and redis:
            await redis.publish(f"job_updates_{job_id}", json.dumps({"type": "error", "message": str(e)}))


class WorkerSettings:
    functions = [run_b2b_discovery_task, run_agent_task, resume_agent_task, run_smart_reschedule_task]
    cron_jobs = [
        cron(scan_email_triggers, minute=set(range(0, 60, 2))),
        cron(scan_whatsapp_triggers, minute=set(range(0, 60, 1))),
    ]
    redis_settings = redis_settings
    job_timeout = 1800 # 30 min (Aumentando de 300s pra dar tempo aos fallback engines e delays)
    allow_abort_jobs = True
    on_startup = startup
    on_shutdown = shutdown

