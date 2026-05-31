"""
modules.hierarchy.service.b2b_scanner
======================================
Motor principal de discovery B2B via DuckDuckGo + perfis LinkedIn.

Emite lotes de nos via async generator para o ARQ worker publicar
no canal Redis e o frontend receber via WebSocket em tempo real.

Funcoes publicas:
    discover_employees_stream(company, domain, ...) -> AsyncGenerator
    discover_employees(company, domain, ...) -> list[dict]
"""
import re
import html
import os
import time
import asyncio
import json
import random
from typing import List, Dict, Optional, AsyncGenerator
from sqlalchemy import select, delete, or_, func

from core.infra.database import async_session
from models import Organization, Employee
from .search_engine import get_duck_results
from .role_engine import role_engine
from .org_search import org_search
from .candidate_processor import CandidateProcessor
from modules.intelligence.service.preview_service import get_url_preview
from .filters import get_seniority_level, get_department_tag, PURCHASING_KEYWORDS, LOGISTICS_KEYWORDS, apply_strict_filters, is_same_person
from core.external.email_service import apply_pattern
from .logging_utils import log_session_start, log_query_start

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
    max_results: int = 100,
    job_id: Optional[str] = None
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
        
        # 🚀 LIMPEZA IMEDIATA: Deleta funcionários antigos (MENOS os sócios)
        # Isso atende ao requisito: "os employees devem sumir do front, menos root e sócios".
        from sqlalchemy import delete, and_, not_, or_
        await session.execute(
            delete(Employee).where(
                and_(
                    Employee.company_id == db_org_id,
                    not_(
                        or_(
                            Employee.department == "Quadro de Sócios (QSA)",
                            Employee.department.ilike("%Sócio%"),
                            Employee.department.ilike("%Societário%"),
                            Employee.department.ilike("%Conselho%"),
                            Employee.seniority == 6
                        )
                    )
                )
            )
        )
        await session.commit()
        
        # Avisa o front-end para limpar os nós existentes
        yield [{"type": "clear_nodes"}]

    # 1. CLEAN BRAND FOR SEARCH (Remove ruído corporativo: GmbH, Ltda, etc)
    clean_brand = temp_brand.replace("Gmb H", "").replace("GmbH", "").replace("Ltda", "").replace("S.A.", "").strip()
    
    # 2. DYNAMIC QUERY GENERATION (Lê do centralizador filters.py com suporte a banco de dados)
    search_location = location if location else "Brasil"
    
    from modules.ai.service.context.business_context import load_db_setting
    hierarchy_config = await load_db_setting("hierarchy_config", {})
    purchasing_kws = hierarchy_config.get("purchasing_keywords", PURCHASING_KEYWORDS) if isinstance(hierarchy_config, dict) else PURCHASING_KEYWORDS
    logistics_kws = hierarchy_config.get("logistics_keywords", LOGISTICS_KEYWORDS) if isinstance(hierarchy_config, dict) else LOGISTICS_KEYWORDS
    
    selected_terms = logistics_kws if area_focus == "logistica" else purchasing_kws
    base_queries = []
    
    # ==== REGRA DE NEGÓCIO: PRIORIZAR SÓCIOS DO CNPJ ====
    # 1. Busca os sócios que já estão no banco (vindos do QSA/CNPJ)
    qsa_partners = []
    rejected_urls = set()
    rejected_names = set()
    async with async_session() as session:
        stmt = select(Employee).where(Employee.company_id == db_org_id, Employee.department == "Quadro de Sócios (QSA)")
        res = await session.execute(stmt)
        qsa_partners = res.scalars().all()

        # Busca funcionários rejeitados (Reprovados) para essa empresa para ignorá-los
        stmt_rej = select(Employee).where(
            Employee.company_id == db_org_id,
            (Employee.role == "Reprovado") | (Employee.department == "Reprovado")
        )
        res_rej = await session.execute(stmt_rej)
        for emp in res_rej.scalars().all():
            if emp.linkedin_url:
                rejected_urls.add(emp.linkedin_url.split("?")[0].rstrip("/"))
            rejected_names.add(emp.name.lower().strip())

    # 2. Envia os sócios do QSA imediatamente para o front-end (mesmo sem LinkedIn)
    if qsa_partners:
        print(f"[B2B Engine] {len(qsa_partners)} sócios encontrados no CNPJ. Enviando para o front...")
        nodes_qsa = []
        for p in qsa_partners:
            nodes_qsa.append({
                "id": p.id,
                "name": p.name,
                "role": p.role or "Sócio / Administrador",
                "department": "Quadro de Sócios (QSA)",
                "level": 6,
                "linkedin": p.linkedin_url,
                "source": "CNPJ/QSA"
            })
            # Cria query específica para o nome do sócio
            base_queries.append(f'{p.name} {clean_brand} {search_location} linkedin')
        
        yield nodes_qsa

    # 3. Adiciona termos genéricos de sócios como fallback (apenas se não houver sócios no CNPJ)
    # 🆕 OTIMIZAÇÃO: Verifica se algum sócio do QSA já tem LinkedIn para evitar buscas redundantes
    has_partner_with_linkedin = any(p.linkedin_url and "linkedin.com/in/" in p.linkedin_url for p in qsa_partners)
    
    if not has_partner_with_linkedin:
        partner_terms = ["Sócio", "Fundador", "Owner"]
        for p_term in partner_terms:
            query = f'{clean_brand} {p_term} {search_location} linkedin'
            if query not in base_queries:
                base_queries.append(query)
    else:
        print(f"[B2B Engine] Sócio com LinkedIn já identificado. Pulando buscas genéricas de sócios.")
        
    # 4. Gera as queries operacionais depois dos sócios
    for term in selected_terms:
        base_queries.append(f'{clean_brand} {term} {search_location} linkedin')
    
    # 5. Adiciona query focada na empresa para pegar perfis variados (Deep Discovery)
    base_queries.append(f'site:linkedin.com/in/ "{clean_brand}" {search_location}')

    if product_focus:
        from core.external.groq_service import expand_product_to_b2b_terms, evaluate_lead_temperature
        all_terms = await expand_product_to_b2b_terms(product_focus)
        for t in all_terms[:3]:
            # Insere no topo para priorizar o foco de produto
            base_queries.insert(0, f'{temp_brand} {area_focus} {t} linkedin')

    from core.external.groq_service import evaluate_lead_temperature
    from modules.crm.service.pipedrive_service import pipedrive_service

    # 3. SEARCH & PROCESSING LOOP
    razao_social_official = org.name if org else None
    partner_names = [p.name for p in qsa_partners] if qsa_partners else []

    processor = CandidateProcessor(
        temp_brand, 
        domain, 
        area_focus, 
        location, 
        product_focus,
        razao_social=razao_social_official,
        partners=partner_names
    )
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
                
                # Se for o mesmo nome de um sócio já mapeado com LinkedIn, pula a busca CRM deste contato
                if any(is_same_person(p.name, person.get("name")) and p.linkedin_url for p in qsa_partners):
                    print(f"[B2B Engine] Pulando contato CRM '{person.get('name')}' pois já é um sócio mapeado.")
                    continue

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
                
                # NOVO FLUXO: Busca no DuckDuckGo e testa CADA perfil retornado.
                # Se a IA disser que trabalha na empresa (is_valid = True), paramos e usamos este perfil.
                # Se não passar, continuamos até o final. Se não achar, usa perfil dummy.
                real_linkedin = None
                valid_node_data = None
                search_query = f'{name} "{temp_brand}" site:linkedin.com/in/'
                try:
                    search_results = await get_duck_results(search_query, max_results=5)
                    if search_results:
                        for r in search_results:
                            link = r.get("href", "")
                            if "linkedin.com/in/" in link and "pd_" not in link and "pipedrive_" not in link:
                                test_link = link.split("?")[0].rstrip("/")
                                
                                test_res = {
                                    "title": r.get("title", ""),
                                    "body": r.get("body", ""),
                                    "href": test_link
                                }
                                
                                test_processor_res = await processor.process_candidate(test_res, is_partner_search=True)
                                if test_processor_res and test_processor_res.get("main"):
                                    real_linkedin = test_link
                                    valid_node_data = test_processor_res.get("main")
                                    print(f"[B2B Engine] Perfil correto encontrado no LinkedIn para {name}!")
                                    break
                except Exception as e:
                    print(f"[B2B Engine] Erro ao buscar/validar LinkedIn real para {name}: {e}")

                if valid_node_data:
                    node_data = valid_node_data
                else:
                    print(f"[B2B Engine] Nenhum perfil LinkedIn exato validado para {name}, deixando quieto como Contato Pipedrive.")
                    node_data = {
                        "name": name,
                        "role": "Contato no Pipedrive",
                        "level": 5,
                        "department": "Vendas/Pipedrive",
                        "linkedin": f"https://linkedin.com/in/pd_{person.get('id')}",
                        "confidence": 100 
                    }

                node_data["temperature"] = temperature
                node_data["source"] = "Pipedrive"
                
                async with async_session() as session:
                    # Tenta encontrar contato existente pelo pipedrive_id, linkedin_url ou nome fuzzy
                    stmt_pd = select(Employee).where(
                        (Employee.company_id == db_org_id) & 
                        ((Employee.pipedrive_id == str(person.get('id'))) | 
                         (Employee.linkedin_url == f"pipedrive_{person.get('id')}"))
                    )
                    res_pd = await session.execute(stmt_pd)
                    emp = res_pd.scalars().first()
                    
                    if not emp:
                        stmt_all_pd = select(Employee).where(Employee.company_id == db_org_id)
                        res_all_pd = await session.execute(stmt_all_pd)
                        for e in res_all_pd.scalars().all():
                            if is_same_person(e.name, name):
                                emp = e
                                break
                                
                    if emp:
                        emp.pipedrive_id = str(person.get('id'))
                        emp.email = email or emp.email
                        emp.phone = phone or emp.phone
                        emp.temperature = temperature or emp.temperature
                        if emp.role in ["Contato no Pipedrive", None, ""]:
                            emp.role = node_data.get("role", "Contato no Pipedrive")
                            emp.department = node_data.get("department", "Vendas/Pipedrive")
                    else:
                        emp = Employee(
                            name=name,
                            role=node_data.get("role", "Contato no Pipedrive"),
                            department=node_data.get("department", "Vendas/Pipedrive"),
                            seniority=node_data.get("level", 5),
                            email=email,
                            phone=phone,
                            temperature=temperature,
                            company_id=db_org_id,
                            linkedin_url=f"pipedrive_{person.get('id')}",
                            pipedrive_id=str(person.get('id')),
                            source="pipedrive",
                            is_discovery=0
                        )
                        session.add(emp)
                    await session.commit()
                    await session.refresh(emp)
                    node_data["id"] = emp.id
                
                yield [node_data]
        except Exception as e:
            print(f"[B2B Engine/Pipedrive] Erro ao processar pessoas via CRM: {str(e)}")

    # Helper to check if job is cancelled
    async def is_cancelled() -> bool:
        if not job_id:
            return False
        try:
            from arq import create_pool
            from core.infra.redis_config import redis_settings
            redis = await create_pool(redis_settings)
            if await redis.exists(f"job_cancelled_{job_id}") or await redis.exists(f"arq:abort:{job_id}"):
                print(f"[B2B Engine] ⏹️ Cancelamento detectado para o job {job_id}!")
                return True
        except Exception as e:
            # print(f"[B2B Engine] Erro ao verificar cancelamento: {e}")
            pass
        return False

    # 🆕 OTIMIZAÇÃO: Filtra queries que buscam sócios por nome se o sócio já tiver LinkedIn
    filtered_queries = []
    for q in base_queries:
        skip_query = False
        for p in qsa_partners:
            if p.linkedin_url and "linkedin.com/in/" in p.linkedin_url:
                if p.name.lower() in q.lower():
                    skip_query = True
                    break
        if not skip_query:
            filtered_queries.append(q)
    
    base_queries = filtered_queries

    for idx, query in enumerate(base_queries[:15]):
        if await is_cancelled():
            print(f"[B2B Engine] ⏹️ Parando escaneamento devido a cancelamento do job {job_id}.")
            break

        if idx > 0: 
            # 🆕 ELEGÂNCIA: Delay adaptativo menor se a query anterior foi rápida ou falhou por rate limit
            wait_time = random.uniform(15.0, 25.0) 
            print(f"      [B2B Engine] Aguardando {wait_time:.1f}s para a próxima busca...")
            
            slept = 0.0
            while slept < wait_time:
                if await is_cancelled():
                    break
                await asyncio.sleep(1.0)
                slept += 1.0
            
            if await is_cancelled():
                break
        
        log_query_start(query)
        
        # 🆕 ELEGÂNCIA: Tentativa de busca com retry sutil e timeout
        try:
            results = await asyncio.wait_for(get_duck_results(query, max_results=30), timeout=35.0)
        except asyncio.TimeoutError:
            print(f"      [SearchEngine] ⚠️ Timeout na busca DuckDuckGo para: {query[:30]}...")
            continue
        except Exception as e:
            print(f"      [SearchEngine] ⚠️ Erro na busca: {str(e)}")
            # Se for 429, aumenta o próximo delay
            if "429" in str(e):
                await asyncio.sleep(10)
            continue

        if not results: 
            print(f"      [SearchEngine] ⚪ Nenhum resultado encontrado para esta query.")
            continue

        # Identifica se a query atual é uma busca por sócios/fundadores/proprietários
        query_lower = query.lower()
        is_partner_search = (
            "socio" in query_lower or 
            "sócio" in query_lower or 
            "fundador" in query_lower or 
            "owner" in query_lower or 
            any(p.name.lower() in query_lower for p in qsa_partners)
        )

        found_nodes = []
        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            if not href or "linkedin.com/in/" not in href or any(n in href for n in ["/posts/", "/jobs/", "/company/", "/dir/"]) or href in seen_urls:
                continue
            
            # Pula se já estiver rejeitado anteriormente
            if href in rejected_urls:
                print(f"      [B2B Engine] Ignorando candidato previamente REPROVADO (LinkedIn match): {href}")
                continue
            
            name_guess = processor.clean_name_from_title(res.get('title', ''))
            if name_guess and name_guess.lower().strip() in rejected_names:
                print(f"      [B2B Engine] Ignorando candidato previamente REPROVADO (Name match): {name_guess}")
                continue

            seen_urls.add(href)
            
            # Processa o candidato usando o novo módulo (capturando órfãos)
            processor_res = await processor.process_candidate(res, is_partner_search=is_partner_search)
            if not processor_res: continue
            
            node_data = processor_res.get("main")
            orphans = processor_res.get("orphans", [])

            # 1. Persistência do Nó Principal (se existir e for válido)
            if node_data:
                async with async_session() as session:
                    # Tenta match por LinkedIn primeiro
                    stmt_emp = select(Employee).where(Employee.linkedin_url == node_data["linkedin"])
                    res_emp = await session.execute(stmt_emp)
                    existing_emp = res_emp.scalars().first()
                    
                    # Se não achou por LinkedIn, tenta match por NOME fuzzy (para Pipedrive/QSA)
                    if not existing_emp:
                        stmt_all_nodes = select(Employee).where(Employee.company_id == db_org_id)
                        res_all_nodes = await session.execute(stmt_all_nodes)
                        for e in res_all_nodes.scalars().all():
                            if is_same_person(e.name, node_data["name"]):
                                existing_emp = e
                                break

                    if existing_emp:
                        # Atualiza dados (Enriquecimento)
                        existing_emp.name = node_data["name"]
                        existing_emp.role = node_data["role"]
                        existing_emp.department = node_data["department"]
                        existing_emp.seniority = node_data["level"]
                        existing_emp.company_id = db_org_id
                        # Preenche o LinkedIn real se não tinha ou se era dummy do Pipedrive
                        if not existing_emp.linkedin_url or "pipedrive_" in existing_emp.linkedin_url:
                            existing_emp.linkedin_url = node_data["linkedin"]
                        existing_emp.profile_pic = node_data.get("avatar") or existing_emp.profile_pic
                        existing_emp.location = node_data.get("location") or existing_emp.location
                        existing_emp.description = node_data.get("observations") or existing_emp.description
                        existing_emp.education = node_data.get("education") or existing_emp.education
                        existing_emp.matching_score = node_data.get("matching_score") or existing_emp.matching_score
                        existing_emp.evidence = node_data.get("evidence") or existing_emp.evidence
                        existing_emp.headline = node_data.get("headline") or existing_emp.headline
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
                            location=node_data.get("location"),
                            description=node_data.get("observations"),
                            education=node_data.get("education"),
                            matching_score=node_data.get("matching_score"),
                            evidence=node_data.get("evidence"),
                            headline=node_data.get("headline"),
                            company_id=db_org_id
                        )
                        session.add(emp)
                    await session.commit()
                    
                    if not existing_emp:
                        await session.refresh(emp)
                        node_data["id"] = emp.id
                    else:
                        node_data["id"] = existing_emp.id
                
                found_nodes.append(node_data)
                yield [node_data]

            # 2. Promoção e Persistência de Órfãos (Aproveitamento com Repescagem)
            for orphan in orphans:
                # Verifica se já existe no banco (Prioridade: linkedin_url, senão nome+empresa fuzzy)
                async with async_session() as session:
                    existing_o = None
                    if orphan.get("linkedin"):
                        stmt_o = select(Employee).where(Employee.linkedin_url == orphan["linkedin"])
                        res_o = await session.execute(stmt_o)
                        existing_o = res_o.scalars().first()
                    
                    if not existing_o:
                        stmt_all_o = select(Employee).where(Employee.company_id == db_org_id)
                        res_all_o = await session.execute(stmt_all_o)
                        for e in res_all_o.scalars().all():
                            if is_same_person(e.name, orphan["name"]):
                                existing_o = e
                                break
                                
                    if existing_o:
                        continue # Já conhecemos
                
                # Roda a Repescagem para o Órfão (Transforma em nó completo)
                upgraded_node = await processor.upgrade_orphan(orphan)
                
                if upgraded_node:
                    async with async_session() as session:
                        # Segunda verificação pós-upgrade para garantir que não achou um linkedin/nome já cadastrado
                        existing_up = None
                        if upgraded_node.get("linkedin"):
                            check_stmt = select(Employee).where(Employee.linkedin_url == upgraded_node["linkedin"])
                            check_res = await session.execute(check_stmt)
                            existing_up = check_res.scalars().first()
                            
                        if not existing_up:
                            stmt_all_up = select(Employee).where(Employee.company_id == db_org_id)
                            res_all_up = await session.execute(stmt_all_up)
                            for e in res_all_up.scalars().all():
                                if is_same_person(e.name, upgraded_node["name"]):
                                    existing_up = e
                                    break
                                    
                        if existing_up:
                            continue
                            
                        new_emp = Employee(
                            name=upgraded_node["name"],
                            role=upgraded_node["role"],
                            company_id=db_org_id,
                            department=upgraded_node["department"],
                            seniority=upgraded_node["level"],
                            linkedin_url=upgraded_node["linkedin"],
                            email=upgraded_node["email"],
                            profile_pic=upgraded_node.get("avatar"),
                            location=upgraded_node.get("location"),
                            description=upgraded_node.get("observations"),
                            education=upgraded_node.get("education"),
                            matching_score=upgraded_node.get("matching_score"),
                            evidence=upgraded_node.get("evidence"),
                            headline=upgraded_node.get("headline")
                        )
                        session.add(new_emp)
                        await session.commit()
                        
                        await session.refresh(new_emp)
                        upgraded_node["id"] = new_emp.id
                        
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
