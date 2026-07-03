"""
Versão com streaming da descoberta de marcas.
Faz yield de cada candidato conforme é processado.
"""
from typing import AsyncGenerator, Dict, Optional
import asyncio
import random
from modules.intelligence.service.brand_discovery import (
    clean_brand_name, 
    fetch_linkedin_logo, 
    get_corporate_data,
    extract_domain_from_email,
    discover_domain_via_clearbit,
    discover_domain_osint
)
from modules.hierarchy.service.search_engine import get_duck_results
from core.infra.database import async_session
from models import Organization, Employee
from sqlalchemy import select, or_, func
import re

async def discover_company_brand_stream(
    cnpj: str = "",
    domain: str = "",
    raw_name: str = "",
    force: bool = False
) -> AsyncGenerator[Dict, None]:
    """
    Streaming version que faz yield de cada candidato conforme é encontrado.
    Mantém a mesma lógica de filtragem e seleção da versão original.
    """
    
    processed_cnpj = cnpj.replace(".", "").replace("/", "").replace("-", "") if cnpj else None
    detected_domain = None
    search_name = raw_name
    cached = None
    official_data = {}
    cache_hit = False
    partners = []
    candidates_raw = []
    
    # 🕵️ PASSO 0: Check Cache
    if not force:
        try:
            async with async_session() as session:
                filters = []
                if processed_cnpj and len(processed_cnpj) >= 11:
                    filters.append(Organization.cnpj == processed_cnpj)
                
                if raw_name:
                    filters.append(func.lower(Organization.name) == raw_name.lower())

                if filters:
                    stmt = select(Organization).where(or_(*filters))
                    res = await session.execute(stmt)
                    cached = res.scalars().first()
                
                if cached:
                    cached_name = cached.name.lower()
                    requested_name = raw_name.lower() if raw_name else ""
                    is_cnpj_match = processed_cnpj and cached.cnpj == processed_cnpj
                    is_name_match = requested_name and (requested_name in cached_name or cached_name in requested_name)
                    
                    if is_cnpj_match or is_name_match:
                        print(f"[BrandDiscovery] 📦 Cache Hit Validado (Stream): {cached.name}")
                        search_name = cached.name
                        domain = cached.domain or domain
                        cache_hit = True
                        
                        # Busca sócios
                        stmt_p = select(Employee).where(
                            Employee.company_id == cached.id,
                            Employee.department == "Quadro de Sócios (QSA)"
                        )
                        res_p = await session.execute(stmt_p)
                        db_partners = res_p.scalars().all()
                        partners = [{"name": p.name, "role": p.role} for p in db_partners]
                        
                        # Yield do candidato do cache
                        yield {
                            "type": "candidate",
                            "name": cached.name,
                            "url": cached.linkedin_url or f"https://www.linkedin.com/company/{cached.name.lower().replace(' ', '-')}",
                            "followers": "Salvo no Banco",
                            "logo": cached.logo_url or f"https://ui-avatars.com/api/?name={cached.name[:2]}&background=6366f1&color=fff&bold=true&rounded=true&size=128",
                            "partners": partners,
                            "source": "cache"
                        }
                        return  # Para streaming de cache
        except Exception as e:
            print(f"[BrandDiscovery] Cache error (Stream): {e}")

    # PASSO 1: Descoberta via API
    if not cache_hit:
        official_data = await get_corporate_data(processed_cnpj)
        if official_data.get("success"):
            search_name = official_data.get("fantasy") or official_data.get("name")
            print(f"[BrandDiscovery] 📡 Dados oficiais extraídos (Stream): {search_name}")
            partners = [{"name": p.get("name"), "role": p.get("role", "Sócio")} for p in official_data.get("partners", [])]
    
    # Fallback se busca de dados corporativos falhou e não temos nome
    if not search_name:
        search_name = raw_name or (domain.split(".")[0] if domain else "")
        
    if not search_name:
        raise ValueError("Não foi possível identificar o nome da empresa nem pelo CNPJ nem pelo Domínio.")

    # Descoberta de domínio
    try:
        if official_data.get("success") and not domain:
            detected_domain = await extract_domain_from_email(official_data.get("email"))
            if not detected_domain:
                detected_domain = await discover_domain_via_clearbit(search_name)
            if not detected_domain:
                detected_domain = await discover_domain_osint(search_name)
            if detected_domain:
                domain = detected_domain
    except Exception as e:
        print(f"[BrandDiscovery] Domain discovery error (Stream): {e}")

    # PASSO 2: Buscas Multi-Ângulo
    city = ""
    if official_data.get("address"):
        addr_parts = official_data.get("address").split(",")
        if len(addr_parts) > 1:
            city_part = addr_parts[-1].split("-")[0].strip()
            city = city_part
    
    # Extrai a marca curta (duas primeiras palavras significativas) para buscas diretas
    brand_tokens = search_name.split()
    meaningful_tokens = []
    for token in brand_tokens:
        if not any(corp_word == token.upper() for corp_word in ["LTDA", "S.A.", "INC", "LLC", "BRASIL", "BRAZIL", "DO", "DE", "DA", "E"]):
            meaningful_tokens.append(token)
            if len(meaningful_tokens) == 2:
                break
    brand_short = " ".join(meaningful_tokens).strip() if meaningful_tokens else search_name.split()[0]
    
    domain_base = domain.split(".")[0] if domain else ""
    
    search_queries = []
    if brand_short:
        search_queries.append(f'site:linkedin.com/company "{brand_short}"')
    if domain:
        search_queries.append(f'site:linkedin.com/company "{domain}"')
    elif domain_base and domain_base.lower() != brand_short.lower():
        search_queries.append(f'site:linkedin.com/company "{domain_base}"')
    search_queries.append(f'site:linkedin.com/company "{search_name}"')
    if brand_short:
        search_queries.append(f'"{brand_short}" Brasil linkedin')
    
    # Dicionário para rastrear candidatos únicos
    unique_candidates = {}
    
    # 🧪 Função de scoring (copiada da versão original)
    def get_brand_score(name: str) -> int:
        c = unique_candidates[name]
        score = 0
        name_norm = name.lower()
        url = c["url"].lower()
        
        # DNA Corporativo
        corp_dna = [
            "friction", "tmd", "ltda", "ind", "freios", "solutions", 
            "sistemas", "tecnologia", "technology", "technologies", 
            "brasil", "brazil", "group", "holdings", "quimica", "química", 
            "chemicals", "indústria", "comércio"
        ]
        
        if "/company/" in url or "/school/" in url: 
            score += 150
        if any(dna in name_norm for dna in corp_dna): 
            score += 100
        if " " in name: 
            score += 40
        if c["followers"] != "N/A": 
            score += 80

        clean_search = search_name.lower()
        simple_search = "".join(filter(str.isalnum, clean_search))
        simple_name = "".join(filter(str.isalnum, name_norm))
        
        if simple_search and simple_name:
            if simple_search in simple_name or simple_name in simple_search:
                score += 300
                if simple_search == simple_name:
                    score += 600
        
        # 🆕 SUPER BÔNUS: Se for um match exato com a marca curta (ex: "3M")
        if brand_short:
            brand_short_norm = brand_short.lower()
            simple_brand_short = "".join(filter(str.isalnum, brand_short_norm))
            if simple_brand_short == simple_name or name_norm.startswith(brand_short_norm):
                score += 1000  # Bônus gigante para matches exatos da marca!
        
        surnames = ["santos", "silva", "oliveira", "souza", "pereira", "costa", "ferreira", "lima", "natacci", "rodrigues"]
        words = name_norm.split()
        if any(s in words for s in surnames) and not any(dna in name_norm for dna in corp_dna):
            score -= 400
        
        if len(name) > 45: 
            score -= 150
            
        return score
    
    # Cada vez que encontramos um candidato, enriquecemos e fazemos yield
    print(f"[BrandDiscovery] 🔍 Começando buscas por perfis (Stream)...")
    
    candidate_count = 0
    active_queries = list(dict.fromkeys([q for q in search_queries if q]))
    has_high_confidence = False
    
    print(f"[BrandDiscovery] 🚀 Iniciando buscas concorrentes por perfis (Stream)...")
    
    # Executa todas as buscas em paralelo para evitar timeout.
    # timeout=22s: get_duck_results() já tem seu próprio timeout interno de ~20s por
    # tentativa de DDG (_DDG_SUBPROCESS_TIMEOUT + 5.0) antes de cair no fallback Bing —
    # com um timeout externo menor que isso (era 12s), essa chamada sempre matava a busca
    # antes do DDG estourar seu próprio timeout, sem o fallback Bing ter chance de rodar.
    tasks = [
        asyncio.wait_for(get_duck_results(query, max_results=15, is_company=True), timeout=22.0)
        for query in active_queries
    ]
    
    for coro in asyncio.as_completed(tasks):
        try:
            res = await coro
            
            for r in res:
                title = r.get("title", "")
                snippet = (r.get("body") or r.get("snippet") or "").lower()
                name = clean_brand_name(title)
                
                # Extração de seguidores
                followers = "N/A"
                f_match = re.search(r"([\d\.,k\+]+)\s+(followers|seguidores)", snippet)
                if f_match:
                    followers = f_match.group(1).upper()
                
                url = r.get("href") or r.get("link") or r.get("url") or ""
                
                if name and url and "/company/" in url.lower():
                    if name not in unique_candidates:
                        # Registro inicial (bloqueia duplicatas antes do await de imagem)
                        unique_candidates[name] = {"name": name, "url": url, "followers": followers, "logo": None}
                        
                        # Tenta buscar logo (rápido)
                        try:
                            # Adiciona um pequeno delay aleatório para não disparar muitos fetches de logo ao mesmo tempo
                            await asyncio.sleep(random.uniform(0.1, 0.5))
                            real_logo = fetch_linkedin_logo(url)
                            if real_logo:
                                unique_candidates[name]["logo"] = real_logo
                            else:
                                initials = "".join([w[0] for w in name.split()[:2]]).upper()
                                unique_candidates[name]["logo"] = f"https://ui-avatars.com/api/?name={initials}&background=6366f1&color=fff&bold=true&rounded=true&size=128"
                        except:
                            initials = "".join([w[0] for w in name.split()[:2]]).upper()
                            unique_candidates[name]["logo"] = f"https://ui-avatars.com/api/?name={initials}&background=6366f1&color=fff&bold=true&rounded=true&size=128"
                        
                        candidate_count += 1
                        
                        # Calcula score na hora para saber se a confiança é alta (para referência futura, sem early exit)
                        score = get_brand_score(name)
                        if score >= 900:
                            has_high_confidence = True
                            
                        yield {
                            "type": "candidate",
                            "index": candidate_count,
                            "name": name,
                            "url": url,
                            "followers": followers,
                            "logo": unique_candidates[name]["logo"],
                            "partners": partners,
                            "source": "search_concurrent"
                        }
        except Exception as e:
            # str(e) vem vazio para asyncio.TimeoutError — inclui o tipo pra não perder
            # o diagnóstico (era exatamente esse timeout que estava sendo disparado aqui).
            print(f"[BrandDiscovery] Concurrency query error: {type(e).__name__}: {e}")

    # 🏆 ORDENAÇÃO FINAL POR SCORE
    scored_candidates = []
    for name in unique_candidates.keys():
        score = get_brand_score(name)
        scored_candidates.append((name, score))
    
    # Ordena pelos scores (maiores primeiro)
    sorted_candidates = sorted(scored_candidates, key=lambda x: x[1], reverse=True)
    
    # 🎯 Yield dos top 12 candidatos em ordem de score
    top_alternatives = []
    for name, score in sorted_candidates[:12]:
        cand = unique_candidates[name]
        top_alternatives.append({
            "name": cand["name"],
            "followers": cand["followers"],
            "logo": cand["logo"],
            "url": cand["url"],
            "partners": partners,
            "score": score,
            "source": "sorted"
        })
    
    # Sinal de conclusão com os top candidatos ordenados
    yield {
        "type": "complete",
        "total_candidates": len(unique_candidates),
        "search_name": search_name,
        "detected_domain": detected_domain or domain,
        "top_alternatives": top_alternatives
    }

