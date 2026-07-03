"""
modules.intelligence.service.preview_service
=============================================
Extracao de metadados Open Graph de URLs para pre-visualizacao de links.

Tenta em ordem: og:* -> twitter:* -> title/description padrao HTML.
role_hint e company_hint permitem inferir dados quando OG nao existe.

Funcao publica: get_url_preview(url, role_hint, company_hint) -> dict
"""
import httpx
import re
import base64
from typing import Dict, Optional
from bs4 import BeautifulSoup

async def _download_and_convert_to_base64(url: str) -> Optional[str]:
    """Faz o download da imagem e converte para base64 para persistência no banco."""
    if not url: return None
    try:
        # User-Agent de navegador para evitar bloqueios no download da imagem
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "image/jpeg")
                b64 = base64.b64encode(resp.content).decode("utf-8")
                return f"data:{content_type};base64,{b64}"
    except Exception as e:
        print(f"      [Preview Service] Falha ao capturar imagem real: {e}")
    return None

async def get_url_preview(url: str, role_hint: str = "", company_hint: str = "", fast_mode: bool = False) -> Dict:
    """
    Simula um crawler de rede social para extrair metadados Open Graph REAIS do LinkedIn.
    Agora também captura a imagem em base64 para persistência definitiva.
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

                og_image = get_tag('property', 'og:image') or get_tag('name', 'twitter:image')
                
                if not og_image:
                    # Segundo Round: Tenta com User-Agent de Twitter (muitos perfis só liberam pra ele)
                    headers["User-Agent"] = "Twitterbot/1.0"
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        og_image = get_tag('property', 'og:image') or get_tag('name', 'twitter:image')

                # Captura de Imagem Base64 (O "Pulo do Gato" para persistência)
                image_baked = None
                if og_image:
                    image_baked = await _download_and_convert_to_base64(og_image)

                og_title = get_tag('property', 'og:title') or get_tag('name', 'title') or ""
                og_desc = get_tag('property', 'og:description') or get_tag('name', 'description') or ""
                
                title_clean = og_title.replace(" | LinkedIn", "").replace(" | LinkedIn Profile", "").strip()
                parts = [p.strip() for p in re.split(r'[-–|:·•]', title_clean) if p.strip()]
                
                name = parts[0] if len(parts) > 0 else "Colaborador"
                
                # 🛡️ Proteção: Se houver apenas 2 partes, e a segunda for a empresa, o cargo é desconhecido
                potential_role = parts[1] if len(parts) >= 2 else "Cargo não identificado nos metadados"
                if len(parts) == 2 and company_hint:
                    from difflib import SequenceMatcher
                    similarity = SequenceMatcher(None, potential_role.lower(), company_hint.lower()).ratio()
                    if similarity > 0.8:
                        potential_role = "Cargo não identificado nos metadados"
                
                role = potential_role
                
                raw_sources = [og_title, og_desc]
                if not fast_mode:
                    try:
                        search_query = f'{name} {company_hint or ""} linkedin cargo'
                        async with httpx.AsyncClient(timeout=10.0) as s_client:
                            s_url = f"https://duckduckgo.com/html/?q={search_query}"
                            s_resp = await s_client.get(s_url, headers={"User-Agent": "Mozilla/5.0"})
                            if s_resp.status_code == 200:
                                raw_sources.append(s_resp.text[:5000])
                    except: pass

                if not og_image:
                    print(f"      [Crawler] ⚠️ Nenhuma imagem para {name}")

                return {
                    "name": name,
                    "role": role,
                    "company": company_hint or (parts[1] if len(parts) >= 2 else "N/A"),
                    "image": image_baked or og_image, # Prioriza o Base64, fallback para URL
                    "description": og_desc if len(og_desc) < 400 else og_desc[:400] + "...",
                    "url": url,
                    "raw_sources": raw_sources 
                }
            else:
                return {"error": f"Blocked {resp.status_code}", "is_valid": False}
    except Exception as e:
        return {"error": str(e), "is_valid": False}
