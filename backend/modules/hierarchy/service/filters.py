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
    "juridicio", "pessoal", "enfermagem", "fiscal", "comunicação", "communication", "software", 
    "desenvolvedor", "developer", "sistemas", "marketing", "vendas", "comercial", 
    "assistencia", "técnica", "engenheiro de produto", "engenheiro industrial", 
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

def is_same_person(name1: str, name2: str) -> bool:
    if not name1 or not name2:
        return False
        
    c1 = normalize_str(name1)
    c2 = normalize_str(name2)
    
    if c1 == c2:
        return True
        
    import re
    from difflib import SequenceMatcher
    
    # Remove special characters and split to tokens
    t1 = [t for t in re.sub(r'[^a-z0-9\s]', ' ', c1).split() if t not in {'de', 'da', 'do', 'das', 'dos', 'e', 'a', 'o'} and len(t) > 1]
    t2 = [t for t in re.sub(r'[^a-z0-9\s]', ' ', c2).split() if t not in {'de', 'da', 'do', 'das', 'dos', 'e', 'a', 'o'} and len(t) > 1]
    
    if not t1 or not t2:
        return False
        
    # First name must be very similar (minimum 80% similarity)
    if t1[0] != t2[0]:
        if SequenceMatcher(None, t1[0], t2[0]).ratio() < 0.8:
            return False
            
    # Count overlapping or highly similar tokens
    matches = 0
    for token1 in t1:
        for token2 in t2:
            if token1 == token2 or SequenceMatcher(None, token1, token2).ratio() >= 0.85:
                matches += 1
                break
                
    min_len = min(len(t1), len(t2))
    if min_len <= 2:
        return matches >= min_len
    else:
        return matches >= 2


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

async def apply_strict_filters(name: str, title: str, snippet: str, core_company: str, target_brand: str, target_location: str = None, mechanical_title: str = "Não Identificado") -> tuple[bool, str]:
    """
    PRE-FILTRO DE SEGURANÇA: Bloqueia marcas invasoras e lixo óbvio para economizar API da IA.
    Retorna (True, "Aprovado") se o candidato PARECE ser da empresa certa, (False, "Motivo...") se for lixo óbvio.
    """
    ctx = await BusinessContextService.get_tenant_context()
    hier = ctx.get("hierarchy", {})
    
    title_clean = normalize_str(title)
    snippet_clean = normalize_str(snippet)
    context_clean = f"{title_clean} | {snippet_clean}"
    
    # Geração robusta de variações da marca alvo
    def get_variants(brand_str: str) -> list[str]:
        norm = normalize_str(brand_str)
        if not norm or len(norm) <= 2:
            return []
        
        variants = {norm}
        
        # Limpezas de sufixos empresariais brasileiros e internacionais
        cleaned = norm
        for suffix in ["ltda", "s/a", "sa", "gmbh", "holding", "group", "grupo", "comercio", "servicos", "industria", "eireli", "me"]:
            cleaned = re.sub(rf"\b{suffix}\b", "", cleaned).strip()
            
        if cleaned and len(cleaned) > 2:
            variants.add(cleaned)
            
        # Variações sem espaços
        for v in list(variants):
            variants.add(v.replace(" ", ""))
            
        # Tratamento especial de "autopecas" / "auto pecas" / "autopeças"
        for v in list(variants):
            if "auto pecas" in v:
                variants.add(v.replace("auto pecas", "autopecas"))
            if "autopecas" in v:
                variants.add(v.replace("autopecas", "auto pecas"))
                
        return sorted(list(variants), key=len, reverse=True)
        
    brand_variants = list(set(get_variants(target_brand) + get_variants(core_company)))
    
    # 🕵️ 1. SEGURANÇA DE MARCA
    has_our_brand = any(bv in context_clean for bv in brand_variants if len(bv) > 2)
    
    # 🕵️ 2. FILTRAGEM POR RELEVÂNCIA (Whitelist unificada e abrangente em PT/EN)
    default_whitelist = [
        "buyer", "compras", "comprador", "compradora", "procurement", "suprimentos", "supply", "sourcing", 
        "purchasing", "purchas", "category manager", "logistica", "logística", "logistics", "supply chain", 
        "pcp", "almoxarife", "estoque", "expedição", "warehouse"
    ]
    
    whitelist_raw = hier.get("whitelist_keywords", default_whitelist)
    if isinstance(whitelist_raw, dict):
        whitelist = []
        for lst in whitelist_raw.values():
            if isinstance(lst, list):
                whitelist.extend(lst)
    elif isinstance(whitelist_raw, list):
        whitelist = whitelist_raw
    else:
        whitelist = default_whitelist
        
    # Garante que termos cruciais da whitelist default em PT e EN sempre façam parte da checagem
    whitelist = list(set(normalize_str(kw) for kw in whitelist + default_whitelist if kw))
    is_high_value = any(kw in context_clean for kw in whitelist)

    if not has_our_brand and not is_high_value:
        if mechanical_title == "Não Identificado":
            print(f"      [Filtro Mecânico] ⚠️ AVISO: {name} | Sem marca ({brand_variants}) e nenhum cargo identificado. Passando para Análise Humana.")
            return True, "Aprovado"
        else:
            reason = f"Sem marca e sem cargo relevante na whitelist (Cargo lido: {mechanical_title})"
            print(f"      [Filtro Mecânico] 🚫 REJEITADO: {name} | {reason}")
            return False, reason

    # 🕵️ 3. BLOQUEIO DE OUTRAS MARCAS
    other_competitors = ["mercedes", "scania", "volkswagen", "bosch", "zf ", "continental", "gm", "volvo"]
    for comp in other_competitors:
        normalized_comp = normalize_str(comp)
        if f"at {normalized_comp}" in title_clean or f"na {normalized_comp}" in title_clean:
            reason = f"Concorrente detectado no cargo: {comp}"
            print(f"      [Filtro Mecânico] 🚫 REJEITADO: {name} | {reason}")
            return False, reason

    # 🕵️ 4. NEGATIVE KEYWORDS (Vetos do banco)
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
    
    for nk in normalized_negatives:
        nk_stripped = nk.strip()
        if not nk_stripped: continue
        pattern = rf"\b{re.escape(nk_stripped)}\b"
        if re.search(pattern, context_clean):
            reason = f"Contém palavra vetada: '{nk}'"
            print(f"      [Filtro Mecânico] 🚫 REJEITADO: {name} | {reason}")
            return False, reason

    print(f"      [Filtro Mecânico] ✅ APROVADO: {name} | Passou nas checagens mecânicas.")
    return True, "Aprovado"
