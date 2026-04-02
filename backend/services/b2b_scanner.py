from .search_engine import get_duck_results

def rescue_profile_link(name: str, company: str) -> str:
    """Tenta resgatar o link de um perfil aprovado que veio sem URL (Repescagem)."""
    try:
        query = f'"{name}" "{company}" site:br.linkedin.com'
        results = get_duck_results(query, max_results=3)
        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            if "linkedin.com/in/" in href:
                return href
    except: pass
    return ""

import re
import os
import time
import random
from typing import List, Dict, Optional, Generator
from .search_engine import get_duck_results
from .email_service import apply_pattern, get_permutations, verify_email
from .filters import get_seniority_level, normalize_str, apply_strict_filters, get_department_tag

def discover_employees(company_name: str, domain: str, email_api_key: str = None, max_results: int = 50) -> List[Dict]:
    """Motor B2B síncrono para descoberta de funcionários."""
    # Estratégia de Busca em Camadas (Garante que pegamos do CEO ao Analista)
    queries = [
        # Camada 6/5: Alta Cúpula (Diretores e Board)
        f'site:br.linkedin.com/in/ "{company_name}" ("Diretor" OR "Director" OR "VP" OR "Head" OR "Executive" OR "Sócio")',
        # Camada 4: Gestão Tática (Gerentes e Group Leaders)
        f'site:br.linkedin.com/in/ "{company_name}" ("Gerente" OR "Manager" OR "Group Leader" OR "Supervisor")',
        # Camada 3/2: Estratégico (Category Managers e Sourcing)
        f'site:br.linkedin.com/in/ "{company_name}" ("Strategic Sourcing" OR "Category Manager" OR "Especialista")',
        # Camada 1: Operacional (Compradores e Logística)
        f'site:br.linkedin.com/in/ "{company_name}" ("Comprador" OR "Buyer" OR "Logística" OR "Analista")',
        # Camada Regional (Casos como Campinas/SP)
        f'site:br.linkedin.com/in/ "{company_name}" "{location or ""}" "suprimentos"'
    ]
    
    # 🕵️‍♂️ TRACKER DE COBERTURA (Garante que tentamos preencher todos os níveis)
    found_levels = set()
    
    employees = []
    seen_urls = set()
    winning_pattern = None 
    
    for query in queries:
        results = get_duck_results(query, max_results=max_results)
        if not results: continue
        
        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            if not href or "linkedin.com/in/" not in href or href in seen_urls:
                continue
            seen_urls.add(href)
            
            title = res.get('title', '')
            # Extração Básica de Nome e Cargo
            parts = title.replace(" | ", " - ").replace("|", " - ").split(' - ')
            if len(parts) < 1: continue
            
            name = parts[0].strip()
            role = parts[1].strip() if len(parts) > 1 else "Especialista em Supply Chain"
            
            # Filtro Simples de Empresa
            core_company_name = domain.split('.')[0].lower() 
            if core_company_name not in title.lower() and company_name.lower() not in title.lower():
                continue
            
            name_parts = name.split()
            if not name_parts: continue
            first = name_parts[0].lower()
            last = name_parts[-1].lower() if len(name_parts) > 1 else first
            
            if winning_pattern:
                final_email = apply_pattern(first, last, domain, winning_pattern)
            else:
                permutations = get_permutations(first, last, domain)
                pattern_found = False
                for email_guess, pat_name in permutations:
                    if verify_email(email_guess):
                        winning_pattern = pat_name
                        final_email = apply_pattern(first, last, domain, pat_name)
                        pattern_found = True
                        break
                if not pattern_found:
                    winning_pattern = "first.last"; final_email = f"{first}.{last}@{domain}"
            
            employees.append({
                "name": name.title(),
                "role": role[:50], 
                "email": final_email,
                "linkedin": href,
                "company": company_name
            })
    return employees

def discover_employees_stream(company_name: str, domain: str, confirmed_brand: Optional[str] = None, location: Optional[str] = None, email_api_key: str = None, max_results: int = 100) -> Generator[List[Dict], None, None]:
    """Motor B2B Streaming de Alta Performance."""
    from .brand_discovery import discover_company_brand
    
    # 🎯 IDENTIFICAÇÃO DE MARCA (Unifica a lógica para descoberta e confirmação)
    cnpj_clean = "".join(filter(str.isdigit, str(company_name)))
    core_name = company_name.split(" (")[0]
    
    if confirmed_brand:
        print(f"[B2B Engine] 💎 Usando Marca Confirmada pelo Usuário: {confirmed_brand}")
        brand_name = confirmed_brand
        raw_candidates = [confirmed_brand]
    else:
        print(f"[B2B Engine] 🔍 Identificando Marca oficial para: {cnpj_clean or core_name}...")
        brand_data = discover_company_brand(cnpj_clean, domain, core_name)
        brand_name = brand_data["brand"]
        raw_candidates = [brand_name] + [alt["name"] for alt in brand_data.get("alternatives", [])[:2]]

    # 🧼 ATOMIZAÇÃO (Gera versões curtas para busca volumosa)
    search_keywords = []
    unique_check = set()
    
    for base in raw_candidates:
        # Gera: Nome Completo, Primeiras 2 palavras, Primeira palavra
        words = base.split()
        variants = [base]
        if len(words) > 1: variants.append(" ".join(words[:2]))
        if len(words) > 0: variants.append(words[0])
        
        for kw in variants:
            # Limpeza radical de termos corporativos e jurídicos que ninguém coloca no LinkedIn pessoal
            clean = re.sub(r"(\bltda\b|\bs\.?a\.?\b|\bs/a\b|cnpj|eireli|\.ind|\.br|\.com)", "", kw, flags=re.IGNORECASE).strip()
            clean = re.sub(r"[\.\-/]", " ", clean)
            clean = " ".join(clean.split())
            
            if len(clean) >= 3 and clean.lower() not in unique_check:
                search_keywords.append(clean)
                unique_check.add(clean.lower())
    
    # Limita a busca aos 3 nomes mais fortes para evitar redundância extrema
    search_keywords = search_keywords[:3]
    
    print(f"[B2B Engine] 🏆 Marca Identificada: {brand_name.upper()} (Busca via: {search_keywords})")
    print(f"[B2B Engine] 🚀 Iniciando Escaneamento: {brand_name.upper()}")

    loc_clean = location.split(",")[0] if location else ""
    
    # 🎯 ESTRATÉGIA DE BUSCA ORGÂNICA (Queries Simples para burlar WAF)
    # Em vez de uma query gigante, fazemos várias buscas "naturais"
    
    base_queries = []
    for kw in search_keywords:
        # Camada executiva (Fragmentada)
        base_queries.append(f'site:br.linkedin.com/in/ "{kw}" Diretor Compras {loc_clean}')
        base_queries.append(f'site:br.linkedin.com/in/ "{kw}" Procurement Director {loc_clean}')
        base_queries.append(f'site:br.linkedin.com/in/ "{kw}" Gerente Suprimentos {loc_clean}')
        base_queries.append(f'site:br.linkedin.com/in/ "{kw}" Supply Chain Manager {loc_clean}')
        base_queries.append(f'site:br.linkedin.com/in/ "{kw}" Head of Procurement {loc_clean}')
        
        # Camada operacional (Fragmentada)
        base_queries.append(f'site:br.linkedin.com/in/ "{kw}" Comprador Senior {loc_clean}')
        base_queries.append(f'site:br.linkedin.com/in/ "{kw}" Strategic Sourcing {loc_clean}')
        base_queries.append(f'site:br.linkedin.com/in/ "{kw}" Especialista Suprimentos {loc_clean}')
        base_queries.append(f'site:br.linkedin.com/in/ "{kw}" Coordenador Compras {loc_clean}')
        
    # Shuffle para não manter padrão de busca
    random.shuffle(base_queries)
    
    # Executa apenas as Top 12 mais promissoras para manter o volume sob controle
    selected_queries = base_queries[:12]
    
    seen_urls = set()
    log_path = os.path.join(os.getcwd(), "logs", "engine_raw.log")
    
    # Define o nome da marca para o log (Pega o primeiro termo da busca)
    brand_name_log = search_keywords[0].upper() if search_keywords else company_name.upper()
    
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f_log:
        f_log.write(f"\n{'='*80}\n")
        f_log.write(f"SESSÃO: {brand_name_log} ({company_name}) | LOCAL: {location}\n")
        f_log.write(f"DATA: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f_log.write(f"{'='*80}\n")

    print(f"[B2B Engine] 🚀 Iniciando Escaneamento: {brand_name_log}")
    
    for idx, query in enumerate(selected_queries):
        print(f"[B2B Engine] 🔍 Minerando Lote {idx+1}: {query}")
        results = get_duck_results(query, max_results=60)
        if not results: continue
        
        batch = []
        for res in results:
            href = res.get("href", "").split("?")[0].rstrip("/")
            if not href or "linkedin.com/in/" not in href or href in seen_urls: continue
            
            title = res.get('title', '').replace(" | LinkedIn", "").strip()
            body = (res.get("body") or res.get("snippet") or "").strip()
            
            # 🛡️ TRATAMENTO DE RESULTADOS AMALGAMADOS (Super-Splitter Bosch/Robert Bosch)
            raw_title = res.get('title', '').replace(" | LinkedIn", "").strip()
            raw_body = body
            
            # Lista de variantes para quebra (Quanto mais variada, melhor a quebra)
            core_name = brand_name.split()[0] if brand_name else company_name
            variants = [brand_name, core_name, "Robert Bosch", "Bosch Brasil", "Bosch Brazil"]
            variants = sorted(list(set([v for v in variants if len(v) > 3])), key=len, reverse=True)
            
            # Cria a Regex de Quebra (ex: /(Robert Bosch|Bosch Brasil|...)/i)
            split_regex = r"(?i)(" + "|".join([re.escape(v) for v in variants]) + r")"
            
            # Divide o amálgama em pedaços individuais
            potential_blocks = []
            if len(re.findall(split_regex, raw_title)) > 1:
                # Divide o título: Ex: ["Nome1 - ", "Marca", "Nome2 - ", "Marca", ...]
                raw_parts = re.split(split_regex, raw_title)
                # Reagrupa [Nome/Cargo] com sua respectiva [Marca]
                for i in range(0, len(raw_parts) - 1, 2):
                    p_text = raw_parts[i].strip()
                    p_brand = raw_parts[i+1].strip()
                    if len(p_text) > 5:
                        potential_blocks.append({"title": f"{p_text} {p_brand}", "body": raw_body})
            else:
                potential_blocks.append({"title": raw_title, "body": raw_body})

            for b_idx, block in enumerate(potential_blocks):
                title = block["title"]
                body = block["body"]
                
                # 🔗 VALIDAÇÃO DE LINK (Anti-Hallucination + Repescagem)
                current_href = href
                is_sub_profile = (b_idx > 0)
                
                if is_sub_profile:
                    # Parte 1: Tenta achar um link no corpo
                    other_links = re.findall(r'https?://[a-z]+\.linkedin\.com/in/[^/\s?]+', body)
                    found_diff = [l.split("?")[0].rstrip("/") for l in other_links if l.split("?")[0].rstrip("/") != href]
                    if found_diff:
                        current_href = found_diff[0]
                    else:
                        # Se não achou na sorte, vamos marcar como "Pendência de Link"
                        current_href = None

                processed_title = title

                # 🚀 DEDUPLICAÇÃO DE SUB-PERFIL
                if b_idx > 0 and current_href in seen_urls: continue
                if b_idx > 0: seen_urls.add(current_href)

                processed_title = title
            
                # Limpeza de cargo/nome no título do bloco
                name_parts = [p.strip() for p in re.split(r"\s*[\|\-–:·•]\s*", processed_title) if p.strip()]
                if not name_parts: continue
                
                name = name_parts[0].replace("...", "").strip()
                # ✂️ SUPER-SPLITTER (Anti-Smash 3.0)
                # Usamos múltiplas variações da marca como "bisturi" para fatiar o amontoado
                brand_variations = [brand_name, "Robert Bosch", "Bosch", confirmed_brand]
                # Remove duplicatas e strings vazias, e escapa para Regex
                brand_pattern = "|".join(sorted(set(re.escape(v) for v in brand_variations if v), key=len, reverse=True))
                
                # 🧼 Limpeza Profunda do Nome (Remove lixo de empresa/departamento grudado no nome)
                # Anti-Smash: Se o nome começou grudado com a marca (ex: BrasilMaria)
                name = re.sub(rf"(?i)({brand_pattern}|Power Tools|Brasil|Ltd|S/A|Ltda|Systems|S/S)", "", name).strip()
                # Remove prefixos de ligação que "sobraram" do split
                name = re.sub(r"(?i)^(do|da|de|na|no|o|a|e|at|...)\s+", "", name).strip()
                
                # 🛡️ ANTI-NOISE: Se o nome ou o cargo for apenas "LinkedIn" ou variações, descarta
                noise_pattern = r"(?i)^(linkedin|linked in|linked|perfil|profile|ver no linkedin)$"
                if re.match(noise_pattern, name) or (title and re.search(noise_pattern, title)):
                    continue

                if len(name) < 3: continue

                # 🎯 SNIPPET ISOLATION
                focused_body = body
                try:
                    first_name_ref = name.split()[0].lower()
                    if first_name_ref in body:
                        pos = body.find(first_name_ref)
                        start = max(0, pos - 60)
                        end = min(len(body), pos + 220)
                        focused_body = body[start:end]
                except: pass

                # Aplicar Filtros Strict
                core_company_name = domain.split('.')[0].lower() if domain else company_name.lower()
                filter_res = apply_strict_filters(name, title, focused_body, core_company_name, brand_name, location)
                
                # 🚑 MOTOR DE REPESCAGEM (Resgate de Perfil Aprovado sem Link)
                link_rescue_failed = False
                if filter_res and current_href is None:
                    print(f"      [REPESCAGEM] 🚑 Buscando link real para: {name}...")
                    current_href = rescue_profile_link(name, confirmed_brand)
                    if not current_href:
                        link_rescue_failed = True
                    elif current_href in seen_urls: 
                        link_rescue_failed = True
                    else:
                        seen_urls.add(current_href)

                # 📝 LOG DE AUDITORIA (Transparência Total - Agora para TODOS)
                with open(log_path, "a", encoding="utf-8") as fl:
                    status = "✅ APROVADO" if (filter_res and not link_rescue_failed) else "🚫 BLOQUEADO (Filtro Strict)"
                    if filter_res and link_rescue_failed:
                        status = "🚫 BLOQUEADO (Link não encontrado na Repescagem)"
                    
                    suffix = f" [SUB-PERFIL {b_idx+1}]" if len(potential_blocks) > 1 else ""
                    fl.write(f"\n[QUERY: {idx+1}] CANDIDATO: {name}{suffix}\n")
                    fl.write(f"LINK: {current_href or 'PENDENTE'}\n")
                    fl.write(f"RESULTADO: {status}\n")
                    fl.write(f"--- [DADOS BRUTOS DO MOTOR] ---\n")
                    fl.write(f"TITLE BRUTO: {title}\n")
                    fl.write(f"BODY BRUTO: {body[:400]}...\n")
                    fl.write(f"{'-'*30}\n")
                
                if not filter_res or link_rescue_failed:
                    continue
                
                # 🔍 EXTRAÇÃO DE CARGO DE ALTA PRECISÃO
                role_candidate = ""
                t_parts = re.split(r"\s*[||\-–·•]\s*", processed_title)
                anchor_words = ["comprador", "buyer", "procurement", "sourcing", "supply", "chain", "manager", "director", "analista", "especialista", "suprimentos", "logística", "gerente", "diretor", "coordenador", "head", "purchasing", "lead", "compras", "purchas"]
                
                for tp in t_parts:
                    tp_clean = tp.strip()
                    tp_lower = tp_clean.lower()
                    if tp_lower in brand_name.lower() or name.lower() in tp_lower: continue
                    if any(aw in tp_lower for aw in anchor_words):
                        tp_clean = re.sub(r"\b[A-Z][a-z]+\s[A-Z][a-z]+.*$", "", tp_clean).strip()
                        role_candidate = tp_clean
                        break

                if not role_candidate:
                    snippet_text = filter_res["context_to_check"].lower()
                    for aw in anchor_words:
                        if aw in snippet_text:
                            pos = snippet_text.find(aw)
                            segment = filter_res["context_to_check"][max(0, pos-20) : pos+40]
                            segment = re.sub(r"(veja|perfil|linkedin|comunidade|bilhão|conexões|links?|experiência|localidade|at|em|no|na|of|the).*$", "", segment, flags=re.IGNORECASE).strip()
                            if len(segment) > 5:
                                role_candidate = segment
                                break

                # 🛠️ POST-PROCESSING (Limpeza de "Cargos Smashed" e Falsos Positivos)
                role_candidate = re.sub(re.escape(brand_name), "", role_candidate, flags=re.IGNORECASE).strip()
                # Se o cargo ficou "manco" (ex: "Head of" ou "Gerente de"), busca no snippet
                if len(role_candidate) < 8 or role_candidate.lower().endswith((" of", " de", " da", " do")):
                    # Tenta achar o cargo completo no snippet
                    role_pattern = rf"{re.escape(name)}.*?(?:at|na|no|em|is a|trabalha como)\s+([^·,\|]+)"
                    extended_role = re.search(role_pattern, focused_body, re.I)
                    if extended_role:
                        role_candidate = extended_role.group(1).strip()
                    else:
                        # Busca heurística por palavras de cargo no snippet
                        role_heuristic = re.search(r"(head of [^·,\|]+|gerente de [^·,\|]+|diretor de [^·,\|]+|comprador [^·,\|]+|regional head [^·,\|]+)", focused_body, re.I)
                        if role_heuristic:
                            role_candidate = role_heuristic.group(1).strip()

                # Remove prefixos lixo de 1-3 letras no começo
                role_candidate = re.sub(r"^[A-Z]{1,3}\b\s*", "", role_candidate)
                # Corrige CamelCase
                role_candidate = re.sub(r"([a-z])([A-Z])", r"\1 \2", role_candidate)
                
                if not role_candidate or len(role_candidate) < 4:
                    if any(k in query.lower() for k in ["diretor", "director", "head"]): role_candidate = "Management / Strategy"
                    elif any(k in query.lower() for k in ["gerente", "manager"]): role_candidate = "Suprimentos (Geral)"
                    else: role_candidate = "Professional"

                role = role_candidate.title()[:80].strip()
                department = get_department_tag(role) # Usa a função robusta do filters.py
                seniority = get_seniority_level(role)
                print(f"      [APROVADO] ✅ {name} ({role}) {'[Múltiplo]' if len(potential_blocks) > 1 else ''}")
    
                n_parts = name.lower().split()
                f = n_parts[0] if n_parts else "user"
                l = n_parts[-1] if len(n_parts) > 1 else "name"
                email_guess = f"{f}.{l}@{domain.lstrip('@')}" if domain else f"{f}.{l}@company.com"
                
                # ID Único para evitar colisões em amálgamas
                node_id = f"node_{current_href.split('/in/')[-1].replace('/', '_')}_{b_idx}"
                
                # 💎 EXTRAÇÃO DE DADOS PROFUNDA (Heurística Avançada)
                snippet = focused_body
                snippet_lower = snippet.lower()
                
                # 1. Formação Acadêmica (Busca Explícita + Heurística)
                edu_match = re.search(r"(?:formação acadêmica|education):\s*([^·,\|]+)", snippet, re.I)
                education = edu_match.group(1).strip() if edu_match else "N/A"
                
                if education == "N/A":
                    # Tenta achar nomes de faculdades conhecidas no texto bruto
                    univ_patterns = r"(usp|unicamp|fgv|facamp|unisal|puc|esamc|mackenzie|fatec|senai|inpg|insper|senac|fei|fmu|unip|unifesp|ita|ime|harvard|mit|inova|school)"
                    univ_match = re.search(univ_patterns, snippet_lower)
                    if univ_match:
                        education = univ_match.group(0).upper()
                
                # 🔥 Limpeza de Cargo e Anti-Truncamento
                role_clean = re.sub(r"[\-\|·].*$", "", role_candidate).strip() if " - " in role_candidate or " | " in role_candidate else role_candidate
                role_clean = re.sub(brand_pattern, "", role_clean, flags=re.IGNORECASE).strip()
                role_clean = role_clean.replace(name, "").strip().strip("-").strip("|").strip()

                # Se o cargo ficou "manco" ou Vazio (ex: Gaston Diaz Perez - Bosch), busca no snippet
                if len(role_clean) < 4 or role_clean.lower() in ["professional", "linkedin", "bosch", "robert bosch", "brasil"]:
                    # Tenta achar o cargo completo no snippet
                    role_pattern = rf"{re.escape(name)}.*?(?:at|na|no|em|is a|trabalha como|head of|director|vp|manager|lead)\s+([^·,\|]+)"
                    extended_role = re.search(role_pattern, snippet, re.I)
                    if extended_role:
                        role_clean = extended_role.group(1).strip()
                    else:
                        # Busca heurística ultra-agressiva por palavras-chave técnicas e de gestão
                        role_heuristic = re.search(r"(ceo|presidente|head of [^·,\|]+|diretor|gerente|comprador|sourcing|procur|logis|engineer|engenheiro|analista|analyst|specialist|especialista|suprimentos|supply)[^·,\|]+", snippet, re.I)
                        if role_heuristic:
                            role_clean = role_heuristic.group(0).strip()
                        else:
                            role_clean = "Procurement Professional"

                # Limpeza final de ruído corporativo no cargo
                role_clean = re.sub(rf"(?i)\s*(at|na|no|em|da|do|is|working)\s*({brand_pattern}|linkedin|perfil|community).*$", "", role_clean)
                role_final = role_clean[:80].strip().title()

                # 🎯 CALCULO DE HIERARQUIA (Após cargo limpo e completo)
                seniority = get_seniority_level(role_final)
                department = get_department_tag(role_final)

                # 2. Localização (Busca Explícita + Heurística)
                loc_match = re.search(r"(?:localidade|location):\s*([^·,\|]+)", snippet, re.I)
                location_val = loc_match.group(1).strip() if loc_match else "N/A"
                
                if location_val == "N/A":
                    # Tenta achar cidades conhecidas (Polos Industriais)
                    city_patterns = r"(campinas|são\s?paulo|indaiatuba|valinhos|vinhedo|sumaré|hortolândia|sorocaba|itu|jundiaí|jaguariúna|paulina|americana|limeira|piracicaba|curitiba|manaus|salto|itupeva)"
                    city_match = re.search(city_patterns, snippet_lower)
                    if city_match:
                        location_val = city_match.group(0).title()

                # 3. Conexões (Suporte a PT e EN)
                conn_match = re.search(r"(\+ de \d+|[\d\.\,kK\+]+)\s*(?:conexões|connections)", snippet, re.I)
                connections = conn_match.group(1).strip() if conn_match else "N/A"
                
                # 4. Destaques (Certificações, Metodologias)
                highlights = []
                for tag in ["MBA", "PMP", "Black Belt", "Green Belt", "Six Sigma", "Strategic Sourcing", "Supply Chain", "CPIM", "Procurement"]:
                    if tag.lower() in snippet_lower:
                        highlights.append(tag)
                
                n_parts = name.lower().split()
                f = n_parts[0] if n_parts else "user"
                l = n_parts[-1] if len(n_parts) > 1 else "name"
                email_guess = f"{f}.{l}@{domain.lstrip('@')}" if domain else f"{f}.{l}@company.com"
                
                # ID Único para evitar colisões em amálgamas
                node_id = f"node_{href.split('/in/')[-1].replace('/', '_')}_{b_idx}"
                
                # 5. Observações de Auditoria
                obs_list = []
                if location_val.lower() in snippet_lower and "@" not in location_val:
                    obs_list.append("📍 Localização validada no perfil")
                if any(h.lower() in snippet_lower for h in (highlights or [])):
                    obs_list.append("🏆 Certificações encontradas")
                
                batch.append({
                    "id": node_id,
                    "name": name.title(),
                    "role": role_final,
                    "company": brand_name,
                    "email": email_guess,
                    "url": f"https://br.linkedin.com{href}" if href.startswith('/') else href,
                    "department": department,
                    "level": seniority,
                    "education": education,
                    "location": location_val,
                    "connections": connections,
                    "highlights": ", ".join(highlights) if highlights else "N/A",
                    "observations": " | ".join(obs_list) if obs_list else snippet.strip()[:100] + "..."
                })

            seen_urls.add(href)
        
        if batch:
            print(f"[B2B Engine] 🚀 Despachando lote de {len(batch)} nomes.")
            yield batch
