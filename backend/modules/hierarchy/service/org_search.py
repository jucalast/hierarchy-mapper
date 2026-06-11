"""
modules.hierarchy.service.org_search
=====================================
Busca de dados organizacionais complementares via The Org e LinkedIn.

get_theorg_role() consulta o organograma publico do The Org para validar
cargo e departamento quando dados do LinkedIn sao insuficientes.

Classe: OrgSearch | Singleton: org_search
"""
import httpx
import re
import html
import unicodedata
from typing import Optional, Tuple

def simplify_text(text: str) -> str:
    if not text: return ""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

class OrgSearch:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        }

    async def get_theorg_role(self, company_name: str, person_name: str) -> Tuple[str, str, str]:
        """
        Tenta localizar o funcionário no organograma oficial do The Org.
        Retorna (info_confirmacao, cargo_encontrado, url_perfil).
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                t_brand = simplify_text(company_name).lower().replace(" ", "-")
                base_name = simplify_text(person_name).lower().replace(".", "").strip()
                name_parts = [p for p in base_name.split() if len(p) > 1 or p.isalpha()]
                
                if not name_parts:
                    return "", "Não Encontrado", "N/A"

                # Variações de Slugs (nome-completo, nome-sobrenome, etc.)
                slugs = ["-".join(name_parts)]
                if len(name_parts) > 1:
                    slugs.append(f"{name_parts[0]}-{name_parts[-1]}")
                if len(name_parts) > 2:
                    slugs.append(f"{name_parts[0]}-{name_parts[1]}")
                
                for s in list(set(slugs)):
                    check_url = f"https://theorg.com/org/{t_brand}/org-chart/{s}"
                    try:
                        resp = await client.get(check_url, follow_redirects=True, timeout=5.0, headers=self.headers)
                        final_url = str(resp.url).lower()
                        
                        # Validação de Segurança (Nome no título e primeiro nome no slug final)
                        candidate_first_name = name_parts[0].lower()
                        page_title_match = re.search(r'<title>(.*?)</title>', resp.text, re.I | re.S)
                        raw_title = html.unescape(page_title_match.group(1)) if page_title_match else ""
                        page_title_low = raw_title.lower()
                        final_slug = final_url.split('/')[-1]
                        
                        if resp.status_code == 200 and (candidate_first_name in final_slug) and (candidate_first_name in page_title_low):
                            # Extração de Cargo
                            role = "Confirmed Profile"
                            # Tenta extrair da meta tag
                            title_match = re.search(r'property="og:title" content="[^"-]*-\s*([^|@"]*)\s', resp.text, re.I)
                            if not title_match:
                                title_match = re.search(fr"<title>[^<]*{re.escape(name_parts[0])}[^<]*-\s*([^|@<]*)\s+", resp.text, re.I)
                            
                            if title_match:
                                role = html.unescape(title_match.group(1).strip())
                                # Limpeza final
                                role = re.sub(r'\s+(at|na|da|in|of|@)\s+.*', '', role, flags=re.IGNORECASE).strip(" -—|")
                                if len(role) < 3: role = "Confirmed Profile"

                            return " [HIERARCHY CONFIRMED]", role.title(), str(resp.url)
                    except:
                        continue
        except:
            pass
            
        return "", "Não Encontrado", "N/A"

org_search = OrgSearch()
