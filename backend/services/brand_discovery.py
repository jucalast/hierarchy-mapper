import re
import html
from typing import List, Dict, Optional
from .search_engine import get_duck_results
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
                    name = data.get("razao_social") or data.get("nome") or data.get("fantasia")
                    email = data.get("email")
                    
                    if name:
                        final_result["name"] = name
                        final_result["address"] = f"{data.get('logradouro')}, {data.get('numero')} - {data.get('bairro')}, {data.get('municipio')} - {data.get('uf')}"
                        final_result["status"] = data.get("descricao_situacao_cadastral") or data.get("situacao") or "ATIVO"
                        final_result["email"] = email
                        final_result["success"] = True
                        
                        if email:
                            print(f"[BrandDiscovery] 📧 E-mail oficial encontrado: {email}")
                            return final_result
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
    from .search_engine import get_duck_results
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

async def discover_company_brand(cnpj: str, domain: str = "", raw_name: str = "") -> Dict:
    """
    Orquestra a descoberta da marca oficial via CNPJ, Domínio e Nome.
    """
    processed_cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "")
    
    # 🕵️ PASSO 0: Check Cache (Banco Local)
    from .database import async_session, Organization
    from sqlalchemy import select
    
    detected_domain = None
    search_name = raw_name
    cached = None
    
    try:
        async with async_session() as session:
            stmt = select(Organization).where(Organization.cnpj.like(f"%{processed_cnpj}%"))
            res = await session.execute(stmt)
            cached = res.scalars().first()
            
            if cached:
                print(f"[BrandDiscovery] 📦 Cache Hit (DB): {cached.name}")
                search_name = cached.name
                domain = cached.domain or domain
                official_data = {"success": True, "name": cached.name, "email": None}
            else:
                # PASSO 1: Descobrir via API se não estiver no banco
                official_data = await get_corporate_data(processed_cnpj)
                
                # 💾 SALVAR NO CACHE (Persistência)
                if official_data.get("success"):
                    search_name = official_data.get("name")
                    print(f"[BrandDiscovery] 💾 Salvando novo cache para: {search_name}")
                    
                    # Tenta pegar domínio antes de salvar
                    temp_domain = domain
                    if not temp_domain:
                        temp_domain = await extract_domain_from_email(official_data.get("email"))
                    
                    new_org = Organization(
                        cnpj=processed_cnpj,
                        name=search_name,
                        domain=temp_domain or "",
                        address=official_data.get("address"),
                        description="Auto-discovered via BrandDiscovery"
                    )
                    session.add(new_org)
                    await session.commit()
                    cached = new_org # Marca como "em cache" para o restante da função
        
        if official_data.get("success"):
            search_name = official_data.get("name")
            
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

    # 🔍 PASSO 2: Buscas Multi-Ângulo (Agora com Nome Real)
    from .search_engine import get_duck_results
    search_queries = [
        f'"{processed_cnpj}" site:br.linkedin.com',
        f'linkedin "{search_name}"',
        f'"{search_name} {domain}" site:br.linkedin.com' if domain else None,
        f'"{search_name}" br.linkedin.com/company'
    ]
    
    candidates_raw = []
    for query in filter(None, search_queries):
        res = await get_duck_results(query, max_results=10)
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
            "url": cand["url"]
        })

    return {
        "brand": valid_names[0] if valid_names else raw_name.title(),
        "detected_domain": detected_domain,
        "alternatives": top_alternatives
    }
