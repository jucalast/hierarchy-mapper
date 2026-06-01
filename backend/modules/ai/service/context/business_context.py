"""
business_context.py — Inteligência de Negócio Dinâmica

Este módulo centraliza o conhecimento sobre a empresa, seus produtos, clientes ideais
e metodologias de prospecção B2B. Agora totalmente desacoplado para o banco de dados.

Todas as constantes agora servem apenas como FALLBACK caso o banco de dados esteja vazio.
"""

from __future__ import annotations
from typing import Any, Dict
from modules.ai.service.context.business_context_service import BusinessContextService

# =============================================================================
# FALLBACKS ESTÁTICOS (REMOVIDOS - USE O BANCO DE DADOS)
# =============================================================================

COMPANY_NAME = "Empresa B2B"
COMPANY_SEGMENT = "Segmento"
COMPANY_DIFFERENTIALS = []

SELLER_NAME = "Vendedor"
SELLER_ROLE = "Representante"

PRODUCTS = {}

ICP = {
    "industries": [],
    "company_profiles": [],
    "decision_makers": [],
    "pain_points": [],
    "disqualifiers": []
}

REFERENCE_CLIENTS = []

VALUE_PROPOSITIONS = {}

# =============================================================================
# FUNÇÕES DINÂMICAS
# =============================================================================

async def load_db_setting(key: str, default: Any = None) -> Any:
    """
    Mantido para compatibilidade legado, mas agora redireciona para o 
    BusinessContextService para usar as tabelas relacionais.
    """
    ctx = await BusinessContextService.get_tenant_context()
    if not ctx:
        return default
    
    # Mapeamento de chaves legadas para o novo contexto
    mapping = {
        "company_profile": {
            "company_name": ctx["company_name"],
            "company_segment": ctx["company_segment"],
            "company_differentials": ctx["company_differentials"],
            "seller_name": ctx["seller_name"],
            "seller_role": ctx["seller_role"]
        },
        "products": {"list": list(ctx["products"].values())},
        "reference_clients": {"list": ctx["reference_clients"]},
        "icp_config": ctx["icp"],
        "hierarchy_config": ctx["hierarchy"]
    }
    
    return mapping.get(key, default)

async def get_business_context_for_prompt() -> str:
    """
    Retorna um bloco de texto compacto com o contexto de negócio dinâmico.
    """
    ctx = await BusinessContextService.get_tenant_context()
    if not ctx:
        return "Erro ao carregar contexto de negócio."

    company_name = ctx["company_name"]
    company_segment = ctx["company_segment"]
    seller_name = ctx["seller_name"]
    
    diffs_str = "\n".join([f"- {d}" for d in ctx["company_differentials"]])
    products_str = ", ".join([p["name"] for p in ctx["products"].values()])
    ref_clients = ", ".join([c["name"] for c in ctx["reference_clients"][:5]])
    pain_points_str = "\n".join([f"- {p}" for p in ctx["icp"]["pain_points"][:4]])

    return f"""
=== CONTEXTO DA {company_name.upper()} (Vendedor: {seller_name}) ===
EMPRESA: {company_name} — {company_segment}
PRODUTOS: {products_str}
CLIENTES DE REFERÊNCIA: {ref_clients}
DIFERENCIAIS PRINCIPAIS:
{diffs_str}

DORES QUE RESOLVEMOS:
{pain_points_str}

PÚBLICO-ALVO: Compras, Suprimentos, Supply Chain em indústrias e exportadores correspondentes.
""".strip()

async def get_icp_score(company_info: dict) -> dict:
    """
    Pontua um lead de forma dinâmica com base no ICP carregado do banco de dados.
    """
    ctx = await BusinessContextService.get_tenant_context()
    icp = ctx.get("icp", {})
    rules = icp.get("score_rules", [])

    score = 0
    reasons = []
    penalties = []

    segment = (company_info.get("segment") or "").lower()
    description = (company_info.get("description") or "").lower()
    full_text = f"{segment} {description}"

    # Aplicar regras dinâmicas do banco
    for rule in rules:
        pattern = rule["pattern"].lower()
        if pattern in full_text:
            val = rule["score"]
            score += val
            if val > 0:
                reasons.append(rule["reason"])
            else:
                penalties.append(rule["reason"])

    # Porte (Lógica básica mantida, mas poderia ser parametrizada também)
    employees = company_info.get("employees", 0)
    try:
        emp_count = int(employees) if isinstance(employees, (int, float)) or (isinstance(employees, str) and employees.isdigit()) else 0
    except: emp_count = 0

    if emp_count >= 100:
        score += 20
        reasons.append("Empresa de grande porte — volume consistente")
    elif emp_count >= 30:
        score += 10
        reasons.append("Empresa de médio porte")

    # Exportação
    if company_info.get("exports"):
        score += 25
        reasons.append("Empresa exportadora — potencial para caixas CKD")

    score = max(0, min(100, score))
    tier = "A" if score >= 70 else "B" if score >= 40 else "C"

    return {
        "score": score,
        "tier": tier,
        "reasons": reasons,
        "penalties": penalties,
        "recommendation": (
            "Prioridade alta — abordar imediatamente" if tier == "A"
            else "Abordar após leads A" if tier == "B"
            else "Baixa prioridade — nutrição passiva"
        )
    }

async def get_cold_outreach_angle(company_info: dict) -> str:
    """Determina o melhor ângulo de abordagem baseado no banco de dados."""
    ctx = await BusinessContextService.get_tenant_context()
    ref_names = [c["name"] for c in ctx["reference_clients"]]
    client1 = ref_names[0] if len(ref_names) > 0 else "Toyota"
    
    org_name = company_info.get("name", "a empresa")
    
    # Por enquanto mantemos os ângulos fixos mas usando dados dinâmicos nos ganchos
    return f"GANCHO SUGERIDO: 'Trabalhamos com {client1} e resolvemos problemas de suprimentos. Seria relevante para a {org_name}?'"
