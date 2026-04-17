import re
import unicodedata

negative_keywords = [
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

# 🛒 DICIONÁRIO DE COMPRAS (DIVERSIFICADO)
PURCHASING_KEYWORDS = [
    "Comprador", "Compradora", "Procurement", "Strategic Sourcing", "Buyer", 
    "Analista de Compras", "Sourcing", "Purchasing", "Category Manager", 
    "Suprimentos", "Indirect Procurement", "Supply Management", "Capex Buyer", 
    "Opex Buyer", "Commodity Manager", "Purchasing Agent", "Gestor de Suprimentos",
    "Coordenador de Compras", "Gerente de Compras", "Diretor de Compras"
]

# 📦 DICIONÁRIO DE LOGÍSTICA (DIVERSIFICADO)
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

def get_seniority_level(role: str) -> int:
    role = role.lower()
    # Nível 6: C-Level / Heads Globais / Sócios / Fundadores
    if any(x in role for x in ["cpo", "csco", "coo", "chief operation", "chief procurement", "chief", "ceo", "president", "socio", "sócio", "owner", "fundador", "founder", "board"]): return 6
    # Nível 5: Diretoria / VP / Superintendência
    if any(x in role for x in ["diretor", "director", "vp", "vice president", "superintendente"]): return 5
    # Nível 4: Gerência / Head / Lead / Chefia Geral
    if any(x in role for x in ["gerente", "manager", "head", "lead", "gerenta", "chefe", "gestor"]): return 4
    # Nível 3: Coordenação / Supervisão / Encarregados / Especialistas Sêniores
    if any(x in role for x in ["coordenador", "coordinator", "supervisor", "lider", "líder", "encarregado", "specialist", "especialista", "sr.", "senior", "sênior", "supervisão"]): return 3
    # Nível 1: Entrada / Apoio / Estágio / Operacional de base
    if any(x in role for x in ["estagio", "estagiario", "estagiário", "intern", "aprendiz", "auxiliar", "assistente", "assistant", "conferente", "estoquista", "almoxarife", "operador", "jovem"]): return 1
    # Nível 2: Analistas, Compradores, Engenheiros, Consultores e Planejadores (Jr/Pl/Default)
    return 2 

def get_department_tag(role: str) -> str:
    role = role.lower()
    if any(x in role for x in ["compras", "procurement", "buyer", "comprador", "sourcing", "purchas", "category manager", "strategic buyer", "technical buyer"]): return "Procurement"
    if any(x in role for x in ["supply", "suprimentos", "cadeia"]): return "Supply Chain"
    if any(x in role for x in ["logistica", "logística", "logistics", "transporte", "distribuição", "warehouse", "armazém", "almoxarifado", "freight", "last mile", "expedição", "estoque", "frota", "wms", "tms"]): return "Logistics"
    if any(x in role for x in ["comex", "import", "export", "comércio exterior"]): return "Comex"
    if any(x in role for x in ["planejamento", "planning", "pdm", "pcp", "ppcp", "inventário"]): return "Planning"
    if any(x in role for x in ["ceo", "coo", "diretor", "director", "manager", "gerente", "head", "president"]): return "Executive Management"
    return "Operations"

def apply_strict_filters(name: str, title: str, snippet: str, core_company: str, target_brand: str, target_location: str = None) -> bool:
    """
    PRE-FILTRO DE SEGURANÇA: Bloqueia marcas invasoras e lixo óbvio para economizar API da IA.
    Retorna True se o candidato PARECE ser da empresa certa, False se for lixo óbvio.
    """
    # 🛡️ NORMALIZAÇÃO: Remove acentos para garantir match (ex: Böttcher -> Bottcher)
    title_clean = normalize_str(title)
    snippet_clean = normalize_str(snippet)
    context_clean = f"{title_clean} | {snippet_clean}"
    
    brand_variants = [normalize_str(target_brand), normalize_str(core_company)]
    if " " in target_brand:
        brand_parts = target_brand.split()
        if len(brand_parts[0]) > 2:
            brand_variants.append(normalize_str(brand_parts[0]))
    
    # 🕵️ 1. SEGURANÇA DE MARCA
    has_our_brand = any(bv in context_clean for bv in brand_variants if len(bv) > 2)
    
    # 🕵️ 4. FILTRAGEM POR RELEVÂNCIA (Whitelist vs Blacklist)
    # Se houver uma palavra de ALTO VALOR, passamos para IA sem medo.
    high_value_keywords = ["buyer", "compras", "comprador", "compradora", "purchasing", "suprimentos", "supply", "procurement", "sourcing", "strategic"]
    is_high_value = any(kw in context_clean for kw in high_value_keywords)

    if not has_our_brand and not is_high_value:
        # Se não tem a marca E não é um cargo óbvio de compras, descarta
        return False

    # 🕵️ 2. BLOQUEIO DE OUTRAS MARCAS (Anticoncorrente)
    # Se mencionar outras marcas GRANDES no título com "na" ou "at", bloqueia
    other_competitors = ["mercedes", "scania", "volkswagen", "bosch", "zf ", "continental", "gm", "volvo"]
    for comp in other_competitors:
        normalized_comp = normalize_str(comp)
        if f"at {normalized_comp}" in title_clean or f"na {normalized_comp}" in title_clean or f"no {normalized_comp}" in title_clean:
            return False

    # 🕵️ 3. LIXO DE BUSCA (Páginas de vagas, perfis sem nome, etc)
    junk_patterns = ["vagas em", "trabalhe na", "talentos", "recrutamento", "vaga para", "visualizar perfil", "quem e", "salario"]
    if any(p in title_clean for p in junk_patterns):
        return False

    # 🕵️ 4. FILTRAGEM POR RELEVÂNCIA (Whitelist vs Blacklist)
    # Se houver uma palavra de ALTO VALOR (Compras, Suprimentos, Sourcing), ignoramos as negativas e passamos para IA.
    # Adicionado variações para capturar posts informativos (como o da Kamila)
    positive_keywords = ["buyer", "comprador", "compras", "purchasing", "suprimentos", "supply", "procurement", "sourcing", "strategic", "logistic", "logistica", "pcp", "expedicao", "estoque", "warehouse", "comercio", "trade", "negociacao", "operacoes", "diretor", "gerente", "manager", "head"]
    has_positive = any(pk in context_clean for pk in positive_keywords)
    
    if has_positive:
        # Se tem algo positivo (cargo ou departamento), deixamos a IA decidir
        return True

    # Só aplicamos o bloqueio de negativas se NÃO houver nenhuma palavra positiva forte
    normalized_negatives = [normalize_str(nk) for nk in negative_keywords]
    if any(nk in context_clean for nk in normalized_negatives):
        return False

    return True
