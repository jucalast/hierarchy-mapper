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
from services.hierarchy.filters import get_seniority_level, get_department_tag, PURCHASING_KEYWORDS, LOGISTICS_KEYWORDS, apply_strict_filters
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

    # 1. CLEAN BRAND FOR SEARCH (Remove ruído corporativo: GmbH, Ltda, etc)
    clean_brand = temp_brand.replace("Gmb H", "").replace("GmbH", "").replace("Ltda", "").replace("S.A.", "").strip()
    
    # 2. DYNAMIC QUERY GENERATION (Lê do centralizador filters.py)
    search_location = location if location else "Brasil"
    selected_terms = LOGISTICS_KEYWORDS if area_focus == "logistica" else PURCHASING_KEYWORDS
    base_queries = []
    
    # Gera as queries (Marca simplificada e sem aspas rígidas para maior alcance)
    for term in selected_terms:
        # Usamos apenas a marca limpa, sem aspas forçadas na frente
        base_queries.append(f'{clean_brand} {term} {search_location} linkedin')
    
    if product_focus:
        from services.external.groq_service import expand_product_to_b2b_terms, evaluate_lead_temperature
        all_terms = await expand_product_to_b2b_terms(product_focus)
        for t in all_terms[:3]:
            base_queries.insert(0, f'"{temp_brand}" "{area_focus}" "{t}" linkedin')

    from services.external.groq_service import evaluate_lead_temperature
    from services.pipedrive.pipedrive_service import pipedrive_service

    # 3. SEARCH & PROCESSING LOOP
    processor = CandidateProcessor(temp_brand, domain, area_focus, location, product_focus)
    seen_urls = set()
    consecutive_empty = 0  # 🛡️ FIX #5: Quórum de parada inteligente
    
    print(f"[B2B Engine] Iniciando Escaneamento: {brand_name_log}")
    await role_engine.proactive_health_check()
    log_session_start(temp_brand, location, area_focus)

    # 🚀 EXTRAÇÃO E AVALIAÇÃO DE TEMPERATURA DOS LEADS DO PIPEDRIVE
    pipedrive_org_id = None
    async with async_session() as session:
        res = await session.execute(select(Organization).where(Organization.id == db_org_id))
        org_check = res.scalars().first()
        if org_check and org_check.pipedrive_id:
            pipedrive_org_id = org_check.pipedrive_id

    if pipedrive_org_id:
        print(f"[B2B Engine] Organização tem Pipedrive ID ({pipedrive_org_id}). Buscando pessoas e definindo temperatura...")
        try:
            pd_details = await pipedrive_service.get_organization_details(pipedrive_org_id)
            pd_persons = pd_details.get("persons", [])
            pd_activities = pd_details.get("activities", [])
            pd_notes = pd_details.get("notes", [])
            
            for person in pd_persons:
                if not person.get("name"): continue
                
                # Filtra atividades e notas desse contato
                person_activities = [a for a in pd_activities if a.get("person_id") == person.get("id")]
                person_notes = [n for n in pd_notes if n.get("person_id") == person.get("id")]
                
                a_text = " | ".join([f"{a.get('subject')} ({a.get('type')})" for a in person_activities])
                n_text = " | ".join([n.get("content", "") for n in person_notes])
                
                # IA Avalia a temperatura do lead baseada no histórico CRM
                temperature = await evaluate_lead_temperature(a_text, n_text)
                
                # Processa o funcionário usando o processador (simula como se visse do duckduckgo mas com dados exatos)
                name = person.get("name")
                email = None
                if person.get("email") and len(person["email"]) > 0:
                    email = person["email"][0].get("value")
                phone = None
                if person.get("phone") and len(person["phone"]) > 0:
                    phone = person["phone"][0].get("value")
                
                # Emula o dictionary do DuckDuckGo p/ CandidateProcessor
                fake_res = {
                    "title": f"{name} - {temp_brand}",
                    "body": f"Email: {email} | Telefone: {phone} | Pipedrive ID: {person.get('id')}",
                    "href": f"https://linkedin.com/in/pd_{person.get('id')}" # Falso, só pra não dar erro se não tiver
                }
                
                processor_res = await processor.process_candidate(fake_res)
                if processor_res and processor_res.get("main"):
                    node_data = processor_res.get("main")
                    node_data["temperature"] = temperature
                    node_data["source"] = "Pipedrive"
                    
                    async with async_session() as session:
                        emp = Employee(
                            name=name,
                            role=node_data.get("role", "Contato no Pipedrive"),
                            department="Vendas/Pipedrive", # Fake it until real is found
                            seniority=node_data.get("level", 5),
                            email=email,
                            temperature=temperature,
                            company_id=db_org_id,
                            linkedin_url=f"pipedrive_{person.get('id')}",
                        )
                        session.add(emp)
                        await session.commit()
                    
                    yield [node_data]
        except Exception as e:
            print(f"[B2B Engine/Pipedrive] Erro ao processar pessoas via CRM: {str(e)}")

    for idx, query in enumerate(base_queries[:12]):
        if idx > 0: 
            wait_time = random.uniform(20.0, 30.0) # Aumentado para segurança total
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
            
            # Processa o candidato usando o novo módulo (capturando órfãos)
            processor_res = await processor.process_candidate(res)
            if not processor_res: continue
            
            node_data = processor_res.get("main")
            orphans = processor_res.get("orphans", [])

            # 1. Persistência do Nó Principal (se existir e for válido)
            if node_data:
                async with async_session() as session:
                    stmt_emp = select(Employee).where(Employee.linkedin_url == node_data["linkedin"])
                    res_emp = await session.execute(stmt_emp)
                    existing_emp = res_emp.scalars().first()

                    if existing_emp:
                        existing_emp.name = node_data["name"]
                        existing_emp.role = node_data["role"]
                        existing_emp.department = node_data["department"]
                        existing_emp.seniority = node_data["level"]
                        existing_emp.company_id = db_org_id
                        existing_emp.profile_pic = node_data.get("avatar")
                        existing_emp.last_scanned = func.now()
                    else:
                        emp = Employee(
                            name=node_data["name"],
                            role=node_data["role"],
                            department=node_data["department"],
                            seniority=node_data["level"],
                            linkedin_url=node_data["linkedin"],
                            email=node_data["email"],
                            profile_pic=node_data.get("avatar"),
                            company_id=db_org_id
                        )
                        session.add(emp)
                    await session.commit()
                
                found_nodes.append(node_data)
                yield [node_data]

            # 2. Promoção e Persistência de Órfãos (Aproveitamento com Repescagem)
            for orphan in orphans:
                # Verifica se já existe no banco (Prioridade: linkedin_url, senão nome+empresa)
                async with async_session() as session:
                    if orphan.get("linkedin"):
                        stmt_o = select(Employee).where(Employee.linkedin_url == orphan["linkedin"])
                    else:
                        stmt_o = select(Employee).where(Employee.name == orphan["name"], Employee.company_id == db_org_id)
                    
                    res_o = await session.execute(stmt_o)
                    if res_o.scalars().first():
                        continue # Já conhecemos
                
                # Roda a Repescagem para o Órfão (Transforma em nó completo)
                upgraded_node = await processor.upgrade_orphan(orphan)
                
                if upgraded_node:
                    async with async_session() as session:
                        # Segunda verificação pós-upgrade para garantir que não achou um linkedin já cadastrado
                        if upgraded_node.get("linkedin"):
                            check_stmt = select(Employee).where(Employee.linkedin_url == upgraded_node["linkedin"])
                            check_res = await session.execute(check_stmt)
                            if check_res.scalars().first():
                                continue
                            
                        new_emp = Employee(
                            name=upgraded_node["name"],
                            role=upgraded_node["role"],
                            company_id=db_org_id,
                            department=upgraded_node["department"],
                            seniority=upgraded_node["level"],
                            linkedin_url=upgraded_node["linkedin"],
                            email=upgraded_node["email"],
                            profile_pic=upgraded_node.get("avatar")
                        )
                        session.add(new_emp)
                        await session.commit()
                        
                        found_nodes.append(upgraded_node)
                        # Opcional: Yield para o front-end ver o órfão aparecendo? 
                        # Sim, pois ele já passou pelo filtro de relevância do upgrade_orphan.
                        yield [upgraded_node]
                
        # 🛡️ FIX #5: Quórum de parada inteligente (substitui o 'break' prematuro)
        if found_nodes:
            consecutive_empty = 0  # Reset se encontrou alguém nesta query
        else:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                print(f"      [B2B Engine] 3 consultas consecutivas sem resultados. Encerrando escaneamento.")
                break
                
    # Sinal de conclusão (MUITO IMPORTANTE para o front-end parar o loading)
    yield [{"type": "done"}]

import random # For delay
