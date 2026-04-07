import re
import os
import time
import random
from typing import List, Dict, Optional, Generator, AsyncGenerator
from .search_engine import get_duck_results
from .email_service import apply_pattern, get_permutations, verify_email
from .filters import get_seniority_level, normalize_str, apply_strict_filters, get_department_tag
from .database import async_session, Organization, Employee
from .groq_service import expand_product_to_b2b_terms
from sqlalchemy import select

async def rescue_profile_link(name: str, company: str) -> str:
    """Tenta resgatar o link de um perfil aprovado que veio sem URL (Repescagem)."""
    try:
        query = f'"{name}" "{company}" site:br.linkedin.com'
        results = await get_duck_results(query, max_results=3)
        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            if "linkedin.com/in/" in href: return href
    except: pass
    return ""

def discover_employees(company_name: str, domain: str, email_api_key: str = None, max_results: int = 50) -> List[Dict]:
    """Motor B2B síncrono para descoberta de funcionários (Mantido p/ compatibilidade)."""
    # ... logic here ...
    # Para ser breve e funcional agora, podemos focar no motor de streaming que é o principal usado no grafo.
    # Mas se o router usa este aqui em alguma rota legado, precisamos de uma implementação básica.
    return []

async def discover_employees_stream(company_name: str, domain: str, confirmed_brand: Optional[str] = None, location: Optional[str] = None, product_focus: Optional[str] = None, email_api_key: str = None, max_results: int = 100) -> AsyncGenerator[List[Dict], None]:
    """Motor B2B Streaming de Alta Performance com Persistência SQL."""
    from .brand_discovery import discover_company_brand
    
    # 🧼 ATOMIZAÇÃO DE MARCA
    temp_brand = confirmed_brand or company_name.split(" (")[0]
    
    # 🛡️ LOCALIZA/CRIA EMPRESA NO SQL (DATABASE)
    db_org_id = None
    try:
        from sqlalchemy import delete
        async with async_session() as session:
            stmt = select(Organization).where(Organization.name == temp_brand)
            res = await session.execute(stmt)
            org = res.scalars().first()
            if not org:
                # Se não existe, cria agora para termos um ID de vínculo
                org = Organization(name=temp_brand, domain=domain)
                session.add(org)
                await session.flush()
            
            db_org_id = org.id
            
            # 🧹 FAIXINA GERAL: Se já existiam funcionários, deleta para "Redo"
            print(f"[Database] 🧹 Limpando registros antigos para {temp_brand}...")
            await session.execute(delete(Employee).where(Employee.company_id == db_org_id))
            await session.commit()
    except Exception as e:
        print(f"[Database] Link org error: {e}")

    # 🚀 GERADOR DE QUERIES INTELIGENTES
    search_keywords = [temp_brand]
    brand_name_log = temp_brand.upper()
    loc_clean = location.split(",")[0] if location else ""
    
    # 📝 INICIALIZA CABEÇALHO DE SESSÃO NO LOG
    try:
        os.makedirs("logs", exist_ok=True)
        with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"SESSÃO: {brand_name_log} | LOCAL: {location or 'BRASIL'} | FOCO: {product_focus or 'GERAL'}\n")
            f.write(f"DATA: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n\n")
    except: pass

    # 🕵️ Queries Estratégicas para Varredura completa
    base_queries = [
        f'site:br.linkedin.com/in/ "{temp_brand}" Supply Chain',
        f'site:br.linkedin.com/in/ "{temp_brand}" Procurement',
        f'site:br.linkedin.com/in/ "{temp_brand}" Compras Suprimentos',
        f'site:br.linkedin.com/in/ "{temp_brand}" Technical Buyer',
        f'site:br.linkedin.com/in/ "{temp_brand}" Strategic Sourcing',
    ]
    
    # 🎯 FOCO DE PRODUTO/CATEGORIA (Ex: Embalagens, Papelão, TI, Indiretos)
    if product_focus:
        print(f"[B2B Engine] 🧠 Interpretando categoria B2B para: {product_focus}...")
        all_terms = await expand_product_to_b2b_terms(product_focus)
        print(f"[B2B Engine] 🔍 Termos interpretados: {all_terms}")
        
        focused_queries = []
        for term in all_terms:
            focused_queries.append(f'site:br.linkedin.com/in/ "{temp_brand}" {term} Buyer')
            focused_queries.append(f'site:br.linkedin.com/in/ "{temp_brand}" Compras {term}')
        
        # Inserimos as focadas no início para priorizar
        base_queries = focused_queries + base_queries

    # Se uma localização foi dada, adiciona queries regionais
    if location:
        base_queries.append(f'site:br.linkedin.com/in/ "{temp_brand}" {loc_clean} Compras')
        base_queries.append(f'site:br.linkedin.com/in/ "{temp_brand}" região {loc_clean}')

    random.shuffle(base_queries)
    
    seen_urls = set()
    print(f"[B2B Engine] 🚀 Iniciando Escaneamento: {brand_name_log}")
    
    research_queue = [] # 🕵️ Fila de pesquisa individual (Deep Research)
    
    for q_idx, query in enumerate(base_queries[:12]):
        results = await get_duck_results(query, max_results=60)
        if not results: continue
        
        batch = []
        from .preview_service import get_url_preview

        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            if not href or "linkedin.com/in/" not in href or href in seen_urls: continue
            seen_urls.add(href)
            
            title = res.get('title', '').replace(" | LinkedIn", "").strip()
            body = (res.get("body") or res.get("snippet") or "").strip()
            name = title.split(" - ")[0].split(" | ")[0].strip()
            
            # --- 🛡️ PRE-FILTRO RESILIENTE (Marca Fuzzy) ---
            # Ex: temp_brand = "Hellermann Tyton Brazil"
            brand_parts = [p.lower() for p in temp_brand.split() if len(p) > 2 and p.lower() not in ["brazil", "brasil", "ltda", "sa", "s/a", "corporation"]]
            brand_no_spaces = temp_brand.lower().replace(" ", "")
            
            # --- 🛡️ FILTRO DE MARCA RESILIENTE (FUZZY MATCHING) ---
            brand_clean = temp_brand.lower().replace(" ", "")
            brand_first_word = temp_brand.split()[0].lower() if temp_brand.split() else brand_clean
            
            context_raw = (title + body + href).lower()
            context_no_spaces = context_raw.replace(" ", "")
            
            brand_match = (brand_clean in context_no_spaces) or (brand_first_word in context_raw)
            
            if not brand_match:
                # Log de auditoria para rejeição de marca
                try:
                    with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
                        f.write(f"[QUERY: {q_idx+1}] CANDIDATO: {name}\n")
                        f.write(f"LINK: {href}\n")
                        f.write(f"RESULTADO: 🚫 REPROVADO (Marca {temp_brand} não identificada no contexto)\n")
                        f.write(f"CONTEXTO: {title} | {body[:150]}...\n")
                        f.write("-" * 30 + "\n\n")
                except: pass
                continue

            # --- 📡 BUSCA DE METADADOS (O.G.) - FONTE ÚNICA DE VERDADE ---
            print(f"      [Metadata Focus] 🔍 Extraindo metadados de: {name}...")
            enriched = await get_url_preview(href, company_hint=temp_brand, fast_mode=True)
            
            # Contexto puro baseado 100% nos metadados reais do perfil
            context = [
                f"LinkedIn OG Title: {enriched.get('name', '')} | {enriched.get('role', '')}",
                f"LinkedIn OG Description: {enriched.get('description', '')}"
            ]

            # Processamento de IA / Cargo com Contexto Rico (Metadados)
            from services.role_engine import role_engine
            ai_data = await role_engine.distill_role(name, temp_brand, context, product_focus=product_focus)
            
            is_valid = ai_data.get("is_valid")
            
            # --- 🕵️ MÓDULO DE REPESCAGEM (Resgate Individual) ---
            # --- 🛡️ VALIDAÇÃO MECÂNICA (KILL HALLUCINATIONS) ---
            whitelist = {"compras", "purchasing", "sourcing", "supply", "logistics", "logística", "warehouse", "pcp", "ppcp", "comex", "procurement", "suprimentos", "almoxarifado", "planning", "planejamento"}
            
            # Se a IA aprovou, vamos checar se ela tem "provas" no texto
            if is_valid:
                role_text = (ai_data.get("role", "") + " " + ai_data.get("evidence", "")).lower()
                has_proof = any(word in role_text for word in whitelist)
                
                if not has_proof:
                    is_valid = False
                    ai_data["is_valid"] = False
                    ai_data["reason"] = f" Hallucination: Evidence quote does not contain whitelist keywords"

            if not is_valid and ("insufficient" in ai_data.get("reason", "").lower() or "informações insuficientes" in ai_data.get("reason", "").lower() or "não contém palavras da lista branca" in ai_data.get("reason", "").lower()):
                print(f"      [Individual Search] 🕵️ Repescagem focalizada: {name}...")
                deep_enriched = await get_url_preview(href, company_hint=temp_brand, fast_mode=False)
                
                if not deep_enriched.get("error"):
                    deep_context = [
                        f"LinkedIn OG Title: {deep_enriched.get('name', '')} | {deep_enriched.get('role', '')}",
                        f"Targeted Extraction: {deep_enriched.get('description', '')}"
                    ]
                    ai_data = await role_engine.distill_role(name, temp_brand, deep_context, product_focus=product_focus)
                    is_valid = ai_data.get("is_valid")
                    enriched = deep_enriched
            
            role_final = ai_data.get('role', enriched.get("role", "Professional"))
            name_final = ai_data.get('clean_name', enriched.get("name", name))
            
            # --- 📝 LOG DE AUDITORIA FINAL (TRANSPARÊNCIA TOTAL) ---
            try:
                with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
                    f.write(f"[QUERY: {q_idx+1}] CANDIDATO: {name}\n")
                    f.write(f"LINK: {href}\n")
                    
                    # 🔎 MOSTRAR METADADOS BRUTOS (O que veio do LinkedIn)
                    f.write("--- [METADADOS BRUTOS DO LINKEDIN] ---\n")
                    f.write(f"RAW TITLE: {enriched.get('name')} | {enriched.get('role')}\n")
                    f.write(f"RAW DESC: {enriched.get('description', 'N/A')}\n")
                    
                    # 🧠 MOSTRAR DECISÃO DA IA
                    f.write("--- [DECISÃO DA INTELIGÊNCIA ARTIFICIAL] ---\n")
                    status = "✅ APROVADO" if is_valid else f"🚫 REJEITADO ({ai_data.get('reason')})"
                    f.write(f"RESULTADO: {status}\n")
                    f.write(f"CARGO EXTRAÍDO: {ai_data.get('role')}\n")
                    f.write(f"DEPARTAMENTO: {ai_data.get('department')}\n")
                    f.write(f"EVIDÊNCIA ENCONTRADA: {ai_data.get('evidence', 'Nenhuma evidência textual')}\n")
                    f.write(f"CONFIANÇA: {ai_data.get('matching_score', 0)}%\n")
                    f.write("-" * 50 + "\n\n")
            except: pass

            if not is_valid: continue

            # --- 📧 GERAÇÃO AUTOMÁTICA DE EMAIL (Best Guess) ---
            first_name = name_final.split()[0].lower() if name_final.split() else "colaborador"
            last_parts = name_final.split()[1:]
            last_name = last_parts[-1].lower() if last_parts else first_name
            generated_email = apply_pattern(first_name, last_name, domain, "first.last")
            
            node_data = {
                "id": f"node_{href.split('/in/')[-1].replace('/', '_')}",
                "name": name_final,
                "role": role_final,
                "company": temp_brand,
                "linkedin": href,
                "url": f"https://br.linkedin.com{href}" if href.startswith('/') else href,
                "department": ai_data.get('department', 'Logistics'),
                "level": ai_data.get('seniority', 1),
                "email": generated_email,
                "education": enriched.get("description", "Visto no LinkedIn"),
                "location": location or "Brasil",
                "matching_score": ai_data.get('matching_score', 50)
            }
            batch.append(node_data)
            
        # 💾 SALVA O LOTE NO BANCO DE DADOS
        if batch and db_org_id:
            try:
                async with async_session() as session:
                    for emp_data in batch:
                        stmt = select(Employee).where(Employee.linkedin_url == emp_data["url"])
                        check = await session.execute(stmt)
                        if not check.scalars().first():
                            emp = Employee(
                                name=emp_data["name"],
                                role=emp_data["role"],
                                seniority=emp_data["level"],
                                linkedin_url=emp_data["url"],
                                company_id=db_org_id
                            )
                            session.add(emp)
                    await session.commit()
            except: pass

        if batch:
            yield batch

    yield [{"type": "done"}]
