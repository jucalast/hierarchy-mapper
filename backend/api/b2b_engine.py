import re
import socket
import smtplib
import httpx
import os
import time
from typing import List, Dict, Optional
from ddgs import DDGS

def verify_linkedin_url(url: str) -> bool:
    """Verifica se a URL do LinkedIn é válida (não retorna 404)."""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.head(url, allow_redirects=True)
            return response.status_code != 404
    except Exception:
        return False

def verify_email(email: str, api_key: str = None) -> bool:
    """
    Validação de email genérica sem dependências de APIs externas.
    Usa validação sintática + verificação de domínio + SMTP check (opcional).
    """
    if not email or '@' not in email:
        return False
    
    # Validação sintática básica
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    
    domain = email.split('@')[1]
    
    try:
        # Verifica se o domínio existe
        socket.gethostbyname(domain)
        
        # Verificação SMTP (mais leve, sem enviar email)
        try:
            with smtplib.SMTP(domain, timeout=5) as server:
                server.helo()
                server.mail('test@example.com')
                code, message = server.rcpt(email)
                return code == 250
        except (smtplib.SMTPException, socket.timeout, ConnectionRefusedError):
            # Se SMTP falhar, considera válido apenas pela sintaxe e domínio
            return True
            
    except socket.gaierror:
        return False
    
    return True

def get_permutations(first: str, last: str, domain: str) -> List[tuple]:
    """Retorna formatos possíveis e seu identificador de padrão."""
    return [
        (f"{first}.{last}@{domain}", "first.last"),
        (f"{first[0]}{last}@{domain}", "f_last"),
        (f"{first}{last}@{domain}", "firstlast"),
        (f"{first}@{domain}", "first")
    ]

def apply_pattern(first: str, last: str, domain: str, pattern: str) -> str:
    """Aplica o padrão vencedor a um novo funcionário."""
    if pattern == "first.last": return f"{first}.{last}@{domain}"
    if pattern == "f_last": return f"{first[0]}{last}@{domain}"
    if pattern == "firstlast": return f"{first}{last}@{domain}"
    if pattern == "first": return f"{first}@{domain}"
    return f"{first}.{last}@{domain}" # default

def discover_employees(company_name: str, domain: str, email_api_key: str = None, max_results: int = 50) -> List[Dict]:
    """
    Motor B2B genérico para descoberta de funcionários.
    Usa Multi-Query para triplicar o volume e burlar paginação curta de buscadores.
    """
    # 💥 MOTOR POTENTE DESAGRUPADO: Várias consultas individuais granulares para máxima precisão
    queries = [
        f'site:br.linkedin.com/in/ "{company_name}" "compras"',
        f'site:br.linkedin.com/in/ "{company_name}" "supply chain"',
        f'site:br.linkedin.com/in/ "{company_name}" "procurement" OR "buyer"',
        f'site:br.linkedin.com/in/ "{company_name}" "category manager" OR "sourcing"',
        f'site:br.linkedin.com/in/ "{company_name}" "embalagem" OR "packaging"',
        f'site:br.linkedin.com/in/ "{company_name}" "diretos" OR "indiretos"',
        f'site:br.linkedin.com/in/ "{company_name}" "capex" OR "cpo"'
    ]
    
    employees = []
    seen_urls = set()
    winning_pattern: Optional[str] = None 
    verified_urls = {}  # Cache para URLs verificadas 
    
    import time
    import random
    
    try:
        for query in queries:
            results = []
            
            # 🛡️ ANTI-BAN SYSTEM: Rotação de backends e recriação do cliente a cada tentativa
            for backend in ["api", "lite", "html"]:
                try:
                    # Delay humano randômico para destruir padrões de identificação de bots
                    time.sleep(random.uniform(2.5, 4.5))
                    
                    with DDGS() as ddgs:
                        # Extrai a lista do generator forçando a execução da requisição
                        search_iter = ddgs.text(query, region="br-pt", max_results=max_results, backend=backend)
                        if search_iter:
                            results = list(search_iter)
                        
                    if results:
                        # Achou resultados! Quebra a tentativa de backends (Anti-ban Sucesso!)
                        break
                except Exception as e:
                    print(f"[B2B Anti-Ban] DuckDuckGo '{backend}' deu block. Girando backend...")
                    continue # Tenta o próximo (ex: api -> lite -> html)
                    
            if not results:
                continue
                
            for res in results:
                    href = res.get("href", "")
                    title = res.get('title', '')
                    
                    # 🛡️ VALIDAÇÃO DE LINK DO LINKEDIN
                    if not href or "linkedin.com/in/" not in href:
                        continue
                    
                    # Limpeza da URL do LinkedIn para evitar 404 (remove parâmetros como ?trk= ou /pt/)
                    href = href.split("?")[0].rstrip("/")
                    
                    if href in seen_urls:
                        continue
                    
                    # Temporariamente desabilitando validação de URL para performance
                    seen_urls.add(href)
                    
                    title = res.get('title', '')
                    
                    # 🛡️ ANTI-FALSO POSITIVO
                    core_company_name = domain.split('.')[0].lower() 
                    search_name = company_name.lower()
                    
                    # Verifica se o nome da empresa está no título (flexível)
                    if core_company_name not in title.lower() and search_name not in title.lower():
                        continue
                        
                    normalized_title = title.replace(" | ", " - ").replace("|", " - ")
                    parts = normalized_title.split(' - ')
                    
                    if len(parts) >= 1:
                        name = parts[0].strip()
                        if len(name.split()) < 2 or "linkedin" in name.lower() or "perfil" in name.lower() or "..." in name:
                            continue
                            
                        # 🎯 EXTRAÇÃO INTELIGENTE DE CARGO E EMPRESA ATUAL
                        role = ""
                        current_company = None
                        
                        # Procura pela empresa atual (geralmente a primeira após o nome)
                        for i, part in enumerate(parts[1:], 1):
                            clean_part = part.strip()
                            
                            # Se contém "at" ou "na" + empresa, essa é a empresa atual
                            if " at " in clean_part.lower() or " na " in clean_part.lower():
                                # Ex: "Director, Procurement and Contracts - New Programs Development at Embraer"
                                if " at " in clean_part.lower():
                                    role_parts = clean_part.split(" at ")
                                    role = role_parts[0].strip()
                                    current_company = role_parts[1].strip() if len(role_parts) > 1 else ""
                                elif " na " in clean_part.lower():
                                    role_parts = clean_part.split(" na ")
                                    role = role_parts[0].strip()
                                    current_company = role_parts[1].strip() if len(role_parts) > 1 else ""
                                break
                            # Se não achou "at/na", assume que a primeira parte é o cargo
                            elif not role and not any(keyword in clean_part.lower() for keyword in ["linkedin", "perfil"]):
                                role = clean_part
                        
                        # Se não encontrou empresa atual com "at/na", usa a primeira empresa encontrada
                        if not current_company:
                            for part in parts[1:]:
                                clean_part = part.strip()
                                if clean_part and clean_part.lower() not in ["linkedin", "perfil profissional"]:
                                    # Verifica se não é um cargo (palavras-chave de cargo)
                                    if not any(keyword in clean_part.lower() for keyword in ["director", "manager", "analyst", "analista", "supervisor", "coordinator", "gerente", "procurement", "compras", "supply"]):
                                        current_company = clean_part
                                        break
                                        
                        # 🛡️ FILTRO ESTREITO DE EMPRESA ATUAL: Rejeita se trabalha claramante em outra (ex: Embraer em busca de Bosch)
                        if current_company:
                            if core_company_name not in current_company.lower() and search_name not in current_company.lower():
                                continue
                        
                        if not role:
                            continue
                        
                        # 🛡️ CADEIA DE SUPRIMENTOS STRICT FILTER & SNIPPET FALLBACK (ABRANGENDO ESTRATÉGICO, TÁTICO E CATEGORIAS)
                        supply_keywords = [
                            "supply", "suprimento", "logíst", "logistic", "compras", "procurement", 
                            "buyer", "comprador", "sourcing", "materiais", "estoque", "almoxarifado", 
                            "operaç", "operation", "category", "categoria", "cpo", "embalagem", 
                            "packaging", "diretos", "indiretos", "capex"
                        ]
                        
                        body_snippet = res.get("body", "").lower()
                        
                        is_supply_chain = any(kw in role.lower() for kw in supply_keywords)
                        
                        if not is_supply_chain:
                            # Tenta resgatar da descrição do snippet
                            if any(kw in body_snippet for kw in supply_keywords):
                                # Define provisoriamente baseado na palavra que ele ativou
                                if "category" in body_snippet or "sourcing" in body_snippet: role = "Category Manager / Sourcing"
                                elif "embalagem" in body_snippet or "packaging" in body_snippet: role = "Especialista em Embalagens"
                                elif "compras" in body_snippet or "comprador" in body_snippet: role = "Profissional de Compras"
                                elif "logíst" in body_snippet or "logistic" in body_snippet: role = "Profissional de Logística"
                                elif "supply" in body_snippet: role = "Profissional de Supply Chain"
                                else: role = "Operações B2B"
                            else:
                                continue # Exclui completamente: É o algoritmo do LinkedIn empurrando perfis do RH/Engenharia por tabela!
                        
                        if not role:
                            role = "Especialista em Supply Chain"
                            
                        first = name.split()[0].lower()
                        last = name.split()[-1].lower()
                        
                        # ARQUITETURA DE EMAIL - USA DOMÍNIO INFORMADO (CONSISTENTE)
                        final_email = ""
                        if winning_pattern:
                            # Usa o domínio informado na API (sempre consistente)
                            final_email = apply_pattern(first, last, domain, winning_pattern)
                        else:
                            permutations = get_permutations(first, last, domain)
                            pattern_found = False
                            
                            # Validação de email genérica (sem dependências)
                            for email_guess, pat_name in permutations:
                                is_valid = verify_email(email_guess)
                                if is_valid:
                                    winning_pattern = pat_name
                                    # Usa o domínio informado na API (sempre consistente)
                                    final_email = apply_pattern(first, last, domain, pat_name)
                                    pattern_found = True
                                    break
                                        
                            if not pattern_found:
                                winning_pattern = "first.last" 
                                # Usa o domínio informado na API (sempre consistente)
                                final_email = f"{first}.{last}@{domain}"
                        
                        # Log apenas para debug (pode ser removido em produção)
                        # print(f"[DEBUG] Email gerado: {final_email} (empresa: {current_company})")
                        
                        employees.append({
                            "name": name.title(),
                            "role": role[:50], 
                            "email": final_email,
                            "linkedin": href,
                            "company": current_company or company_name
                        })
    except Exception as e:
        print("[Custom B2B Engine Error]:", e)
        
    return employees

def discover_employees_stream(company_name: str, domain: str, location: str = None, email_api_key: str = None, max_results: int = 100):
    """
    Motor B2B de Alta Performance com Persistência para 200+ Leads.
    Utiliza micro-segmentação de queries para evitar sobrecarga e capturar 
    especialistas em cada 'gaveta' de Procurement.
    """
    # 🎯 SUPER-QUERIES: Agrupamos os termos para fazer MENOS perguntas ao servidor, mas com mais conteúdo
    queries = [
        f'site:br.linkedin.com/in/ "{company_name}" "CPO" OR "Director" OR "Head"',
        f'site:br.linkedin.com/in/ "{company_name}" "Strategic Sourcing" OR "Category Manager"',
        f'site:br.linkedin.com/in/ "{company_name}" "Compras Diretas" OR "Embalagem" OR "Buyer"',
        f'site:br.linkedin.com/in/ "{company_name}" "Compras Indiretas" OR "CAPEX" OR "MRO"',
        f'site:br.linkedin.com/in/ "{company_name}" "Comprador Senior" OR "Analista de Compras"',
        f'site:br.linkedin.com/in/ "{company_name}" "Coordenador Logística" OR "Supply Chain Analyst"'
    ]
    
    seen_urls = set()
    import time
    import random
    import re

    # 🎯 LIMPEZA DE MARCA: De "ROBERT BOSCH LIMITADA" para "BOSCH"
    core_company_name = domain.split('.')[0].lower() 
    brand_name = core_company_name.upper() if len(core_company_name) > 3 else company_name.split()[0]
    
    # 🎯 RASTREADOR DE PIRÂMIDE (QUERIES DE ALTA ADERÊNCIA)
    loc_clean = location.split(",")[0] if location else ""
    
    # 🎯 ESTRATÉGIA DE BUSCA BALANCEADA (Encontra + candidatos para o Filtro limpar)
    neg = "-vagas -jobs"
    
    queries = [
        f'site:br.linkedin.com/in/ "Gerente de Compras" "{brand_name}" {loc_clean} {neg}',
        f'site:br.linkedin.com/in/ "Diretor de Suprimentos" "{brand_name}" {loc_clean} {neg}',
        f'site:br.linkedin.com/in/ "Strategic Sourcing" "{brand_name}" {loc_clean} {neg}',
        f'site:br.linkedin.com/in/ "Procurement Manager" "{brand_name}" {loc_clean} {neg}',
        f'site:br.linkedin.com/in/ "Buyer" "{brand_name}" {loc_clean} {neg}',
        f'site:br.linkedin.com/in/ "Comprador" "{brand_name}" {loc_clean} {neg}',
        f'site:br.linkedin.com/in/ "Analista de Suprimentos" "{brand_name}" {loc_clean} {neg}',
        f'site:br.linkedin.com/in/ "@{brand_name}" "Suprimentos" {loc_clean} {neg}' # Layer de alta fidelidade
    ]

    # 🛡️ LISTA DE BLOQUEIO (Foco em Profissões que NÃO são de escritório/procurement)
    # Movida para o processamento interno para não poluir a query do DuckDuckGo
    blocklist = ["produção", "operador", "ajudante", "montador", "vendedor", "vendas", "sales", "hr", "rh", "human resources", "recursos humanos", "factory", "fábrica"]

    try:
        search_name = company_name.lower()
        print(f"[B2B Engine] 🚀 Iniciando Escaneamento de ALTA FIDELIDADE: {brand_name}")
        
        # Log File Setup
        log_path = os.path.join(os.getcwd(), "logs", "engine_raw.log")
        
        with open(log_path, "a", encoding="utf-8") as f_log:
            f_log.write(f"\n{'='*80}\n")
            f_log.write(f"SESSÃO: {brand_name} ({company_name}) | LOCAL: {location}\n")
            f_log.write(f"DATA: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f_log.write(f"{'='*80}\n")

        for idx, query in enumerate(queries):
            results = []
            # 🕒 Delay Humano: evita rate-limit
            time.sleep(random.uniform(2.5, 5.0))
            
            if idx > 0:
                print(f"[B2B Stream] Camada {idx+1}/{len(queries)}...")
            
            print(f"[B2B Engine] 🔍 Minerando: {query}")
            for backend in ["api", "lite", "html"]:
                try:
                    with DDGS() as ddgs:
                        search_iter = ddgs.text(query, region="br-pt", max_results=40, backend=backend)
                        if search_iter:
                            results = list(search_iter)
                            if results: break
                except: continue
            
            # 🔄 SMART CLUSTER FALLBACK
            # Se a busca específica (ex: Sumaré) falhou, tenta o hub regional (ex: Campinas)
            if not results and loc_clean.lower() in ["sumare", "sumaré"]:
                 print(f"  [B2B] 🔄 Tentando hub regional (Campinas)...")
                 query_hub = query.replace(loc_clean, "Campinas")
                 try:
                     with DDGS() as ddgs:
                         results = list(ddgs.text(query_hub, region="br-pt", max_results=30))
                 except: pass
            
            def process_results(data_list):
                print(f"  [B2B] 🔎 Analisando {len(data_list)} candidatos...")
                batch = []
                for res in data_list:
                    href = res.get("href", "").split("?")[0].rstrip("/")
                    # 🚀 REGRA DE OURO: Apenas perfis do Brasil
                    if not href or "br.linkedin.com/in/" not in href or href in seen_urls: continue
                    
                    title = res.get('title', '').replace(" | LinkedIn", "").strip()
                    body = res.get("body", "").lower()
                    full_context = (title + " " + body).lower()
                    

                    # 🛡️ DATA EXTRACTION
                    # Use slug for better name guessing in combined snippets
                    slug_parts = href.split("/in/")[-1].split("-")
                    slug_name = slug_parts[0].lower()
                    
                    name_parts = [p.strip() for p in re.split(r"\s*[||\-–:]\s*", title) if p.strip()]
                    if not name_parts: continue
                    name = name_parts[0].replace("...", "").strip()
                    
                    # Try to match name with slug to avoid wrong person
                    if slug_name not in name.lower() and len(name_parts) > 1:
                        for part in name_parts:
                            if slug_name in part.lower():
                                name = part.replace("...", "").strip()
                                break

                    # Isolar o contexto específico do candidato
                    fragments = re.split(r"[\-–|·:…\.]", title + " " + body[:250])
                    context_to_check = title + " " + body[:200] # Fallback
                    for frag in fragments:
                        if name.split()[0].lower() in frag.lower():
                            context_to_check = frag.strip()
                            break

                    # Variáveis de contexto para filtros
                    full_context = (title + " " + body).lower()
                    
                    # 🧩 NORMALIZAÇÃO DE TEXTO (IGNORA ACENTOS)
                    def normalize_str(s):
                        import unicodedata
                        return "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()
                    
                    full_context_norm = normalize_str(full_context)
                    loc_norm = normalize_str(loc_clean or "")

                    # 🧩 DETECÇÃO DE PERFIS COLADOS (Profile Smash)
                    # Separa quando a marca está colada em um nome ou preposição (ex: naABB, ABBGiulia, atABBbrazil)
                    patterns = [
                        rf"([a-z]+)({brand_name})", # Preposição+Marca: naABB -> na ... ABB
                        rf"({brand_name})([A-Z][a-z]+)", # Marca+Nome: ABBGiulia -> ABB ... Giulia
                        rf"(at|na|no|da|do|em)({brand_name.lower()})", # Mashed low: naabb -> na ... abb
                    ]
                    for p in patterns:
                        title = re.sub(p, r"\1 ... \2", title, flags=re.IGNORECASE)
                        body = re.sub(p, r"\1 ... \2", body, flags=re.IGNORECASE)

                    # 🧩 EXTRAÇÃO DE FRAGMENTO ÚNICO (Anti-Contágio)
                    # Separamos por reticências e analisamos se o fragmento pertence ao nosso candidato
                    fragments = [f.strip() for f in re.split(r"\s*[…\.]{2,}\s*", title + " " + body[:350]) if len(f.strip()) > 5]
                    relevant_fragments = []
                    
                    name_parts = [p.lower() for p in name.split() if len(p) > 2]
                    
                    for i, frag in enumerate(fragments):
                        frag_low = frag.lower()
                        # Se o fragmento contém o nome do nosso candidato
                        if any(p in frag_low for p in name_parts):
                            relevant_fragments.append(frag)
                            
                            # TENTA PEGAR O PRÓXIMO FRAGMENTO, mas com cuidado!
                            if i + 1 < len(fragments):
                                next_frag = fragments[i+1]
                                # 🛡️ BARREIRA DE VIZINHO: Se o próximo fragmento parece ser OUTRA pessoa, não pega!
                                # Padrão: Nome Próprio + Separador (ex: Rafael Santos - )
                                if not re.match(r"^[A-Z][a-z]+\s[A-Z][a-z]+.*[\-–|·•:]", next_frag):
                                    relevant_fragments.append(next_frag)
                            break
                    
                    context_to_check = " ".join(relevant_fragments) if relevant_fragments else (title + " " + body[:200])
                    context_norm = normalize_str(context_to_check)

                    print(f"    [DADOS] Candidato: {name}")
                    print(f"      [RESUMO] {context_to_check[:95]}...")
                    
                    # 🪵 RAW Logging to file (Start)
                    with open(log_path, "a", encoding="utf-8") as fl:
                        fl.write(f"\n[QUERY: {idx+1}] CANDIDATO: {name}\n")
                        fl.write(f"LINK: {href}\n")
                        fl.write(f"TITLE: {title}\n")
                        fl.write(f"BODY: {body.replace('\n', ' ')}\n")

                    if len(name.split()) < 2 or any(kw in name.lower() for kw in ["linkedin", "perfil", "vaga", "job", "...", "perfil profissional"]):
                        with open(log_path, "a", encoding="utf-8") as fl: fl.write("RESULTADO: 🚫 BLOQUEADO (Nome Inválido/Genérico)\n")
                        print(f"      [BLOQUEIO] 🚫 Nome inválido ou Perfil Genérico")
                        continue

                    # 🛡️ 1. FILTRO DE FIDELIDADE DE MARCA (STRICT & CURRENT)
                    brand_norm = core_company_name.lower()
                    
                    # 🎯 PROXIMITY CHECK: A marca deve estar PRÓXIMA ao nome (máx 25 palavras)
                    words = context_norm.split()
                    try:
                        # Encontra a primeira palavra do nome no contexto
                        name_idx = -1
                        for first_p in name.split():
                            if first_p.lower() in words:
                                name_idx = words.index(first_p.lower())
                                break
                        
                        brand_idx = -1
                        # Procura a marca mesmo que esteja colada em outra palavra no split (ex: atABBbrazil)
                        for i, w in enumerate(words):
                            if brand_norm in w or brand_name.lower() in w:
                                brand_idx = i
                                break

                        is_proximate = False
                        if name_idx != -1 and brand_idx != -1:
                            if abs(name_idx - brand_idx) < 25: # Balanced range
                                is_proximate = True
                    except:
                        is_proximate = False

                    # 🛡️ BARREIRA DE EXPERIÊNCIA PASSADA (Listas de vírgula costumam ser passado)
                    is_past_list = re.search(rf"(empresas como|passagens por|ex-)([\w\s,]*?)\b({brand_norm})\b", context_norm)
                    if is_past_list:
                         with open(log_path, "a", encoding="utf-8") as fl: fl.write(f"RESULTADO: 🚫 BLOQUEADO (Marca citada como experiência PASSADA)\n")
                         print(f"      [BLOQUEIO] 🚫 Marca {brand_name} detectada como experiência PASSADA")
                         continue

                    # O vínculo com a marca DEVE estar no fragmento isolado e ser próximo
                    brand_in_fragment = (any(brand_norm in w or brand_name.lower() in w for w in words)) and is_proximate
                    
                    # 🎯 CURRENT ROLE MARKER
                    current_brand_pattern = rf"(experiência:|experience:|@|atualmente na|working at|desde|\b(na|at|no|em|da|job at))\s?([\w\s]*?)\b({core_company_name}|{brand_norm})\b"
                    current_match = re.search(current_brand_pattern, context_to_check, re.IGNORECASE)
                    
                    # Detect other companies that might be the REAL current one
                    other_company_match = re.search(r"\b(na|at|no|em|da|working at|atualmente na)\b\s+([A-Z][\w\s]{2,30})", context_to_check, re.IGNORECASE)
                    
                    if not brand_in_fragment and not (current_match and brand_norm in current_match.group(0).lower()):
                         # Se falhou no fragmento, dá uma última chance no full_context apenas se for um match FORTE (@marca)
                         if not (re.search(rf"@{brand_norm}", full_context_norm)):
                            with open(log_path, "a", encoding="utf-8") as fl: fl.write("RESULTADO: 🚫 BLOQUEADO (Sem vínculo atual claro ou marca distante do nome)\n")
                            print(f"      [BLOQUEIO] 🚫 Sem vínculo explícito com {brand_name} no fragmento")
                            continue

                    if other_company_match:
                        other_comp = other_company_match.group(2).strip()
                        other_comp_low = other_comp.lower()
                        not_companies = ["setor", "área", "area", "departamento", "equipe", "time", "gerente", "coordenador", "especialista", "comprador", "silva", "santos", "oliveira", "souza", "lima", "ferreira", "da", "de", "do", "das", "dos", "sourcing", "purchasing", "procurement", "supply", "sumaré", "sumare", "campinas", "brasil", "brazil", "rmc", "reconhecimento", "internacional", "placas", "confiáveis", "validadas", "comunidade", "projeto", "organização", "finanças", "vendas", "marketing", "engenharia", "ti", "it", "rh", "hr", "linkedin", "administração", "gestão", "comercial", "operacional"]
                        
                        # ANTI-NAME-FS: Se a "empresa" achada for parte do nome do candidato, ignora
                        is_part_of_name = any(n_part.lower() == other_comp_low for n_part in name.split())
                        
                        is_target = brand_norm in other_comp_low or brand_name.lower() in other_comp_low
                        is_noise = any(other_comp_low.startswith(sw) or sw in other_comp_low.split() for sw in not_companies) or is_part_of_name
                        
                        # Se achou outra empresa, mas ela está LONGE do nome (indicando que é outra pessoa no snippet), ignoramos o bloqueio
                        try:
                            other_idx = words.index(other_comp_low.split()[0])
                            is_far_other = abs(name_idx - other_idx) > 10
                        except:
                            is_far_other = False

                        if not is_target and not is_noise and not is_far_other:
                             with open(log_path, "a", encoding="utf-8") as fl: fl.write(f"RESULTADO: 🚫 BLOQUEADO (Outra Empresa: {other_comp})\n")
                             print(f"      [BLOQUEIO] 🚫 Vínculo ATUAL com outra empresa detectado: '{other_comp}'")
                             continue

                    # 🛡️ 2. FILTRO DE DEPARTAMENTO E PORTAIS (BLOCKLIST)
                    bad_match = None
                    for bad in blocklist:
                        if len(bad) <= 4:
                            if re.search(rf"\b{bad}\b", context_to_check):
                                bad_match = bad; break
                        elif bad in context_to_check:
                            bad_match = bad; break

                    if bad_match:
                        # Double check: Se o termo proibido está no fragmento do candidato, bloqueia.
                        # Mas se o candidato tem um cargo de suprimentos CLARO no mesmo fragmento, reconsidera.
                        is_strong_procurement = any(kw in context_to_check for kw in ["compras", "purchas", "procurement", "buyer", "packaging", "sourcing"])
                        if not is_strong_procurement:
                            with open(log_path, "a", encoding="utf-8") as fl: fl.write(f"RESULTADO: 🚫 BLOQUEADO (Blocklist no fragmento: {bad_match})\n")
                            print(f"      [BLOQUEIO] 🚫 Fora de Escopo/Blocklist (Termo: '{bad_match}')")
                            continue

                    # 🛡️ 3. FILTRO DE QUALIDADE (PROCUREMENT/SUPPLY CORE)
                    # Expandido para incluir variações de gênero (comprador/a) e termos singulares
                    supply_keywords = ["compras", "comprador", "compradora", "purchas", "sourcin", "supply", "suprimento", "suprimentos", "logística", "materials", "materiais", "buyer", "planner", "procurement", "estoque", "almoxarife", "almoxarifado", "warehouse", "packaging", "embalagem", "sourcing", "expedição"]
                    
                    # Verificamos no contexto relevante primeiro, depois no geral (início)
                    is_procurement = any(kw in context_to_check for kw in supply_keywords) or any(kw in full_context[:200] for kw in supply_keywords)
                    
                    if not is_procurement:
                        with open(log_path, "a", encoding="utf-8") as fl: fl.write("RESULTADO: 🚫 BLOQUEADO (Não relacionado a Suprimentos)\n")
                        print(f"      [BLOQUEIO] 🚫 Atividade não relacionada a Suprimentos")
                        continue

                    # 🛡️ 4. FILTRO DE LOCALIZAÇÃO (STRICT se fornecido)
                    if loc_norm and loc_norm not in full_context_norm:
                        rmc_cluster = ["campinas", "hortolandia", "americana", "paulinia", "valinhos", "vinhedo", "indaiatuba", "rmc", "metro de campinas"]
                        is_far_away = re.search(r"\b(curitiba|manaus|rio de janeiro|bh|belo horizonte|waterloo|london|usa|florida)\b", full_context_norm)
                        is_nearby = any(city in full_context_norm for city in rmc_cluster) if loc_norm in rmc_cluster + ["sumare"] else False
                        
                        if not any(kw in full_context_norm for kw in ["brasil", "brazil", "remote", "remoto"]) and not is_nearby:
                            if is_far_away:
                                with open(log_path, "a", encoding="utf-8") as fl: fl.write("RESULTADO: 🚫 BLOQUEADO (Localização Incompatível)\n")
                                print(f"      [BLOQUEIO] 🚫 Localização incompatível (Detectado outra região no contexto)")
                                continue
                            else:
                                with open(log_path, "a", encoding="utf-8") as fl: fl.write("RESULTADO: ⚠️ AVISO (Localização duvidosa, mantido pela query)\n")
                                print(f"      [AVISO] ⚠️ Localização não explícita no snippet, mas mantendo pela query geo-localizada.")

                    # Anti-Ex-Funcionário (Palavras-chave e Dates)
                    is_ex = any(kw in full_context for kw in ["ex-", "former", "anterior", "trabalhou"])
                    has_end_date = re.search(rf"\b({core_company_name}|{brand_name.lower()})\b.*?\d{{4}}\s*[–-]\s*\d{{4}}", full_context, re.IGNORECASE)
                    
                    if (is_ex or has_end_date) and not any(kw in full_context for kw in ["atualmente", "atua na", "since", "desde", "presente", "present", "o momento"]):
                        with open(log_path, "a", encoding="utf-8") as fl: fl.write("RESULTADO: 🚫 BLOQUEADO (Ex-Funcionário detectado)\n")
                        print(f"      [BLOQUEIO] 🚫 Ex-Funcionário detectado (Palavra-chave ou Data de Término)")
                        continue

                    # SE PASSOU POR TUDO:
                    with open(log_path, "a", encoding="utf-8") as fl: fl.write("RESULTADO: ✅ APROVADO\n")

                    # 💎 HIGH-PRECISION ROLE EXTRACTION
                    # Tentativa 1: Do Título (Costuma ser mais limpo se não for amontoado)
                    role_candidate = ""
                    if "..." not in title.split(name)[-1]: # Se o título não parece amontoado logo após o nome
                        t_parts = re.split(r"[\-–|]", title)
                        for tp in t_parts:
                            tp_low = tp.lower()
                            if name.lower() not in tp_low and not any(c in tp_low for c in [core_company_name, brand_name.lower()]):
                                if any(kw in tp_low for kw in supply_keywords + ["manager", "lead", "diret", "gerente", "analista", "especialista"]):
                                    role_candidate = tp.strip()
                                    break
                    
                    # Tentativa 2: Do fragmento validado (context_to_check)
                    if not role_candidate:
                        clean_role = context_to_check
                        # Remove lixo de UI do LinkedIn
                        clean_role = re.sub(r"(veja o perfil|nolinkedin|uma comunidade|1 bilhão|conexões|links?|perfil|experiência|localidade).*$", "", clean_role, flags=re.IGNORECASE).strip()
                        # Remove o nome e empresa
                        for n_part in name.split():
                            if len(n_part) > 2: clean_role = re.sub(rf"\b{n_part}\b", "", clean_role, flags=re.IGNORECASE)
                        clean_role = re.sub(rf"\b({core_company_name}|{brand_name.lower()}|{brand_name})\b", "", clean_role, flags=re.IGNORECASE)
                        
                        # Tenta pegar apenas a parte que soa como cargo (antes de preposições de local/empresa)
                        clean_role = re.split(r"\b(em|na|no|at|da|desde|since)\b", clean_role, flags=re.IGNORECASE)[0]
                        role_candidate = clean_role.strip()

                    # Limpeza final de caracteres especiais
                    role_candidate = re.sub(r"[\-\–|·:…\.]", " ", role_candidate).strip()
                    role_candidate = re.sub(r"\s+", " ", role_candidate)
                    
                    if not role_candidate or len(role_candidate) < 4 or any(w in role_candidate.lower() for w in ["comunidade", "perfil no"]):
                        role_candidate = "Especialista em Suprimentos" 
                    
                    role = role_candidate.title()[:65]
                    # 🏆 SMART SENIORITY EXTRACTION
                    seniority_score = 1
                    role_low = role.lower()
                    if any(k in role_low for k in ["vp", "vice president", "diretor", "director", "direção"]): seniority_score = 4
                    elif any(k in role_low for k in ["gerente", "manager", "head"]): seniority_score = 3
                    elif any(k in role_low for k in ["coordena", "supervis", "lead", "sênior", "senior"]): seniority_score = 2
                    
                    seen_urls.add(href)
                    f, l = name.lower().split()[0], name.lower().split()[-1]
                    clean_domain = domain.lstrip("@")
                    batch.append({
                        "id": f"node_{href.split('/in/')[-1].replace('/', '_')}", # ID Robusto baseado no LinkedIn Slug
                        "name": name.title(),
                        "role": role, 
                        "email": f"{f}.{l}@{clean_domain}",
                        "linkedin": href,
                        "company": brand_name,
                        "type": "operational", # Pode ser refinado se necessário
                        "seniority": seniority_score
                    })
                    print(f"      [APROVADO] ✅ Candidato: {name} ({role}) | Nível: {seniority_score}")
                return batch

            batch_employees = process_results(results)
            
            # Fallback (Busca Nacional)
            if not batch_employees and loc_clean in query:
                print(f"  [B2B] ⚠️ Reforçando busca nacional...")
                fb_query = query.replace(loc_clean, "").replace("  ", " ").strip()
                try:
                    with DDGS() as ddgs:
                        fb_res = list(ddgs.text(fb_query, region="br-pt", max_results=30))
                        batch_employees = process_results(fb_res)
                except: pass

            if batch_employees:
                print(f"[B2B Engine] 🚀 Despachando lote de {len(batch_employees)} nomes.")
                yield batch_employees
                
    except Exception as e:
        print("[Custom B2B Engine Error]:", e)
    return
