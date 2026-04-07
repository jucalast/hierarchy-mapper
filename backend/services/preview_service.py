import httpx
import re
from typing import Dict, Optional
from bs4 import BeautifulSoup
from services.role_engine import role_engine

async def get_url_preview(url: str, role_hint: str = "", company_hint: str = "", fast_mode: bool = False) -> Dict:
    """
    Simula um crawler de rede social para extrair metadados Open Graph REAIS do LinkedIn.
    """
    if not url: return {"error": "URL missing"}

    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                def get_tag(attr, val):
                    tag = soup.find('meta', attrs={attr: val})
                    return tag.get('content') if tag else None

                og_title = get_tag('property', 'og:title') or get_tag('name', 'title') or ""
                og_desc = get_tag('property', 'og:description') or get_tag('name', 'description') or ""
                og_image = get_tag('property', 'og:image')
                
                # --- PARSER PURO DE METADADOS ---
                # Ex: "Israel Fernandes - Empresa Hellermann Tyton"
                title_clean = og_title.replace(" | LinkedIn", "").replace(" | LinkedIn Profile", "").strip()
                parts = [p.strip() for p in re.split(r'[-–|:·•]', title_clean) if p.strip()]
                
                # Nome e Cargo "Brutos" dos Metadados
                name = parts[0] if len(parts) > 0 else "Colaborador"
                role = parts[1] if len(parts) >= 2 else "Cargo não identificado nos metadados"
                
                # Se for o caso de Repescagem (Deep Research)
                raw_sources = [og_title, og_desc]
                if not fast_mode:
                    try:
                        search_query = f'"{name}" "{company_hint or ""}" linkedin cargo'
                        async with httpx.AsyncClient(timeout=10.0) as s_client:
                            s_url = f"https://duckduckgo.com/html/?q={search_query}"
                            s_resp = await s_client.get(s_url, headers={"User-Agent": "Mozilla/5.0"})
                            if s_resp.status_code == 200:
                                raw_sources.append(s_resp.text[:5000])
                    except: pass

                return {
                    "name": name,
                    "role": role, # Agora vem do Texto Real do Título, não da IA
                    "company": company_hint or (parts[1] if len(parts) >= 2 else "N/A"),
                    "image": og_image,
                    "description": og_desc if len(og_desc) < 400 else og_desc[:400] + "...",
                    "url": url,
                    "raw_sources": raw_sources # Passamos as fontes puras para o scanner decidir
                }
            else:
                return {"error": f"Blocked {resp.status_code}", "is_valid": False}
    except Exception as e:
        return {"error": str(e), "is_valid": False}
