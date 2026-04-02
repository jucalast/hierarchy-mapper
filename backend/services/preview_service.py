import httpx
import re
from typing import Dict, Optional
from bs4 import BeautifulSoup
from services.role_engine import role_engine

async def get_url_preview(url: str, role_hint: str = "", company_hint: str = "") -> Dict:
    """
    Simula um crawler de rede social para extrair metadados Open Graph do LinkedIn.
    Usa dicas do sistema (hints) como fallback de alta precisão.
    """
    if not url:
        return {"error": "URL missing"}

    # Drible do Erro 999: Simular o Crawler do Facebook que o LinkedIn sempre permite para previews sociais
    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Extraindo Metadados OG
                def get_tag(attr, val):
                    tag = soup.find('meta', attrs={attr: val})
                    return tag.get('content') if tag else None

                og_title = get_tag('property', 'og:title') or get_tag('name', 'title') or ""
                og_desc = get_tag('property', 'og:description') or get_tag('name', 'description') or ""
                
                # Fatiamento inteligente do Título
                # 1. Desgruda CamelCase (ex: CompradoraWesley -> Compradora Wesley)
                og_title = re.sub(r'([a-z])([A-Z])', r'\1 \2', og_title or "")
                
                title_clean = og_title.replace(" | LinkedIn", "").replace(" | LinkedIn Profile", "").strip()
                parts = [p.strip() for p in re.split(r'[-–|:·•]', title_clean) if p.strip()]
                
                # Filtra ruído e remove duplicidade (caso o nome se repita no título)
                noise = ["linkedin", "linked in", "linked", "perfil", "profile", "overview", "followers", "conexões", "see more"]
                parts = [p.strip() for p in parts if p.strip().lower() not in noise]
                
                # 🧼 REMOVE DUPLICATAS: Ex: "Renilton S. Carvalho - Renilton S. Carvalho" -> "Renilton S. Carvalho"
                unique_parts = []
                for p in parts:
                    if p not in unique_parts:
                        unique_parts.append(p)
                parts = unique_parts

                name = parts[0] if len(parts) > 0 else "Colaborador"
                role = "Professional"
                # 1. Títulos de Cargo Comuns (Dicionário de Identificação)
                job_keywords = [
                    "comprador", "buyer", "procurement", "supply chain", "gerente", "manager", "diretor", "director",
                    "coordenador", "coordinator", "analista", "analyst", "supervisor", "especialista", "specialist",
                    "logística", "logistics", "compras", "sourcing", "planner", "planejamento", "mestre", "lead", 
                    "head", "vp", "chief", "administrador", "engineer", "engenheiro", "clerk", "auxiliar", "assistente",
                    "strategic sourcing"
                ]

                name = parts[0] if len(parts) > 0 else "Colaborador"
                role = "Professional"
                company = company_hint or "N/A"
                # NOVO: Coletor de Candidatos (para escolher o melhor depois)
                role_candidates = []

                # --- [ COLETA DE FONTES BRUTAS ] ---
                raw_sources = [og_title, og_desc, resp.text]
                
                # --- [ RESGATE VIA BUSCA (duckduckgo) para alimentar a IA ] ---
                try:
                    search_query = f'{name} {company_hint or ""} linkedin cargo'
                    async with httpx.AsyncClient(timeout=10.0) as s_client:
                        s_url = f"https://duckduckgo.com/html/?q={search_query}"
                        s_resp = await s_client.get(s_url, headers={"User-Agent": "Mozilla/5.0"})
                        if s_resp.status_code == 200:
                            raw_sources.append(s_resp.text[:5000])
                except: pass

                # --- [ O MOTOR CENTRAL DE CARGO (A Mágica acontece aqui) ] ---
                role = await role_engine.distill_role(name, company_hint or "Empresa", raw_sources)

                # Final touch
                if role:
                    role = role.strip().strip("-").strip("·").strip("|").strip(":").strip()
                
                if len(parts) >= 3: company = parts[2]
                elif len(parts) == 2: company = parts[1]

                # Se empresa ainda é N/A, tenta achar na descrição
                if (company == "N/A" or company.lower() in noise) and og_desc:
                    matches = re.findall(r'(?:na|at|em|no)\s+([A-Z][a-z\d]+(?:\s+[A-Z][a-z\d]+)?)', og_desc)
                    for m in matches:
                        if m.lower() not in noise:
                            company = m.strip()
                            break

                return {
                    "name": name,
                    "role": role,
                    "company": company,
                    "image": get_tag('property', 'og:image'),
                    "description": og_desc if len(og_desc) < 200 else og_desc[:200] + "...",
                    "url": url
                }
            else:
                return {"error": f"LinkedIn blocked access ({resp.status_code})"}
                
    except Exception as e:
        print(f"[PreviewService] Erro ao extrair preview: {e}")
        return {"error": str(e)}
