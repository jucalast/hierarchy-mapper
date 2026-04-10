import re
import html
import random
import unicodedata
import os
import time
import json
import asyncio
from typing import List, Dict, Optional, Generator, AsyncGenerator
import httpx

def simplify_text(text: str) -> str:
    if not text: return ""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

from services.hierarchy.filters import get_seniority_level, get_department_tag

def clean_extracted_role(role: str, name: str, company: str) -> str:
    """Limpeza ultra-agressiva de cargos para remover boilerplate de SEO e ruído do LinkedIn."""
    if not role: return "Professional"
    
    # 0. Split CamelCase & Names (Ex: "ManagerFelipe" -> "Manager Felipe")
    # Tenta separar quando uma minúscula encosta numa maiúscula
    r = re.sub(r'([a-z])([A-Z])', r'\1 \2', role)
    # Tenta separar quando um nome próprio (Maiúscula + minúsculas) encosta no fim de uma palavra
    r = re.sub(r'([a-z]{3,})([A-Z][a-z]+)', r'\1 \2', r)
    
    # 1. Resolve entidades HTML e remove o próprio nome/empresa
    r = html.unescape(r).replace(name, "").replace(company, "").strip()
    
    # 2. Lista de padrões de "Lixo Radioativo" (Boilerplate de SEO)
    junk_patterns = [
        r"^.*?\.\.\.\s*",                # Início com reticências
        r"veja o perfil de .*? no LinkedIn",
        r"profissional com .*? de experiência",
        r"experiência:.*",
        r"procurando novas oportunidades",
        r"Currently works at",
        r"atualmente atuando como",
        r"pode apresentar você a mais de \d+ pessoas",
        r"conexões no linkedin",
        r"visualizar perfil",
        r"entre para ver",
        r"brasil\.?\s*[A-Z][a-z]+.*", 
        r"law no\.?\s*\d+.*",           
        r".*procurement\s*law.*",
        r".*imagem de company.*",
        r"conheça o perfil",
        r"trajetória no setor",
        r"\d+ conexões",
        r"community of 1 billion members"
    ]
    
    for p in junk_patterns:
        r = re.sub(p, "", r, flags=re.IGNORECASE).strip()
    
    # 3. Limpeza de prefixos/sufixos comuns (na, no, at, @)
    r = re.sub(r"\s+(na|no|da|do|at|in|of|@|na empresa|pela)\s+.*$", "", r, flags=re.IGNORECASE)
    


    # 5. Limpeza de caracteres especiais residuais
    r = re.sub(r'^[·\-\|\.]\s*', '', r)
    r = re.sub(r'\s*[·\-\|\.]$', '', r)
    
    return r.strip().title() or "Professional"
from typing import List, Dict, Optional, Generator, AsyncGenerator
from services.hierarchy.search_engine import get_duck_results
from services.external.email_service import apply_pattern, get_permutations, verify_email
from services.hierarchy.filters import get_seniority_level, normalize_str, apply_strict_filters, get_department_tag
from core.database import async_session
from models import Organization, Employee
from services.external.groq_service import expand_product_to_b2b_terms
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
    """Motor B2B Streaming de Alta Performance com Persistência SQL."""
    from services.intelligence.brand_discovery import discover_company_brand
    
    # 🧼 ATOMIZAÇÃO DE MARCA
    temp_brand = confirmed_brand or company_name.split(" (")[0]
    
    # 🛡️ LOCALIZA/CRIA EMPRESA NO SQL (DATABASE)
    db_org_id = None
    try:
        from sqlalchemy import delete
        async with async_session() as session:
            # Tenta achar por CNPJ, depois por Nome
            org = None
            norm_cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "") if cnpj else None
            
            if norm_cnpj:
                stmt_cnpj = select(Organization).where(Organization.cnpj == norm_cnpj)
                res_cnpj = await session.execute(stmt_cnpj)
                org = res_cnpj.scalars().first()
            
            if not org:
                from sqlalchemy import func
                stmt_name = select(Organization).where(func.lower(Organization.name) == temp_brand.lower())
                res_name = await session.execute(stmt_name)
                org = res_name.scalars().first()
                
            if not org:
                org = Organization(name=temp_brand, domain=domain, cnpj=norm_cnpj)
                session.add(org)
                await session.flush()
            else:
                # Atualiza com o CNPJ que veio agora se ele estava vazio
                if norm_cnpj and not org.cnpj:
                    org.cnpj = norm_cnpj
                if domain and not org.domain:
                    org.domain = domain
            
            db_org_id = org.id
            
            # 🧹 FAIXINA GERAL: Se já existiam funcionários, deleta para "Redo"
            # EXCEÇÃO: Preservar Quadro Societário (QSA) e Inteligência base
            from sqlalchemy import or_
            print(f"[Database] 🧹 Limpando registros antigos para {temp_brand}...")
            await session.execute(
                delete(Employee).where(
                    Employee.company_id == db_org_id,
                    or_(
                        Employee.department != "Quadro de Sócios (QSA)",
                        Employee.department == None
                    )
                )
            )
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

    # 🕵️ Queries Estratégicas para Varredura (PADRÃO HUMANO - Evita 429)
    if area_focus == "logistica":
        print(f"[B2B Engine] 🚚 Foco em ÁREA: LOGÍSTICA")
        base_queries = [
            f'"{temp_brand}" Logística linkedin',
            f'"{temp_brand}" "Supply Chain" linkedin',
            f'"{temp_brand}" PCP Planejamento linkedin',
            f'"{temp_brand}" Gerente Logística linkedin',
            f'"{temp_brand}" Diretor Logística linkedin',
            f'"{temp_brand}" Expedição linkedin',
        ]
    else:
        print(f"[B2B Engine] 🛒 Foco em ÁREA: COMPRAS")
        base_queries = [
            f'"{temp_brand}" Comprador linkedin',
            f'"{temp_brand}" "Analista de Compras" linkedin',
            f'"{temp_brand}" "Procurement" linkedin',
            f'"{temp_brand}" "Sourcing" linkedin',
            f'"{temp_brand}" Gerente Compras linkedin',
            f'"{temp_brand}" Coordenador Compras linkedin',
            f'"{temp_brand}" Diretor Compras linkedin',
            f'"{temp_brand}" "Suprimentos" linkedin',
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
    if product_focus:
        # --- 🔍 ENGENHARIA DE BUSCA AVANÇADA (Combinando Critérios) ---
        loc_clean = location.split(",")[0].strip() if location else ""
        area_terms = ["compras", "purchasing", "sourcing", "suprimentos", "supply chain", "buyer", "procurement"]
        cat_terms = all_terms[:3] # Pega os 3 termos principais interpretados (ex: Packaging, Embalagens)

        base_queries = []
        
        # 1. Busca Ultra-Focada (Marca + Área + Categoria) - PADRÃO HUMANO
        for t in cat_terms:
            base_queries.append(f'"{temp_brand}" "{area_focus}" "{t}" linkedin')
            base_queries.append(f'"{temp_brand}" "purchasing" "{t}" linkedin')

        # 2. Busca Regional (Marca + Área + Localidade)
        if loc_clean:
            for a in area_terms:
                base_queries.append(f'"{temp_brand}" {a} "{loc_clean}" linkedin')
            
        # 3. Busca de Senioridade/Cargos Específicos
        base_queries.append(f'"{temp_brand}" "Gerente de Compras" "{loc_clean}" linkedin')
        base_queries.append(f'"{temp_brand}" "Strategic Sourcing" "{loc_clean}" linkedin')

        # Limpeza e Shuffle
        base_queries = list(set([q.replace('  ', ' ').strip() for q in base_queries]))
        random.shuffle(base_queries)

    print(f"[B2B Engine] 🚀 Iniciando Escaneamento: {brand_name_log}")
    
    # 🕵️ CHECAGEM PROATIVA DE IA
    from services.hierarchy.role_engine import role_engine
    await role_engine.proactive_health_check()
    
    repescagem_queue = [] # 🕵️ Fila de pesquisa individual (Deep Research)

    
    seen_urls = set()
    for q_idx, query in enumerate(base_queries[:12]):
        try:
            with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
                f.write(f"\n{'='*30}\n")
                f.write(f"🔍 NOVA CONSULTA: {query}\n")
                f.write(f"{'='*30}\n\n")
        except: pass

        # ⏳ Pausa para evitar detecção (Simula ritmo humano)
        if q_idx > 0:
            delay = random.uniform(6.0, 10.0)
            print(f"      [B2B Engine] 💤 Aguardando {delay:.2f}s para próxima consulta...")
            await asyncio.sleep(delay)

        results = await get_duck_results(query, max_results=60)
        print(f"      [Debug] Search results for '{query}': {len(results)} found")
        if not results: continue
        
        batch = []
        from services.intelligence.preview_service import get_url_preview
        
        candidates_pool = []
        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            title = res.get('title', '').strip()
            print(f"      [Debug] Processing: {title} | {href}")
            
            # 🛡️ BLINDAGEM AGRESSIVA: Filtra ruídos comuns de buscas "Humanas"
            is_valid_profile = "linkedin.com/in/" in href
            is_noise = any(noise in href for noise in ["/posts/", "/jobs/", "/company/", "/dir/", "/pub/"])
            
            if not href or not is_valid_profile or is_noise:
                print(f"      [Debug] SKIP: Noise or non-profile link detected ({href})")
                continue
            
            if href in seen_urls:
                print(f"      [Debug] SKIP: Already seen URL")
                continue
            
            seen_urls.add(href)
            body = (res.get("body") or res.get("snippet") or "").strip()

            # --- 🧼 LIMPEZA DE NOME (ULTRA AGRESSIVA) ---
            # Remove "| LinkedIn" e outros artefatos comuns
            t_clean = title.replace(" | LinkedIn", "").replace("| LinkedIn", "").strip()
            
            # Split por qualquer delimitador comum (traços, barras, pontos médios) 
            parts = re.split(r'[\|\-\–\—•]', t_clean)
            name_guess = parts[0].strip()
            
            # Se colou com a empresa (ex: NomeKnorrBremse), removemos a marca
            # Se for uma marca curta (< 6 letras), somos menos agressivos no split para evitar apagar o nome
            if len(temp_brand) > 5:
                name_final = re.split(fr"\s*{re.escape(temp_brand)}", name_guess, flags=re.I)[0].strip()
            else:
                name_final = name_guess
            
            name_final = name_final.split('...')[0].strip()
            
            # Validação: se o nome for a própria empresa ou lixo, ignoramos
            if len(name_final) < 3 or name_final.lower() == temp_brand.lower() or "linkedin" in name_final.lower():
                print(f"      [Debug] SKIP: Invalid name_final '{name_final}' for brand '{temp_brand}'")
                continue
            
            name = name_final # Variável usada no restante do loop
            
            theorg_info = ""
            theorg_role = "Não Encontrado"
            theorg_url = "N/A"
            
            # --- 🕵️ HUNT MULTI-SLUG (THE ORG) ---
            # Tentamos variações para bater com o banco do The Org
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Usamos um User-Agent real para evitar bloqueio 403
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                    }
                    
                    t_brand = simplify_text(temp_brand).lower().replace(" ", "-")
                    base_name = simplify_text(name).lower().replace(".", "").strip()
                    name_parts = [p for p in base_name.split() if len(p) > 1 or p.isalpha()]
                    
                    # Variações: [nome-completo, nome-sobrenome, nome-primeiro-segundo, nome-segundo-último]
                    slugs = [
                        "-".join(name_parts),
                        f"{name_parts[0]}-{name_parts[-1]}" if len(name_parts) > 1 else name_parts[0],
                    ]
                    if len(name_parts) > 2:
                        slugs.append(f"{name_parts[0]}-{name_parts[1]}")
                        slugs.append(f"{name_parts[1]}-{name_parts[-1]}")
                        slugs.append(f"{name_parts[0]}-{name_parts[1]}-{name_parts[-1]}")
                    
                    for s in list(set(slugs)):
                        check_url = f"https://theorg.com/org/{t_brand}/org-chart/{s}"
                        try:
                            resp = await client.get(check_url, follow_redirects=True, timeout=5.0, headers=headers)
                            final_url = str(resp.url).lower()
                            
                            # SEGURANÇA MÁXIMA: O nome precisa estar NO TÍTULO principal (não na sidebar)
                            # e o primeiro nome precisa estar no final da URL
                            candidate_first_name = name_parts[0].lower()
                            # Extrai apenas o conteúdo da tag <title> para checagem base
                            page_title_match = re.search(r'<title>(.*?)</title>', resp.text, re.I | re.S)
                            raw_title = html.unescape(page_title_match.group(1)) if page_title_match else ""
                            page_title_low = raw_title.lower()
                            final_slug = final_url.split('/')[-1]
                            
                            if resp.status_code == 200 and (candidate_first_name in final_slug) and (candidate_first_name in page_title_low):
                                theorg_url = str(resp.url)
                                theorg_info = f" [HIERARCHY CONFIRMED]: Profile officially listed on The Org"
                                
                                # Extração de Cargo Real baseada no test_universal_theorg.py
                                role = "Confirmed Profile"
                                # Prioridade 1: og:title
                                title_match = re.search(r'property="og:title" content="[^"-]*-\s*([^|@"]*)\s', resp.text, re.I)
                                if not title_match:
                                    # Prioridade 2: tag <title>
                                    title_match = re.search(fr"<title>[^<]*{re.escape(name_parts[0])}[^<]*-\s*([^|@<]*)\s+", resp.text, re.I)
                                
                                if title_match:
                                    role = title_match.group(1).strip()
                                    role = html.unescape(role)
                                    role = re.sub(fr'\s+(at|na|da|in|of|@)\s+.*', '', role, flags=re.IGNORECASE)
                                    # Remove nome ou marca do cargo por segurança
                                    role = re.sub(re.escape(name), "", role, flags=re.IGNORECASE).strip()
                                    for part in temp_brand.split("-") + [temp_brand]:
                                        if len(part) > 2:
                                            role = re.sub(re.escape(part), "", role, flags=re.IGNORECASE).strip()
                                    role = role.strip(" -—|")
                                    
                                    if len(role) >= 3 and role.lower() not in temp_brand.lower():
                                        role = role.title()
                                    else:
                                        role = "Confirmed Profile"
                                    
                                theorg_role = role
                                
                                print(f"      [The Org] ✅ Sucesso real para {name}: {theorg_role}")
                                break
                            else:
                                if resp.status_code != 404:
                                    print(f"      [The Org] ❌ Falha para {s}: Status {resp.status_code}. Nome: {candidate_first_name} | Slug final: {final_slug}")
                        except Exception as e:
                            print(f"      [The Org] ⚠️ Exceção para {s}: {e}")
                            continue
            except Exception as e:
                # print(f"DEBUG The Org Error: {e}")
                pass

            # --- Extração de Metadados (Metadata Focus) ---
            print(f"      [Metadata Focus] 🔍 Extraindo: {name}...")
            await asyncio.sleep(0.4) # ⏳ Faster delay but still staggered
            enriched = await get_url_preview(href, company_hint=temp_brand, fast_mode=True)
            
            # Adicionamos o The Org ao contexto que a IA vai ler depois
            context = [
                f"Google Title: {title}",
                f"LinkedIn Snippet: {body}",
                f"OG Data: {enriched.get('role', '')} | {enriched.get('description', '')}",
                f"Official Org Chart: {theorg_info} | Official Role: {theorg_role}"
            ]
            
            # 1. 🔍 EXTRAÇÃO IMEDIATA DE METADADOS (Transparência Total)
            meta_desc = enriched.get('description', '')
            meta_title = f"{enriched.get('name', '')} | {enriched.get('role', '')}"
            
            # 🛡️ NORMALIZAÇÃO PARA MATCHING (A&S -> AS ou ASTechnologies)
            def slugify_lenient(text: str) -> str:
                return re.sub(r'[^a-z0-9]', '', text.lower())
            
            brand_slug = slugify_lenient(temp_brand)
            # Pega termos significativos (ex: A&S Technologies -> as, technologies)
            brand_words = [slugify_lenient(w) for w in temp_brand.replace('&', ' ').replace('-', ' ').split() if len(slugify_lenient(w)) >= 2]
            
            # Buscamos a marca no snippet (DDG) E no Metadata (LinkedIn)
            search_context = title + body + href
            meta_context = (enriched.get('role', '') or '') + (enriched.get('description', '') or '')
            full_context_slug = slugify_lenient(search_context + meta_context)
            
            theorg_found = "HIERARCHY CONFIRMED" in (theorg_info or "")
            # Match se qualquer palavra significativa da marca estiver presente ou se o slug completo bater
            brand_match = (brand_slug in full_context_slug) or any(w in full_context_slug for w in brand_words)
            
            # 🛡️ TRAVA DE ÂNCORA DE EMPRESA (Evita Ex-Funcionários e Erros de Marca)
            is_wrong_company = False
            if not theorg_found:
                meta_role = (enriched.get('role', '') or '').lower()
                
                # Só marcamos como ERRO se aparecer o nome de OUTRA empresa clara no headline
                # e nossa marca NÃO estiver lá.
                other_known_signals = ["at ", "na ", "no ", "trabalha em ", "works at "]
                has_at_signal = any(sig in meta_role for sig in other_known_signals)
                
                if has_at_signal:
                    # Se ele diz que trabalha "na Empresa X" e nossa marca não aparece no headline
                    if not any(w in meta_role for w in brand_words) and brand_slug not in meta_role:
                        is_wrong_company = True
            
            if (not theorg_found and not brand_match) or is_wrong_company: 
                print(f"      [Debug] SKIP: {'Company Mismatch' if is_wrong_company else 'Brand not found'}")
                try:
                    with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
                        f.write(f"[ÂNCORA DE EMPRESA] CANDIDATO: {name} | LINK: {href}\n")
                        f.write(f"MOTIVO: 🚫 {'Mismatch' if is_wrong_company else 'Brand not found'} (Role: {enriched.get('role')} | Target: {temp_brand})\n")
                        f.write("-" * 50 + "\n\n")
                except: pass
                continue
            
            
            # 3. 🛡️ FILTRAGEM MECÂNICA (Whitelist Ampliada)
            from .filters import apply_strict_filters
            filter_context = f"{title} {body} {meta_desc}"
            if not theorg_found and not apply_strict_filters(name, title, filter_context, company_name, temp_brand, location):
                try:
                    with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
                        f.write(f"[FILTRO MECÂNICO] CANDIDATO: {name}\n")
                        f.write(f"LINK: {href}\n")
                        f.write(f"--- [METADADOS BRUTOS] ---\n")
                        f.write(f"GOOGLE TITLE: {title}\n")
                        f.write(f"GOOGLE DESC: {body}\n")
                        f.write(f"LINKEDIN OG: {meta_title} | {meta_desc}\n")
                        f.write(f"MOTIVO: 🚫 Rejeitado Automaticamente (Sem palavra positiva)\n")
                        f.write("-" * 50 + "\n\n")
                except: pass
                continue

            # 4. 🧠 PREPARAÇÃO PARA IA (Super Contexto Inviolável)
            # Já temos o 'context' rico definido no início do loop (Linha 213).
            # Vamos apenas garantir que ele inclua o título de metadados se for diferente.
            if meta_title not in context[0]:
                context.append(f"Additional Metadata: {meta_title}")

            candidates_pool.append({
                "idx": len(candidates_pool),
                "name": name,
                "company": temp_brand,
                "context": context,
                "href": href,
                "title": title,
                "body": body,
                "enriched": enriched,
                "product_focus": product_focus,
                "theorg_role": theorg_role,
                "theorg_info": theorg_info,
                "theorg_url": theorg_url
            })

        if not candidates_pool: continue

        # --- 🧊 PROCESSAMENTO DE IA EM LOTE (BATCHING) ---
        from services.hierarchy.role_engine import role_engine
        batch_ai_results = await role_engine.distill_roles_batch(candidates_pool, temp_brand, product_focus, area_focus=area_focus)

        for c in candidates_pool:
            deep_context = None # ✅ LIMPEZA DE MEMÓRIA (Evita vazamento de dados entre candidatos)
            idx = c["idx"]
            name = c["name"]
            href = c["href"]
            title = c["title"]
            body = c["body"]
            enriched = c["enriched"]
            context = c["context"]
            theorg_role = c["theorg_role"]
            theorg_info = c["theorg_info"]
            theorg_url = c["theorg_url"]
            
            ai_data = batch_ai_results.get(idx)
            if not ai_data:
                ai_data = { "clean_name": name, "role": "Professional", "is_valid": False, "reason": "No AI response", "seniority": 2, "matching_score": 0 }
                
            is_valid = ai_data.get("is_valid", False)
            matching_score = ai_data.get("matching_score", 0)

            # --- 🛡️ VALIDAÇÃO DE INTELIGÊNCIA ---
            # Stricter check on confidence - relax if from The Org
            if is_valid and matching_score < 40 and not theorg_found:
                is_valid = False
                ai_data["is_valid"] = False
                ai_data["reason"] = f"Low Confidence ({matching_score}%)"

            role_extracted = str(ai_data.get("role", "")).lower()
            
            # --- 🛡️ SALVAGUARDA SEMÂNTICA (FILTRO FINAL) ---
            final_blacklist = {"vendas", "sales", "marketing", "rh", "hr", "finance", "accounting", "contabilidade", "ti", "it", "produção", "production", "qualidade", "quality", "manutenção", "maintenance", "jurídico", "legal", "facilities", "fpa", "fp&a"}
            if is_valid and any(bad in role_extracted for bad in final_blacklist):
                is_valid = False
                ai_data["is_valid"] = False
                ai_data["reason"] = f"Semantic Rejection: Role '{role_extracted}' belongs to blacklisted department"

            # --- 🕵️ MÓDULO DE REPESCAGEM IMEDIATA (Deep Research) ---
            reason_lower = str(ai_data.get("reason", "")).upper()
            
            # 🚨 TRIGGER REFORÇADO: 
            # 1. Se a IA disse que não é válido por falta de info ou confiança baixa.
            # 2. Se a IA aprovou mas o cargo é GENÉRICO (Professional, Employee, etc).
            # 3. Se a IA aprovou mas a confiança não é TOTAL (< 90%).
            is_generic = any(g in role_extracted for g in ["professional", "employee", "não identificado", "b2b profile", temp_brand.lower()])
            
            needs_repescagem = (not is_valid and any(k in reason_lower for k in [
                "INSUFFICIENT", "UNCERTAIN", "GENERIC", "WHITELIST", "NOT FOUND", "LOW CONFIDENCE", "NO AI RESPONSE"
            ])) or (is_valid and (is_generic or matching_score < 90))
            
            if needs_repescagem:
                # Limpa a URL de sufixos de idioma para evitar dados obsoletos
                href = re.sub(r'/(en|pt|es|fr|de|it|br)/?$', '', href.rstrip('/'))
                
                search_title = f"{title} | {body}"
                print(f"      [Individual Search] 🕵️ Pesquisando especificamente por: {name} na {temp_brand}...")
                
                # 1. 🔍 BUSCA DEDICADA POR NOME (Evita ruído de buscas amplas)
                individual_query = f'"{name}" "{temp_brand}" site:br.linkedin.com'
                individual_results = await get_duck_results(individual_query, max_results=3)
                
                dedicated_context = ""
                mechanical_title = "Não Identificado"
                
                if individual_results:
                    # Pegamos o primeiro resultado que parece ser o perfil correto
                    for ir in individual_results:
                        ir_href = ir.get("href", "").split("?")[0].rstrip("/")
                        if href in ir_href or ir_href in href: # É a mesma pessoa
                            dedicated_context = f"DEDICATED SEARCH RESULT: {ir.get('title')} | {ir.get('body')}"
                            # Extração mecânica pura do título do Google (Fidelidade Máxima)
                            # Suporta formatos: Nome - Cargo, Nome | Cargo, Nome : Cargo
                            t = ir.get('title', '')
                            # Limpa sufixos do LinkedIn
                            t = re.sub(r' \| LinkedIn$', '', t, flags=re.I)
                            t = re.sub(r' - LinkedIn$', '', t, flags=re.I)
                            
                            separators = [r' - ', r' \| ', r' : ']
                            for sep in separators:
                                p = re.split(sep, t)
                                if len(p) > 1:
                                    potential = p[1].split(' | ')[0].strip()
                                    if len(potential) > 3: 
                                        # Se o que achamos for o nome da empresa, ignoramos como cargo
                                        if slugify_lenient(potential) not in [slugify_lenient(temp_brand)]:
                                            mechanical_title = potential
                                            break
                            
                            # 🧪 REPESCAGEM POR SNIPPET (Se o título falhou)
                            if mechanical_title == "Não Identificado":
                                # Procura padrões como "atualmente atuo como X", "sou Y na empresa", etc.
                                bio_lower = ir.get('body', '').lower()
                                patterns = [
                                    r"(?:atualmente |hoje |sou |atuo como )([^.!,·]*?)(?: na | da | em | na empresa|!|\.|\,)",
                                    r"([^.!,·]*?)\s+(?:comprador|compradora|gerente|analista|assistente|diretor|coordenador|supervisor|estagiário)"
                                ]
                                for pat in patterns:
                                    m = re.search(pat, bio_lower)
                                    if m:
                                        role_candidate = m.group(0).strip(" .!,")
                                        if len(role_candidate) > 4 and len(role_candidate) < 50:
                                            mechanical_title = role_candidate.title()
                                            break
                            break

                try:
                    with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
                        f.write(f"[REPESCAGEM IMEDIATA] CANDIDATO: {name}\n")
                        f.write(f"LINK: {href}\n")
                        f.write(f"--- [MOTIVO] ---\n")
                        f.write(f"Iniciando busca individual devido a: {ai_data.get('reason')}\n")
                        if dedicated_context:
                            f.write(f"--- [GOOGLE DEDICADO] ---\n")
                            f.write(f"{dedicated_context}\n")
                            f.write(f"CARGO EXTRAÍDO MECANICAMENTE: {mechanical_title}\n")
                        f.write("-" * 50 + "\n\n")
                except: pass

                # 2. Raspagem de Metadados (Fallback/Enriquecimento)
                deep_enriched = await get_url_preview(href, company_hint=temp_brand, fast_mode=False) 
                
                # 💡 Unificamos a Busca Dedicada + LinkedIn + The Org
                deep_context = [
                    f"Individual Search Insight: {dedicated_context if dedicated_context else search_title}",
                    f"LinkedIn Status: {deep_enriched.get('name', '')} | {deep_enriched.get('role', '')}",
                    # 🧹 Limpeza de ruído institucional do LinkedIn para não confundir a IA
                    f"LinkedIn Bio: {re.sub(r'veja o perfil de .* no linkedin, uma comunidade profissional de.*', '', str(deep_enriched.get('description', '')), flags=re.I).strip()}",
                    f"Hierarchy Data: {theorg_info} | Official Role: {theorg_role}",
                    f"CRITICAL HINT: Use as primary evidence if valid: '{mechanical_title}'" if mechanical_title != "Não Identificado" else "HINT: Deduce the specific role from the 'atuo como' or experience sentences."
                ]
                
                print(f"      [IA Context] 🧠 Analisando {name} focando no cargo extraído: {mechanical_title}...")

                # Destilação Individual (Enviamos o cargo mecânico como pista prioritária)
                ai_data = await role_engine.distill_role(name, temp_brand, deep_context, product_focus=product_focus, area_focus=area_focus)
                
                # SE a IA tentou mudar um cargo mecânico forte por um ruído genérico, restauramos
                if mechanical_title != "Não Identificado" and ai_data.get("is_valid"):
                    ai_role = str(ai_data.get("role", "")).lower()
                    generic_labels = ["professional", "employee", "pioneer", "profile", "member", "não identificado", "unidentified"]
                    
                    # Se o título extraído mecanicamente for bom e a IA deu algo genérico
                    is_ai_generic = any(g == ai_role.strip() for g in generic_labels)
                    if is_ai_generic or (len(ai_role) < 4 and len(mechanical_title) > 5):
                        print(f"      [Fidelity Guard] 🛡️ Restaurando cargo real '{mechanical_title}' (IA deu '{ai_data.get('role')}')")
                        ai_data["role"] = mechanical_title

                # 🛡️ HEURÍSTICA DE RESSURREIÇÃO (Se a IA falhou mas os dados brutos são claros)
                extracted_role_low = str(deep_enriched.get("role", "")).lower()
                extracted_bio_low = str(deep_enriched.get("description", "")).lower()
                ground_truth_narrow = (extracted_role_low + " " + (theorg_role or "").lower() + " " + mechanical_title.lower()).strip()
                ground_truth_wide = (dedicated_context + " " + extracted_role_low + " " + extracted_bio_low + " " + (theorg_role or "").lower()).lower()
                
                whitelist = ["buyer", "comprador", "compras", "purchasing", "suprimentos", "supply", "procurement", "sourcing", "strategic", "logistic", "logistica", "pcp", "expedição", "estoque", "warehouse", "comex", "trade", "negociação"]
                
                # REGRAS DE RESSURREIÇÃO REFORÇADAS:
                # 1. Prova forte no cargo real ou The Org
                has_hard_proof = any(w in ground_truth_narrow for w in whitelist)
                # 2. Prova no contexto amplo, mas sem ser post de vaga
                is_recruitment_post = any(x in ground_truth_wide for x in ["temosvaga", "vaga para", "recrutamos", "contratando", "oportunidade para"])
                has_soft_proof = any(w in ground_truth_wide for w in whitelist) and not is_recruitment_post
                
                # 3. Bloqueio de Vendedor (Vendedor NUNCA é Compras)
                is_seller = any(s in ground_truth_wide for s in ["vendedor", "sales", "comercial", "representante"]) and "comprador" not in ground_truth_narrow

                has_proof = (has_hard_proof or has_soft_proof) and not is_seller
                
                is_valid = ai_data.get("is_valid", False)
                trust_score = ai_data.get('matching_score', 0)

                # Se encontramos prova no Google/TheOrg mas a IA se confundiu, nós resgatamos!
                if has_proof and not is_valid:
                    print(f"      [Heuristic Recovery] 🚀 Resgatando {name} via Ground Truth (Google/TheOrg)!")
                    is_valid = True
                    ai_data["is_valid"] = True
                    ai_data["reason"] = "Role confirmed via Ground Truth (Role/TheOrg Keywords)"
                    ai_data["matching_score"] = 95
                    if not ai_data.get("department"): ai_data["department"] = area_focus.upper()
                    if mechanical_title != "Não Identificado": ai_data["role"] = mechanical_title

                # Validação Final de Whitelist de Segurança
                if not has_proof and trust_score < 70 and not is_valid:
                    is_valid = False
                    ai_data["reason"] = "Safety Filter: No B2B keywords found in bio or AI evidence"

                enriched = {**enriched, **deep_enriched}

                # Log do Resultado da Repescagem (Transparência Total)
                try:
                    with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
                        f.write(f"[RESULTADO REPESCAGEM] CANDIDATO: {name}\n")
                        f.write(f"LINK: {href}\n")
                        f.write("--- [METADADOS BRUTOS] ---\n")
                        f.write(f"DEEP TITLE: {enriched.get('name')} | {enriched.get('role')}\n")
                        f.write(f"DEEP DESC: {enriched.get('description', 'N/A')}\n")
                        f.write("--- [CONSULTA IA] ---\n")
                        f.write(f"RESULTADO: {'✅ APROVADO' if is_valid else '🚫 REJEITADO (' + ai_data.get('reason', '') + ')'}\n")
                except: pass

            name_final = ai_data.get('clean_name', enriched.get("name", name))

            # --- 🎯 SOBERANIA DOS DADOS REAIS (Ground Truth) ---
            raw_role_guess = enriched.get("role", "Professional")
            
            # Ajuste de Título Agregado (Google junta vários nomes)
            # Ex: "Pedro Custodio - Gestor... Camila Lomba - Knorr..."
            if " - " in title:
                # Tenta achar o nome da pessoa no título e pegar o que vem depois
                name_parts = name_final.split()
                # Procura pelo primeiro nome ou nome completo no título
                regex_name = re.escape(name_parts[0]) if name_parts else re.escape(name_final)
                # Regex 'Lazy' que para antes do próximo Nome Próprio (Palavra em Maiúscula)
                match_role = re.search(fr"{regex_name}[^\-]*-\s*([^·\-\|]*?)(?=[A-Z][a-z]+\s+[A-Z]|$)", title, re.I)
                
                if match_role:
                    potential_role = match_role.group(1).strip()
                    if len(potential_role) > 3 and temp_brand.lower() not in potential_role.lower():
                        raw_role_guess = potential_role
                else:
                    # Fallback para o split clássico se não achar o nome
                    parts = title.split(" - ")
                    if len(parts) > 1:
                        potential_role = parts[1].split(" | ")[0].strip()
                        if len(potential_role) > 3 and temp_brand.lower() not in potential_role.lower():
                            raw_role_guess = potential_role

            # Se ainda assim o cargo for "Knorr" ou similar, buscamos no body (snippet)
            if raw_role_guess.lower() == temp_brand.lower() or len(raw_role_guess) < 3:
                match = re.search(fr"([^·\-\|]*)\s+(na|at|no|da|da|de|on)\s+{re.escape(temp_brand)}", body, re.I)
                if match:
                    raw_role_guess = match.group(1).strip()

            # O cargo final obedece uma hierarquia de confiança:
            # 1. The Org (Verdade de Campo Oficial)
            # 2. IA Distill (Se a confiança for alta)
            # 3. Google Heuristics (Fallback final)
            if theorg_role and theorg_role not in ["Não Encontrado", "Confirmed Profile"]:
                role_final = theorg_role
                is_valid = True  # The Org é a verdade absoluta, ignoramos falhas da IA
            elif ai_data.get('matching_score', 0) > 90 and ai_data.get('role') not in ["Profissional B2B", "Não Identificado"] and len(ai_data.get('role', '')) > 4:
                role_final = ai_data.get('role')
            else:
                role_final = clean_extracted_role(raw_role_guess, name_final, temp_brand)
            
            # --- 🎨 LIMPEZA ESTÉTICA FINAL ---
            role_final = html.unescape(role_final)
            
            # --- 📝 LOG DE AUDITORIA FINAL ---
            try:
                with open("logs/engine_raw.log", "a", encoding="utf-8") as f:
                    log_type = "[BATCH/LOTE]" if is_valid else "[REPROVADO]"
                    f.write(f"{log_type} CANDIDATO: {name}\n")
                    f.write(f"LINK: {href}\n")
                    f.write("--- [METADADOS BRUTOS] ---\n")
                    f.write(f"GOOGLE TITLE: {title}\n")
                    f.write(f"LINKEDIN OG: {enriched.get('role', 'N/A')}\n")
                    f.write("--- [DADOS BRUTOS ENVIADOS PARA IA] ---\n")
                    context_to_log = deep_context if deep_context else c.get('context', [])
                    f.write(f"CONTEXT: {' | '.join(context_to_log)}\n")
                    f.write("--- [HUNT RESULT (THE ORG)] ---\n")
                    f.write(f"CARGO THE ORG: {theorg_role}\n")
                    f.write(f"URL THE ORG: {theorg_url}\n")
                    f.write("--- [DECISÃO DA INTELIGÊNCIA ARTIFICIAL] ---\n")
                    status = "✅ APROVADO" if is_valid else f"🚫 REJEITADO ({ai_data.get('reason', 'Não atende aos critérios')})"
                    f.write(f"RESULTADO: {status}\n")
                    f.write(f"CARGO FINAL: {role_final}\n")
                    f.write(f"DEPARTAMENTO: {ai_data.get('department')}\n")
                    f.write(f"CONFIANÇA: {ai_data.get('matching_score', 0)}%\n")
                    f.write("-" * 50 + "\n\n")
            except: pass

            if is_valid:
                # --- 📧 GERAÇÃO AUTOMÁTICA DE EMAIL ---
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
                    "department": get_department_tag(role_final),
                    "level": get_seniority_level(role_final),
                    "email": generated_email,
                    "avatar": enriched.get("image"),
                    "company_logo": enriched.get("company_logo"),
                    "education": f"{ai_data.get('evidence', '')} {enriched.get('description', '')}".strip() or "B2B Profile",
                    "location": location or "Brasil",
                    "matching_score": ai_data.get('matching_score', 50)
                }
                
                # 💾 SALVA NO BANCO DE DADOS IMEDIATAMENTE
                if db_org_id:
                    try:
                        async with async_session() as session:
                            stmt = select(Employee).where(Employee.linkedin_url == node_data["url"])
                            check = await session.execute(stmt)
                            if not check.scalars().first():
                                emp = Employee(
                                    name=node_data["name"],
                                    role=node_data["role"],
                                    seniority=node_data["level"],
                                    department=node_data["department"],
                                    email=node_data["email"],
                                    profile_pic=node_data["avatar"],
                                    description=node_data["education"], # Usamos o campo education que já contém o snippet sintetizado
                                    location=node_data["location"],
                                    linkedin_url=node_data["url"],
                                    company_id=db_org_id
                                )
                                session.add(emp)
                                await session.commit()
                    except: pass
                
                # 🚀 TRANSMITE PARA O FRONT-END IMEDIATAMENTE (Individualmente)
                yield [node_data]

    # --- FIM DO SCANNER ---
    yield [{"type": "done"}]

    yield [{"type": "done"}]
