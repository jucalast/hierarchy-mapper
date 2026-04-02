import httpx
import re
from typing import Dict, Optional
from bs4 import BeautifulSoup

def get_url_preview(url: str, role_hint: str = "", company_hint: str = "") -> Dict:
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
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Extraindo Metadados OG
                def get_tag(attr, val):
                    tag = soup.find('meta', attrs={attr: val})
                    return tag.get('content') if tag else None

                og_title = get_tag('property', 'og:title') or get_tag('name', 'title') or ""
                og_desc = get_tag('property', 'og:description') or get_tag('name', 'description') or ""
                
                # Fatiamento inteligente do Título
                title_clean = og_title.replace(" | LinkedIn", "").replace(" | LinkedIn Profile", "").strip()
                parts = [p.strip() for p in re.split(r'[-–|:·•]', title_clean) if p.strip()]
                
                # Filtra ruído (incluindo variações com espaços)
                noise = ["linkedin", "linked in", "linked", "perfil", "profile", "overview", "followers", "conexões", "see more"]
                parts = [p.strip() for p in parts if p.strip().lower() not in noise]

                # Lógica de Distribuição "Efeito Foto" (Pega o que tá na página e ponto final)
                # 1. Títulos de Cargo Comuns (Dicionário de Identificação)
                job_keywords = [
                    "comprador", "buyer", "procurement", "supply chain", "gerente", "manager", "diretor", "director",
                    "coordenador", "coordinator", "analista", "analyst", "supervisor", "especialista", "specialist",
                    "logística", "logistics", "compras", "sourcing", "planner", "planejamento", "mestre", "lead", 
                    "head", "vp", "chief", "administrador", "engineer", "engenheiro", "clerk", "auxiliar", "assistente"
                ]

                name = parts[0] if len(parts) > 0 else "Colaborador"
                role = "Professional"
                company = company_hint or "N/A"

                # Tentativa 1: Fatiar o título e procurar o cargo real
                found_role = None
                for p in parts[1:]: # Ignora o nome e busca o cargo
                    pl = p.lower()
                    if any(key in pl for key in job_keywords):
                        # Limpeza profunda: Remove "na [Empresa]", "at [Empresa]" que vem no título do LinkedIn
                        p_clean = re.sub(rf"(?i)\s+(at|na|no|em|da|do|atualmente na|trabalha na)\s+.*$", "", p).strip()
                        # Também limpa se o nome da empresa/marca estiver colado no cargo
                        brand_p = company_hint or "LinkedIn"
                        p_clean = re.sub(rf"(?i)\s+{re.escape(brand_p)}.*$", "", p_clean).strip()
                        found_role = p_clean
                        break
                
                # Tentativa 2: Se não achou por palavra-chave, mas tem 3 partes, a do meio é o cargo
                if not found_role and len(parts) >= 3:
                        found_role = parts[1]
                        company = parts[2]
                
                # Tentativa 3: Buscar no início da descrição (Bio)
                if not found_role and og_desc:
                    bio_match = re.search(rf"(?:{name}|{name.split()[0]})\s+(?:is a|é a|é|atualmente)\s+([^,.-]+)", og_desc, re.IGNORECASE)
                    if bio_match:
                        found_role = bio_match.group(1).strip()

                # Aplica o resultado Real (ignora hints se o cargo foi encontrado na página)
                role = found_role if found_role else (role_hint if role_hint.lower() not in ["management / strategy", "linked in", "operational / support"] else "Colaborador")
                
                # Final touch: Capitalize and limit size
                if role:
                    role = role.strip().strip("-").strip("·").strip()
                    # Se o role ainda tiver a empresa (ex: Analista na Bosch), corta de novo
                    role = re.sub(rf"(?i)\s+(at|na|no|em|da|do)\s+.*$", "", role).strip()
                if len(parts) >= 3: company = parts[2]
                elif len(parts) == 2 and not found_role: company = parts[1]

                # Se empresa ainda é N/A, tenta achar na descrição, mas ignora o LinkedIn
                if (company == "N/A" or company.lower() in noise) and og_desc:
                    # Busca "na [Empresa]" ou "em [Empresa]" mas ignora se a empresa for LinkedIn
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
                    "description": og_desc,
                    "url": url
                }
            else:
                return {"error": f"LinkedIn blocked access ({resp.status_code})"}
                
    except Exception as e:
        print(f"[PreviewService] Erro ao extrair preview: {e}")
        return {"error": str(e)}
