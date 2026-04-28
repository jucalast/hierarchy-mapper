"""
Enriquecimento e processamento de contatos para o módulo ContactGrid.
Achata listas, mapeia senioridade e completa emails parciais.
"""
from typing import Dict, Any, List
from core.logging_config import get_logger

log = get_logger(__name__)


def enrich_contacts_for_grid(internal_context: Dict[str, Any]) -> List[Dict]:
    """
    Processa e enriquece contatos para exibição no ContactGrid.
    - Achata decision_makers + employees_by_dept em lista única
    - Mapeia senioridade para labels (Tier 1-6)
    - Filtra sócios e entities excluídas
    - Completa emails parciais com domínio
    
    Retorna a lista filtrada e enriquecida.
    """
    all_persons = []
    
    if "decision_makers" in internal_context:
        dm_data = internal_context["decision_makers"]
        dms = dm_data if isinstance(dm_data, list) else dm_data.get("decision_makers", [])
        all_persons.extend(dms)
    
    if "employees_by_dept" in internal_context:
        by_dept = internal_context["employees_by_dept"].get("by_department", {})
        for dept_name, emps in by_dept.items():
            for e in emps:
                if isinstance(e, dict):
                    e["department"] = dept_name
                    # Mapeamento de Senioridade Fixa para evitar erro de nível 5 em todos
                    s_val = e.get("seniority", 3)
                    try: s_num = int(s_val)
                    except: s_num = 3
                    
                    labels = {
                        6: ("Board / Sócio", "Tier 6"),
                        5: ("Director / Regional Head", "Tier 5"),
                        4: ("Manager / Head", "Tier 4"),
                        3: ("Especialista / Senior", "Tier 3"),
                        2: ("Analista / Operacional", "Tier 2"),
                        1: ("Junior / Estagiário", "Tier 1")
                    }
                    label_text, tier_text = labels.get(s_num, ("Profissional", "Tier 3"))
                    e["seniority_label"] = label_text
                    e["tier"] = tier_text
            all_persons.extend(emps)
    
    # FILTRAGEM: Remove Sócios (Tier 6) e a própria Empresa (Tier 0)
    filtered_list = []
    for p in all_persons:
        if not isinstance(p, dict): continue
        
        role = str(p.get("role", "")).lower()
        dept = str(p.get("department", "")).lower()
        seniority = p.get("seniority")
        
        # Filtra Tier 6 (Sócio/Board) e Tier 0 (Root/Empresa)
        if seniority in [0, 6, "0", "6"]:
            continue
        
        # Filtra por palavras-chave se o seniority for inconclusivo ou for Holding
        is_excluded = any(kw in role or kw in dept for kw in ["sócio", "socio", "holding", "administrador judicial", "aktieselskab", "aktiengesellschaft"])
        if is_excluded:
            continue
            
        filtered_list.append(p)

    return filtered_list


def complete_partial_emails(persons: List[Dict], internal_context: Dict[str, Any]):
    """
    Completa emails parciais e injeta dados extras do OSINT nos contatos.
    Modifica a lista in-place.
    """
    org_info = internal_context.get("organization", {})
    org_domain = org_info.get("domain") or org_info.get("domain_url")
    
    # Fallback: Se não tem domínio, mas tem nome da empresa, tenta construir um
    if not org_domain and org_info.get("name"):
        # Remove espaços e bota .com (tentativa desesperada)
        clean_name = (org_info.get("name") or "").lower().replace(" ", "")
        org_domain = f"{clean_name}.com"

    log.debug("enrichment.start", persons=len(persons), domain=org_domain)

    for p in persons:
        if not isinstance(p, dict): continue
        
        # 1. Ajuste de E-mail (Completar se terminar em @)
        email = p.get("email") or p.get("emailProvavel")
        if email and email.endswith("@") and org_domain:
            p["email"] = f"{email}{org_domain}"
            log.debug("enrichment.email_completed", email=p['email'])
        
        # 2. Injeção de dados extras (OSINT fallback)
        if "osint_result" in internal_context:
            osint = internal_context["osint_result"]
            p_name = p.get("name", "").strip()
            
            # Busca no OSINT (tenta match exato ou parcial)
            p_osint = osint.get(p_name)
            if not p_osint:
                # Busca por primeiro nome se não achar exato
                first_name = p_name.split(" ")[0]
                for key in osint:
                    if first_name in key:
                        p_osint = osint[key]
                        break

            if p_osint:
                if not p.get("location") or p.get("location") == "Localização não identificada": 
                    p["location"] = p_osint.get("location") or p_osint.get("cidade")
                
                if not p.get("observations") or "Nenhuma informação" in p.get("observations", ""):
                    p["observations"] = p_osint.get("summary") or p_osint.get("headline") or p_osint.get("description")
                
                if not p.get("phone"):
                    p["phone"] = p_osint.get("pabx") or p_osint.get("phone") or p_osint.get("whatsapp")

                if not p.get("email"):
                    raw_email = p_osint.get("emailProvavel") or p_osint.get("email")
                    if raw_email:
                        if raw_email.endswith("@") and org_domain:
                            p["email"] = f"{raw_email}{org_domain}"
                        else:
                            p["email"] = raw_email
