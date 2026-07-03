"""Serviços de discovery e construção de hierarquia B2B."""
from .b2b_scanner import discover_employees, discover_employees_stream
from .graph_builder import build_root_node, build_socio_nodes, assign_managers, reparent_subordinates
from .filters import get_seniority_level, get_department_tag, apply_strict_filters
from .cnpj_resolver import fetch_company_data_by_cnpj, build_full_address
from .org_persistence import upsert_organization, persist_socios
from .search_engine import get_duck_results
from .role_engine import role_engine

__all__ = [
    "discover_employees", "discover_employees_stream",
    "build_root_node", "build_socio_nodes", "assign_managers", "reparent_subordinates",
    "get_seniority_level", "get_department_tag", "apply_strict_filters",
    "fetch_company_data_by_cnpj", "build_full_address",
    "upsert_organization", "persist_socios",
    "get_duck_results",
    "role_engine",
]
