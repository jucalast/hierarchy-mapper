"""
Gerenciamento de hierarquia: construção de nós e resolução de managers.
Lógica de construção do grafo de hierarquia a partir de dados brutos.
"""
import re
from typing import List, Dict, Any, Optional

from api.v1.schemas import EmployeeNode
from services.hierarchy.filters import get_seniority_level, get_department_tag


def build_root_node(
    razao_social: str,
    confirmed_brand: Optional[str] = None,
    confirmed_logo: Optional[str] = None,
    domain: Optional[str] = None
) -> Dict[str, Any]:
    """Cria o nó raiz (empresa) da hierarquia."""
    display_name = confirmed_brand or (razao_social[:30] + "..." if len(razao_social) > 30 else razao_social)
    return {
        "id": "root_company",
        "name": display_name,
        "role": "Entidade Principal",
        "department": "Supply Chain (Matriz)",
        "manager_id": None,
        "level": 0,
        "company_logo": confirmed_logo,
        "domain": domain
    }


def build_socio_nodes(qsa: list, razao_social: str) -> List[Dict[str, Any]]:
    """Constrói nós dos sócios (QSA)."""
    nodes = []
    for idx, socio in enumerate(qsa):
        name_socio = socio.get("nome_socio", "Sócio Anônimo")
        role_socio = socio.get("qualificacao_socio", "Sócio")
        clean_socio_id = f"socio_{re.sub(r'[^a-zA-Z0-9]', '_', name_socio.lower())}"
        nodes.append({
            "id": clean_socio_id,
            "name": name_socio,
            "role": role_socio,
            "department": "Quadro de Sócios (QSA)",
            "manager_id": "root_company",
            "level": 6
        })
    return nodes


def assign_managers(
    new_emp: EmployeeNode,
    hierarchy_pool: List[EmployeeNode]
) -> str:
    """
    Atribui manager_id para um novo empregado baseado no pool de hierarquia existente.
    Usa departamento matching + nível sênior imediato.
    """
    if new_emp.level <= 0:
        new_emp.level = get_seniority_level(new_emp.role)
        if new_emp.level <= 0:
            new_emp.level = 1

    levels_map = {0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
    
    for existing in hierarchy_pool:
        if existing.id == new_emp.id:
            continue
        levels_map[existing.level].append(existing)
    
    assigned_manager = "root_company"
    found_boss = False
    
    for senior_level in range(new_emp.level + 1, 7):
        if found_boss:
            break
        if not levels_map.get(senior_level):
            continue
        
        matching_bosses = [
            b for b in levels_map[senior_level]
            if b.department == new_emp.department
            or any(k in b.department for k in ["Diretoria Executiva", "Raiz", "Administração", "Quadro de Sócios (QSA)"])
        ]
        if matching_bosses:
            assigned_manager = matching_bosses[0].id
            found_boss = True
    
    return assigned_manager


def reparent_subordinates(
    new_emp: EmployeeNode,
    hierarchy_pool: List[EmployeeNode]
) -> List[Dict]:
    """
    Re-liga nós existentes ao novo empregado se ele for mais sênior no mesmo departamento.
    Retorna lista de nós que tiveram seus managers atualizados.
    """
    reparented = []
    
    if new_emp.level <= 1:
        return reparented
    
    for existing in hierarchy_pool:
        if existing.id == new_emp.id:
            continue
        
        is_same_dept = (existing.department == new_emp.department)
        is_emp_superior = (new_emp.level > existing.level)
        is_currently_orphan = (existing.manager_id == "root_company")
        
        if is_same_dept and is_emp_superior and is_currently_orphan:
            existing.manager_id = new_emp.id
            reparented.append(existing.dict())
    
    return reparented
