"""
modules.hierarchy.service.filters
==================================
Filtros e classificadores de candidatos B2B por departamento-foco.

Carrega listas de keywords dinamicamente do banco (SystemSetting) com
fallback para defaults. apply_strict_filters elimina cargos fora do
departamento configurado no Tenant (compras | logistica).

Funcoes publicas:
    get_seniority_level(role) -> int  (0-6)
    get_department_tag(role) -> str
    apply_strict_filters(candidate, area) -> bool
"""
import re
import unicodedata
from modules.ai.service.context.business_context_service import BusinessContextService

# Fallbacks legados (J.Ferres)
negative_keywords_fallback = [
    "customer service", "vendedor", "vendedora", "sales", "crm", "rh", "hr", "recurso humano", 
    "juridicio", "pessoal", "enfermagem", "fiscal", "comunicação", "communication", "it ", "software", 
    "desenvolvedor", "developer", "sistemas", "totvs", "datasul", "marketing", "vendas", "comercial", 
    "assistencia", "técnica", "ti ", "engenheiro de produto", "engenheiro industrial", 
    "manufatura", "manufacturing", "production", "produção", "qualidade", "quality",
    "manutenção", "mecanico", "mecânico", "usinagem", "operator", "operador",
    "professor", "acadêmico", "estudante", "student", "freelancer", "autônomo",
    "jurídico", "advogado", "legal", "compliance", "psicologia", "médico",
    "financial", "financeiro", "contas", "contabilidade", "accounting", "payables", "receivables",
    "fpa", "fp&a", "planning and analysis", "auditoria", "audit", "tributário", "tax", "facilities",
    "manutenção Predial", "facilities management", "recepção", "portaria"
]

PURCHASING_KEYWORDS = [
    "Comprador", "Compradora", "Procurement", "Strategic Sourcing", "Buyer", 
    "Analista de Compras", "Sourcing", "Purchasing", "Category Manager", 
    "Suprimentos", "Indirect Procurement", "Supply Management", "Capex Buyer", 
    "Opex Buyer", "Commodity Manager", "Purchasing Agent", "Gestor de Suprimentos",
    "Coordenador de Compras", "Gerente de Compras", "Diretor de Compras"
]

LOGISTICS_KEYWORDS = [
    "Logística", "Supply Chain", "Warehouse Manager", "PCP", "Coordenador de Logística",
    "Inventory", "Almoxarifado", "Expedição", "Logistics Operations", "Cadeia de Suprimentos",
    "Transporte", "Distribuição", "WMS", "TMS", "Fleet Manager", "Gerente de Logística",
    "Analista de Logística", "Analista de PCP", "Planejamento de Produção", 
    "Supply Chain Manager", "Demand Planner", "Logística Internacional"
]

def normalize_str(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s.strip()

async def get_seniority_level(role: str) -> int:
    role = role.lower()
    ctx = await BusinessContextService.get_tenant_context()
    rules = ctx.get("hierarchy", {}).get("seniority_rules", {})
    
    if not rules:
        # Fallback legados
        if any(x in role for x in ["cpo", "csco", "coo", "chief operation", "chief procurement", "chief", "ceo", "president", "socio", "sócio", "owner", "fundador", "founder", "board"]): return 6
        if any(x in role for x in ["diretor", "director", "vp", "vice president", "superintendente"]): return 5
        if any(x in role for x in ["gerente", "manager", "head", "lead", "gerenta", "chefe", "gestor"]): return 4
        if any(x in role for x in ["coordenador", "coordinator", "supervisor", "lider", "líder", "encarregado", "specialist", "especialista", "sr.", "senior", "sênior", "supervisão"]): return 3
        if any(x in role for x in ["estagio", "estagiario", "estagiário", "intern", "aprendiz", "auxiliar", "assistente", "assistant", "conferente", "estoquista", "almoxarife", "operador", "jovem"]): return 1
        return 2

    # Usar regras do banco
    for kw, score in sorted(rules.items(), key=lambda item: item[1], reverse=True):
        if kw in role:
            return score
    
    return 2 

async def get_department_tag(role: str) -> str:
    role = role.lower()
    ctx = await BusinessContextService.get_tenant_context()
    mapping = ctx.get("hierarchy", {}).get("department_mapping", {})

    if not mapping:
        # Fallback legado
        if any(x in role for x in ["compras", "procurement", "buyer", "comprador", "sourcing", "purchas", "category manager", "strategic buyer", "technical buyer"]): return "Procurement"
        if any(x in role for x in ["supply", "suprimentos", "cadeia"]): return "Supply Chain"
        if any(x in role for x in ["logistica", "logística", "logistics", "transporte", "distribuição", "warehouse", "armazém", "almoxarifado", "freight", "last mile", "expedição", "estoque", "frota", "wms", "tms"]): return "Logistics"
        if any(x in role for x in ["comex", "import", "export", "comércio exterior"]): return "Comex"
        if any(x in role for x in ["planejamento", "planning", "pdm", "pcp", "ppcp", "inventário"]): return "Planning"
        if any(x in role for x in ["ceo", "coo", "diretor", "director", "manager", "gerente", "head", "president"]): return "Executive Management"
        return "Operations"

    for kw, tag in mapping.items():
        if kw in role:
            return tag
    
    return "Operations"

async def apply_strict_filters(name: str, title: str, snippet: str, core_company: str, target_brand: str, target_location: str = None) -> bool:
    """
    PRE-FILTRO DE SEGURANÇA: Bloqueia marcas invasoras e lixo óbvio para economizar API da IA.
    Retorna True se o candidato PARECE ser da empresa certa, False se for lixo óbvio.
    """
    ctx = await BusinessContextService.get_tenant_context()
    hier = ctx.get("hierarchy", {})
    
    title_clean = normalize_str(title)
    snippet_clean = normalize_str(snippet)
    context_clean = f"{title_clean} | {snippet_clean}"
    
    brand_variants = [normalize_str(target_brand), normalize_str(core_company)]
    
    # 🕵️ 1. SEGURANÇA DE MARCA
    has_our_brand = any(bv in context_clean for bv in brand_variants if len(bv) > 2)
    
    # 🕵️ 2. FILTRAGEM POR RELEVÂNCIA (Whitelist)
    whitelist_raw = hier.get("whitelist_keywords", ["buyer", "compras", "procurement", "suprimentos", "supply", "sourcing"])
    if isinstance(whitelist_raw, dict):
        whitelist = []
        for lst in whitelist_raw.values():
            if isinstance(lst, list):
                whitelist.extend(lst)
    elif isinstance(whitelist_raw, list):
        whitelist = whitelist_raw
    else:
        whitelist = ["buyer", "compras", "procurement", "suprimentos", "supply", "sourcing"]
        
    is_high_value = any(kw in context_clean for kw in whitelist)

    if not has_our_brand and not is_high_value:
        return False

    # 🕵️ 3. BLOQUEIO DE OUTRAS MARCAS
    other_competitors = ["mercedes", "scania", "volkswagen", "bosch", "zf ", "continental", "gm", "volvo"]
    for comp in other_competitors:
        normalized_comp = normalize_str(comp)
        if f"at {normalized_comp}" in title_clean or f"na {normalized_comp}" in title_clean:
            return False

    # 🕵️ 4. NEGATIVE KEYWORDS (Vetos do banco)
    # Pega os vetos do departamento focado ou globais
    focus = hier.get("department_focus", "compras")
    forbidden = hier.get("forbidden_keywords", {}).get(focus, negative_keywords_fallback)
    
    # Ignora palavras-chave negativas que façam parte do próprio nome da empresa alvo
    words_to_ignore = set()
    for bv in brand_variants:
        if len(bv) > 2:
            for word in bv.split():
                if len(word) > 2:
                    words_to_ignore.add(word)

    normalized_negatives = [
        normalize_str(nk) for nk in forbidden 
        if normalize_str(nk) not in words_to_ignore
    ]
    
    if any(nk in context_clean for nk in normalized_negatives):
        return False

    return True
