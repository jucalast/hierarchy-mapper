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
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    # Normalização básica (ReceitaWS usa nomes de campos diferentes as vezes)
                    name = data.get("razao_social") or data.get("nome") or data.get("fantasia")
                    email = data.get("email")
                    
                    if name:
                        final_result["name"] = name
                        final_result["address"] = f"{data.get('logradouro')}, {data.get('numero')} - {data.get('bairro')}, {data.get('municipio')} - {data.get('uf')}"
                        final_result["status"] = data.get("descricao_situacao_cadastral") or data.get("situacao") or "ATIVO"
                        final_result["email"] = email
                        final_result["success"] = True
                        
                        # Se achamos e-mail, podemos parar (é o dado mais precioso aqui)
                        if email:
                            return final_result
            except:
                continue
                
    return final_result

async def discover_company_brand(cnpj: str, domain: str = "", raw_name: str = "") -> Dict:
    """
    Orquestra a descoberta da marca oficial via CNPJ, Domínio e Nome.
    """
    processed_cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "")
    
    # 🕵️ PASSO 1: Descobrir o NOME REAL pelo CNPJ (OSINT Nível 1)
    try:
        db_name = await get_corporate_name(processed_cnpj)
        print(f"[BrandDiscovery] CNPJ Identificado: {db_name}")
        search_name = db_name
    except Exception:
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
        "alternatives": top_alternatives
    }
