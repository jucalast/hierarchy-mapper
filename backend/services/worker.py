import asyncio
import json
from typing import Optional
from arq import create_pool
from sqlalchemy import select
from core.redis_config import redis_settings
from services.hierarchy.b2b_scanner import discover_employees_stream

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
    max_results: int = 100
):
    import urllib.parse
    print(f"[Worker] 🚀 TASK INVOKED: run_b2b_discovery_task for {company_name}")
    print(f"         Args: domain={domain}, cnpj={cnpj}, brand={confirmed_brand}, logo={confirmed_logo}, area={area_focus}")
    
    # 🕵️ Passo 0: Check Rápido no Banco (Para resposta instantânea)
    from core.database import async_session
    from models import Organization, Employee
    
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
            
            if not is_valid:
                print(f"[Worker] ⚠️ Cache de Organização ignorado por divergência: {db_org.name} vs {company_name}")
                db_org = None
            else:
                print(f"[Worker] ⚡ Encontro rápido no banco! Enviando nós imediatos para {db_org.name}")
            # Se já temos no banco mas falta logo, atualiza agora
            if (confirmed_logo and not db_org.logo_url) or (confirmed_brand and db_org.name != confirmed_brand):
                async with async_session() as session:
                    target = await session.get(Organization, db_org.id)
                    if target:
                        if confirmed_logo: target.logo_url = confirmed_logo
                        if confirmed_brand: target.name = confirmed_brand
                        await session.commit()
                if confirmed_logo: db_org.logo_url = confirmed_logo
                if confirmed_brand: db_org.name = confirmed_brand

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
            for i, p in enumerate(res_p.scalars().all()):
                fast_nodes.append({
                    "id": f"partner_{i}",
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

    # 🕵️ 1. Descoberta Completa (Só se não tivermos a empresa confirmada ou se faltar logo/linkedin no banco)
    from services.intelligence.brand_discovery import discover_company_brand
    
    # O usuário pediu explicitamente para NÃO encontrar o perfil novamente se já tivermos no banco.
    needs_discovery = db_org is None

    if needs_discovery:
        try:
            print(f"[Worker] 🔎 Localizando marca oficial para {company_name}...")
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
                    for i, p in enumerate(partners):
                        stmt_p = select(Employee).where(Employee.name == p.get("name"), Employee.company_id == db_org.id)
                        res_p = await session.execute(stmt_p)
                        if not res_p.scalars().first():
                            new_p = Employee(
                                name=p.get("name"),
                                role=p.get("role", "Sócio"),
                                department="Quadro de Sócios (QSA)",
                                seniority=6,
                                company_id=db_org.id
                            )
                            session.add(new_p)
                        
                        update_nodes.append({
                            "id": f"partner_{i}",
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
            print(f"[Worker] Erro na descoberta completa: {e}")
    else:
        print(f"[Worker] ✅ Marca já confirmada ({db_org.name}). Pulando descoberta de perfil.")
        # Se temos o logo no banco, vamos enviar uma atualização final para garantir que o UI tenha ele
        if db_org.logo_url:
            logo_proxy = f"http://127.0.0.1:8000/api/v1/proxy/image?url={db_org.logo_url}" if "http" in db_org.logo_url else db_org.logo_url
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
        max_results=max_results
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
            print(f"[Worker] Found {count} employees so far for {company_name}...")

    print(f"[Worker] Job completed for {company_name}. Total found: {count}")
    
    # 🏁 ÚLTIMO ESFORÇO: Garante que o Front-End saiba que ACABOU, 
    # mesmo que o loop tenha vindo vazio.
    try:
        await ctx['redis'].publish(f"job_updates_{ctx['job_id']}", json.dumps({"type": "done"}))
    except: pass

    return {"status": "completed", "count": count}

async def startup(ctx):
    print("[Worker] Worker started. Ready for heavy lifting...")

async def shutdown(ctx):
    print("[Worker] Worker shutting down...")

class WorkerSettings:
    functions = [run_b2b_discovery_task]
    redis_settings = redis_settings
    job_timeout = 1800 # 30 min (Aumentando de 300s pra dar tempo aos fallback engines e delays)
    on_startup = startup
    on_shutdown = shutdown
