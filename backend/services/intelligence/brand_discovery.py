import re
import html
from typing import List, Dict, Optional
from services.hierarchy.search_engine import get_duck_results
import httpx
import time
import random

def clean_brand_name(raw_name: str) -> str:
    """
    Limpa o nome extraído do LinkedIn, preservando espaços e separando CamelCase.
    """
    # 1. Divide em separadores comuns e pega o primeiro pedaço (Mantendo hífens internos)
    clean = re.split(r"[|–•·:]", raw_name)[0].strip()
    
    # 2. CamelCase inteligente (KaeferRip -> Kaefer Rip)
    # Só funciona se não dermos .lower() antes
    clean = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean)
    clean = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', clean)
    
    # 3. Remove termos comuns e ruído (Case Insensitive)
    noise = [
        r"on linkedin", r"\| linkedin", r": overview", r"- linkedin", 
        r"linkedin brasil", r"linkedin brazil", r"brazil", r"brasil", 
        r"\d+\s+followers", r"\d+\s+seguidores", r"connections", r"see\s+more",
        r"followers$", r"seguidores$", r"vagas", r"jobs", r"trabalhe conosco",
        r"www\.[^\s]+", r"\.com(\.br)?", r"\.ind\.br", r"\.net",
        r"\bltda\b", r"\bs\.?a\.?\b", r"\bs/a\b", r"\bcia\b", r"\beireli\b"
    ]
    
    for pattern in noise:
        clean = re.sub(pattern, " ", clean, flags=re.IGNORECASE)
    
    # 4. Remove múltiplos espaços e pontuações
    clean = re.sub(r"[^a-zA-Z0-9À-ÿ\s]", " ", clean)
    clean = " ".join(clean.split())
    
    # Validação Básica
    return clean.title() if len(clean) > 2 else raw_name.title()

def fetch_linkedin_logo(url: str) -> Optional[str]:
    """
    Tenta extrair o logo real do LinkedIn fingindo ser um bot de 
    redes sociais (geralmente permitido por eles para previews).
    """
    if "/company/" not in url: return None
    
    # User-Agent que o LinkedIn costuma deixar passar para ler meta-tags (Social Crawlers)
    social_headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url, headers=social_headers)
            if resp.status_code == 200:
                # Procura a tag <meta property="og:image" content="...">
                match = re.search(r'<meta property="og:image" content="(https://media\.licdn\.com/dms/image/[^"]+)"', resp.text)
                if match:
                    # Limpa a URL de entidades HTML (ex: &amp; -> &)
                    return html.unescape(match.group(1))
    except:
        pass
    return None

async def get_corporate_data(cnpj: str) -> Dict:
    """
    Busca Nome Oficial, Endereço, Status e Email por CNPJ em múltiplas camadas OSINT.
    Tenta todas as camadas para garantir que pegamos o e-mail se disponível.
    """
    clean_cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "")
    final_result = {
        "name": f"Empresa (CNPJ: {cnpj})", 
        "address": "Brasil", 
        "status": "ATIVO", 
        "email": None,
        "partners": [], # Lista de Sócios
        "success": False
    }
    
    layers = [
        f"https://brasilapi.com.br/api/cnpj/v1/{clean_cnpj}",
        f"https://minhareceita.org/{clean_cnpj}",
        f"https://receitaws.com.br/v1/cnpj/{clean_cnpj}"
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in layers:
            try:
                print(f"[BrandDiscovery] 📡 Consultando: {url.split('/')[2]}...")
                resp = await client.get(url)
                if resp.status_code == 200:
                    print(f"[BrandDiscovery] 🟢 Sucesso via {url.split('/')[2]}")
                    data = resp.json()
                    name = data.get("fantasia") or data.get("razao_social") or data.get("nome")
                    fantasy = data.get("fantasia")
                    email = data.get("email")
                    phone = data.get("telefone") or data.get("tel")
                    
                    # Normaliza o QSA (Sócios)
                    qsa_raw = data.get("qsa") or []
                    partners = []
                    for s in qsa_raw:
                        partners.append({
                            "name": s.get("nome_socio") or s.get("nome"),
                            "role": s.get("qualificacao_socio") or s.get("qual") or "Sócio"
                        })

                    if name:
                        final_result["name"] = name
                        final_result["fantasy"] = fantasy
                        final_result["address"] = f"{data.get('logradouro')}, {data.get('numero')} - {data.get('bairro')}, {data.get('municipio')} - {data.get('uf')}"
                        final_result["status"] = data.get("descricao_situacao_cadastral") or data.get("situacao") or "ATIVO"
                        final_result["email"] = email
                        final_result["phone"] = phone
                        final_result["partners"] = partners
                        final_result["success"] = True
                        
                        # Continua para as próximas APIs para enriquecer mais dados
                        pass
                else:
                    print(f"[BrandDiscovery] 🔴 Erro {resp.status_code} via {url.split('/')[2]}")
            except Exception as e:
                print(f"[BrandDiscovery] ⚠️ Falha na conexão com {url.split('/')[2]}: {str(e)}")
                continue
                
    return final_result

async def extract_domain_from_email(email: Optional[str]) -> Optional[str]:
    """Extrai domínio corporativo de um e-mail, ignorando provedores genéricos."""
    if not email or "@" not in str(email): return None
    
    parts = str(email).split("@")
    if len(parts) <= 1: return None
    
    domain_part = parts[-1].lower().strip()
    generic = [
        "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br",
        "uol.com.br", "terra.com.br", "ig.com.br", "bol.com.br", "icloud.com",
        "contabilidade", "consultoria", "advocacia", "me.com", "outlook.com.br",
        "uol.com", "live.com", "msn.com", "apple.com"
    ]
    if not any(gen in domain_part for gen in generic) and "." in domain_part:
        return domain_part
    return None

async def discover_domain_via_clearbit(name: str) -> Optional[str]:
    """Tenta descobrir o domínio via API do Clearbit Autocomplete."""
    try:
        # Pega apenas os 2 primeiros termos para busca mais precisa
        search_term = " ".join(name.split()[:2])
        url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={search_term}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    domain = data[0].get("domain")
                    if domain:
                        return domain
    except Exception as e:
        print(f"[BrandDiscovery] Erro Clearbit: {e}")
    return None

async def discover_domain_osint(name: str) -> Optional[str]:
    """Tenta descobrir o domínio oficial da empresa via busca OSINT se as APIs falharem."""
    from services.hierarchy.search_engine import get_duck_results
    queries = [f'"{name}" official website', f'site oficial "{name}"']
    
    for query in queries:
        try:
            results = await get_duck_results(query, max_results=3)
            for r in results:
                url = r.get("url") or r.get("link")
                if not url: continue
                
                # Ignorar redes sociais na busca por site oficial
                if any(x in url for x in ["linkedin.com", "facebook.com", "instagram.com", "youtube.com", "twitter.com", "cnpj.biz", "econodata.com.br"]):
                    continue
                
                # Extrair domínio da URL
                match = re.search(r'https?://([^/]+)', url)
                if match:
                    domain = match.group(1).replace("www.", "").lower()
                    if "." in domain:
                        return domain
        except:
            continue
    return None

async def discover_company_brand(cnpj: str = "", domain: str = "", raw_name: str = "", force: bool = False) -> Dict:
    """
    Orquestra a descoberta da marca oficial via CNPJ, Domínio e Nome.
    """
    from core.database import async_session
    from models import Organization, Employee
    from sqlalchemy import select, or_, func

    processed_cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "") if cnpj else None
    
    # 🕵️ PASSO 0: Check Cache (Banco Local)
    detected_domain = None
    search_name = raw_name
    cached = None
    official_data = {}
    cache_hit = False
    partners = []
    candidates_raw = []
    
    # Só busca no cache se NÃO for um force_refresh
    if not force:
        try:
            async with async_session() as session:
                # 🏺 Busca por CNPJ (Prioridade 1) ou por Nome (Prioridade 2 - Case Insensitive)
                filters = []
                if processed_cnpj and len(processed_cnpj) >= 11: # Garante que é um CNPJ/CPF válido
                     filters.append(Organization.cnpj == processed_cnpj)
                
                if raw_name:
                    filters.append(func.lower(Organization.name) == raw_name.lower())

                if filters:
                    stmt = select(Organization).where(or_(*filters))
                    res = await session.execute(stmt)
                    cached = res.scalars().first()
                
                if cached:
                    # 🛑 VALIDAÇÃO DE SEGURANÇA: Só aceita o cache se o nome for parecido ou se o CNPJ bater
                    cached_name = cached.name.lower()
                    requested_name = raw_name.lower() if raw_name else ""
                    
                    # Se achou por CNPJ, é match total. Se achou por nome, comparamos.
                    is_cnpj_match = processed_cnpj and cached.cnpj == processed_cnpj
                    is_name_match = requested_name and (requested_name in cached_name or cached_name in requested_name)
                    
                    if is_cnpj_match or is_name_match:
                        print(f"[BrandDiscovery] 📦 Cache Hit Validado: {cached.name}")
                        search_name = cached.name
                        domain = cached.domain or domain
                    else:
                        print(f"[BrandDiscovery] ⚠️ Cache ignorado (Nome divergente): {cached.name} vs {raw_name}")
                        cached = None # Força nova busca
                    
                    if cached:
                        # VÍNCULO IMEDIATO
                        if processed_cnpj and not cached.cnpj:
                            print(f"[BrandDiscovery] 🔗 Atrelando CNPJ {processed_cnpj} ao registro existente.")
                            cached.cnpj = processed_cnpj
                            await session.commit()
                        
                        # Busca os sócios
                        stmt_p = select(Employee).where(Employee.company_id == cached.id, Employee.department == "Quadro de Sócios (QSA)")
                        res_p = await session.execute(stmt_p)
                        db_partners = res_p.scalars().all()
                        partners = [{"name": p.name, "role": p.role} for p in db_partners]
                        
                        if not partners and processed_cnpj:
                            official_data = await get_corporate_data(processed_cnpj)
                            if official_data.get("success"):
                                partners = official_data.get("partners", [])
                                for p in partners:
                                    new_p = Employee(
                                        name=p.get("name"),
                                        role=p.get("role", "Sócio"),
                                        department="Quadro de Sócios (QSA)",
                                        seniority=6,
                                        company_id=cached.id
                                    )
                                    session.add(new_p)
                                await session.commit()
                        
                        cache_hit = True
                        candidates_raw.append({
                            "name": cached.name,
                            "url": cached.linkedin_url or f"https://www.linkedin.com/company/{cached.name.lower().replace(' ', '-')}",
                            "followers": "Salvo no Banco"
                        })
        except Exception as e:
            print(f"[BrandDiscovery] Cache Check error: {e}")

    # PASSO 1: Descobrir via API se não tiver no banco ou se for force
    if not cache_hit:
        official_data = await get_corporate_data(processed_cnpj)
        if official_data.get("success"):
            search_name = official_data.get("fantasy") or official_data.get("name")
            print(f"[BrandDiscovery] 📡 Dados oficiais extraídos: {search_name}")
            brand_partners = [{"name": p.get("name"), "role": p.get("role", "Sócio")} for p in official_data.get("partners", [])]
            partners = brand_partners
    
    try:
        if official_data.get("success"):
            search_name = official_data.get("fantasy") or official_data.get("name")
            
            # Tenta pegar domínio do email se não foi passado um domínio
            if not domain:
                detected_domain = await extract_domain_from_email(official_data.get("email"))
                if detected_domain:
                    domain = detected_domain
                else:
                    # 🚀 CAMADA 2: Clearbit
                    detected_domain = await discover_domain_via_clearbit(search_name)
                    if not detected_domain:
                        detected_domain = await discover_domain_osint(search_name)
                    
                    if detected_domain:
                        domain = detected_domain
                        # Opcional: Atualizar o banco com o novo domínio descoberto
                        async with async_session() as session:
                            stmt = select(Organization).where(Organization.cnpj == processed_cnpj)
                            res = await session.execute(stmt)
                            db_org = res.scalars().first()
                            if db_org and not db_org.domain:
                                db_org.domain = detected_domain
                                await session.commit()
            else:
                search_name = raw_name or (domain.split(".")[0] if domain else "")
    except Exception as e:
        print(f"[BrandDiscovery] Erro na camada de descoberta oficial: {e}")
        search_name = raw_name or (domain.split(".")[0] if domain else "")
        if not search_name:
            raise ValueError("Não foi possível identificar a empresa.")

    # 🔍 PASSO 2: Buscas Multi-Ângulo (Padrão HUMANO - Evita 429)
    from services.hierarchy.search_engine import get_duck_results
    search_queries = [
        f'"{search_name}" linkedin oficial perfil',
        f'"{search_name}" linkedin company page',
        f'linkedin {search_name} {domain}' if domain else None,
        f'página da empresa {search_name} linkedin'
    ]
    
    # candidates_raw já inicializado no topo
    for query in filter(None, search_queries):
        res = await get_duck_results(query, max_results=10, is_company=True)
        for r in res:
            title = r.get("title", "")
            snippet = (r.get("body") or r.get("snippet") or "").lower()
            name = clean_brand_name(title)
            
            # Extração de Seguidores
            followers = "N/A"
            f_match = re.search(r"([\d\.,k\+]+)\s+(followers|seguidores)", snippet)
            if f_match:
                followers = f_match.group(1).upper()

            if name: 
                print(f"      [BrandDiscovery] ✨ Candidato encontrado: {name} -> {r.get('href', '')}")
                candidates_raw.append({
                    "name": name, 
                    "url": r.get("href", ""),
                    "followers": followers
                })
    
    # ... (Decisão e Scoring permanecem os mesmos)

    # 🎯 Decisão e Scoring
    if not candidates_raw:
        return {"brand": raw_name.title(), "alternatives": []}
        
    unique_candidates = {}
    for c in candidates_raw:
        name = c["name"]
        if name not in unique_candidates or (c["followers"] != "N/A" and unique_candidates[name]["followers"] == "N/A"):
            unique_candidates[name] = c

    def get_brand_score(name: str) -> int:
        c = unique_candidates[name]
        score = 0
        name_norm = name.lower()
        url = c["url"]
        
        corp_dna = ["friction", "tmd", "ltda", "ind", "freios", "solutions", "sistemas", "tecnologia", "brasil", "brazil", "group", "holdings"]
        
        if "/company/" in url: score += 150
        if any(dna in name_norm for dna in corp_dna): score += 100
        if " " in name: score += 40
        if c["followers"] != "N/A": score += 80
        
        surnames = ["santos", "silva", "oliveira", "souza", "pereira", "costa", "ferreira", "lima", "natacci", "rodrigues"]
        words = name_norm.split()
        if any(s in words for s in surnames) and not any(dna in name_norm for dna in corp_dna):
            score -= 400
        
        if len(name) > 35: score -= 100
        return score

    sorted_names = sorted(unique_candidates.keys(), key=get_brand_score, reverse=True)
    valid_names = [n for n in sorted_names if get_brand_score(n) > 0]
    
    if not valid_names:
        valid_names = [n for n in sorted_names if get_brand_score(n) > -50]
    
    top_alternatives = []
    for n in valid_names[:8]: # Pega os Top 8 para buscar logos reais
        cand = unique_candidates[n]
        # 🧪 Tenta buscar o logo REAL no LinkedIn
        real_logo = fetch_linkedin_logo(cand["url"])
        
        if real_logo:
            cand["logo"] = real_logo
        else:
            # Fallback para o avatar premium se o real falhar
            initials = "".join([w[0] for w in n.split()[:2]]).upper()
            cand["logo"] = f"https://ui-avatars.com/api/?name={initials}&background=6366f1&color=fff&bold=true&rounded=true&size=128"
            
        top_alternatives.append({
            "name": cand["name"],
            "followers": cand["followers"],
            "logo": cand["logo"],
            "url": cand["url"],
            "partners": partners
        })

    # 🏺 Persistência removida: Agora somente via Rota /Confirm após escolha do Usuário

    return {
        "brand": valid_names[0] if valid_names else (search_name or raw_name.title()),
        "detected_domain": detected_domain or domain,
        "partners": partners or official_data.get("partners", []), 
        "alternatives": top_alternatives,
        "cache_hit": cache_hit,
        "linkedin_url": top_alternatives[0]["url"] if top_alternatives else ""
    }
