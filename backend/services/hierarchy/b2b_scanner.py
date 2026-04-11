import re
import html
import os
import time
import asyncio
import json
import random
from typing import List, Dict, Optional, AsyncGenerator
from sqlalchemy import select, delete, or_, func

from core.database import async_session
from models import Organization, Employee
from services.hierarchy.search_engine import get_duck_results
from services.hierarchy.role_engine import role_engine
from services.hierarchy.org_search import org_search
from services.hierarchy.candidate_processor import CandidateProcessor
from services.intelligence.preview_service import get_url_preview
from services.hierarchy.filters import get_seniority_level, get_department_tag
from services.external.email_service import apply_pattern
from services.hierarchy.logging_utils import log_session_start, log_query_start

async def discover_employees(company_name: str, domain: str, email_api_key: str = None, max_results: int = 50) -> List[Dict]:
    """Motor B2B síncrono para descoberta de funcionários (Agora Async)."""
    results = []
    async for batch in discover_employees_stream(company_name, domain, max_results=max_results):
        for node in batch:
            if node.get("status") != "done":
                results.append(node)
    return results

async def discover_employees_stream(
    company_name: str, 
    domain: str, 
    cnpj: Optional[str] = None,
    confirmed_brand: Optional[str] = None, 
    location: Optional[str] = None, 
    product_focus: Optional[str] = None, 
    area_focus: Optional[str] = "compras",
    email_api_key: str = None, 
    max_results: int = 100
) -> AsyncGenerator[List[Dict], None]:
    """
    Motor B2B Streaming Orquestrado (Modular).
    Caminho Feliz: Search -> CandidateProcessor -> RoleEngine -> Database -> UI.
    """
    temp_brand = confirmed_brand or company_name.split(" (")[0]
    brand_name_log = temp_brand.upper()
    
    # 1. DATABASE SYNC (Busca Resiliente: CNPJ -> Nome)
    async with async_session() as session:
        org = None
        norm_cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "") if cnpj else None
        
        # 1. Tenta por CNPJ
        if norm_cnpj:
            res = await session.execute(select(Organization).where(Organization.cnpj == norm_cnpj))
            org = res.scalars().first()
        
        # 2. Tenta por Nome (Case Insensitive)
        if not org:
            search_brand = confirmed_brand or company_name.split(" (")[0]
            res = await session.execute(select(Organization).where(func.lower(Organization.name) == search_brand.lower()))
            org = res.scalars().first()
        
        if not org:
            # Fallback final: cria nova
            org = Organization(name=temp_brand, domain=domain, cnpj=norm_cnpj)
            session.add(org)
            await session.flush()
        else:
            # Garante que o CNPJ seja preenchido se não estava
            if norm_cnpj and not org.cnpj: 
                org.cnpj = norm_cnpj
            # Garante que o domínio seja preenchido se não estava
            if domain and not org.domain:
                org.domain = domain
        
        db_org_id = org.id
        await session.execute(delete(Employee).where(Employee.company_id == db_org_id, or_(Employee.department != "Quadro de Sócios (QSA)", Employee.department == None)))
        await session.commit()

    # 2. QUERY GENERATION
    base_queries = []
    if area_focus == "logistica":
        base_queries = [f'"{temp_brand}" Logística linkedin', f'"{temp_brand}" "Supply Chain" linkedin', f'"{temp_brand}" Gerente Logística linkedin']
    else:
        base_queries = [f'"{temp_brand}" Comprador linkedin', f'"{temp_brand}" "Analista de Compras" linkedin', f'"{temp_brand}" Procurement linkedin']
    
    if product_focus:
        from services.external.groq_service import expand_product_to_b2b_terms
        all_terms = await expand_product_to_b2b_terms(product_focus)
        for t in all_terms[:3]:
            base_queries.insert(0, f'"{temp_brand}" "{area_focus}" "{t}" linkedin')

    # 3. SEARCH & PROCESSING LOOP
    processor = CandidateProcessor(temp_brand, domain, area_focus, location, product_focus)
    seen_urls = set()
    
    print(f"[B2B Engine] 🚀 Iniciando Escaneamento: {brand_name_log}")
    await role_engine.proactive_health_check()
    log_session_start(temp_brand, location, area_focus)

    for idx, query in enumerate(base_queries[:12]):
        if idx > 0: 
            wait_time = random.uniform(10.0, 15.0)
            print(f"      [B2B Engine] Aguardando {wait_time:.1f}s para a próxima busca...")
            await asyncio.sleep(wait_time)
        
        log_query_start(query)
        results = await get_duck_results(query, max_results=30)
        if not results: continue

        found_nodes = []
        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            if not href or "linkedin.com/in/" not in href or any(n in href for n in ["/posts/", "/jobs/", "/company/", "/dir/"]) or href in seen_urls:
                continue
            
            seen_urls.add(href)
            
            # Processa o candidato usando o novo módulo
            node_data = await processor.process_candidate(res)
            
            if node_data:
                # Persistência
                async with async_session() as session:
                    emp = Employee(
                        name=node_data["name"],
                        role=node_data["role"],
                        department=node_data["department"],
                        seniority=node_data["level"],
                        linkedin_url=node_data["linkedin"],
                        email=node_data["email"],
                        company_id=db_org_id
                    )
                    session.add(emp)
                    await session.commit()
                
                found_nodes.append(node_data)
                yield [node_data]
                
                # 🛠️ OTIMIZAÇÃO: "SÓ PARA... SE APROVAR ALGUÉM"
                # Uma vez que encontramos um candidato válido para esta query, passamos para a próxima
                # para economizar processamento e API da IA.
                break
                
    # Sinal de conclusão (MUITO IMPORTANTE para o front-end parar o loading)
    yield [{"type": "done"}]

import random # For delay
