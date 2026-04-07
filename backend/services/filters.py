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
    "financial", "financeiro", "contas", "contabilidade", "accounting", "payables", "receivables"
]

def normalize_str(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return s.strip()

def get_seniority_level(role: str) -> int:
    role = role.lower()
    if any(x in role for x in ["ceo", "president", "presidente", "founder", "socio", "sócio", "owner"]): return 6
    if any(x in role for x in ["diretor", "director", "cpo", "vp", "vice president"]): return 5
    if any(x in role for x in ["gerente", "manager", "head", "lead"]): return 4
    if any(x in role for x in ["coordenador", "coordinator", "supervisor", "lider", "líder"]): return 3
    if any(x in role for x in ["senior", "sênior", "especialista", "specialist", "pleno"]): return 2
    return 1

def get_department_tag(role: str) -> str:
    role = role.lower()
    if any(x in role for x in ["compras", "procurement", "buyer", "comprador", "sourcing", "purchas"]): return "Procurement"
    if any(x in role for x in ["supply", "suprimentos", "cadeia"]): return "Supply Chain"
    if any(x in role for x in ["logistica", "logística", "logistics", "transporte", "distribuição", "warehouse", "armazém", "almoxarifado"]): return "Logistics"
    if any(x in role for x in ["comex", "import", "export", "comércio exterior"]): return "Comex"
    if any(x in role for x in ["planejamento", "planning", "pdm", "pcp"]): return "Planning"
    if any(x in role for x in ["ceo", "diretor", "director", "manager", "gerente", "head", "president"]): return "Executive Management"
    return "Operations"

def apply_strict_filters(name: str, title: str, snippet: str, core_company: str, target_brand: str, target_location: str = None) -> bool:
    """
    PRE-FILTRO DE SEGURANÇA: Bloqueia marcas invasoras e lixo óbvio para economizar API da IA.
    Retorna True se o candidato PARECE ser da empresa certa, False se for lixo óbvio.
    A decisão REAL sobre cargo e departamento agora fica com a IA (RoleEngine).
    """
    title_clean = title.lower().strip()
    snippet_clean = snippet.lower().strip()
    context_clean = f"{title_clean} | {snippet_clean}"
    
    brand_variants = [target_brand.lower(), core_company.lower()]
    if " " in target_brand:
        brand_variants.append(target_brand.split()[0].lower())
    
    # 🕵️ 1. SEGURANÇA DE MARCA (Só passa se a nossa marca estiver presente de alguma forma)
    has_our_brand = any(bv in context_clean for bv in brand_variants)
    
    # RELAXAMENTO: Se for um cargo de compras MUITO relevante, permitimos passar para IA auditar
    # Isso resgata quem tem o cargo no título mas a marca só no corpo escondido
    high_value_keywords = ["buyer", "comprador", "purchasing", "suprimentos", "supply", "procurement", "sourcing", "strategic"]
    is_high_value = any(kw in title_clean for kw in high_value_keywords)

    if not has_our_brand and not is_high_value:
        return False

    # 🕵️ 2. BLOQUEIO DE OUTRAS MARCAS (Anticoncorrente)
    # Se mencionar outras marcas GRANDES no título com "na" ou "at", bloqueia
    other_competitors = ["mercedes", "scania", "volkswagen", "bosch", "zf ", "continental", "gm", "volvo"]
    for comp in other_competitors:
        if f"at {comp}" in title_clean or f"na {comp}" in title_clean or f"no {comp}" in title_clean:
            return False

    # 🕵️ 3. LIXO DE BUSCA (Páginas de vagas, perfis sem nome, etc)
    junk_patterns = ["vagas em", "trabalhe na", "talentos", "recrutamento", "vaga para", "visualizar perfil", "quem é", "salário"]
    if any(p in title_clean for p in junk_patterns):
        return False

    # 🕵️ 4. BLOQUEIO DE DEPARTAMENTOS IRRELEVANTES (Não-Supply Chain)
    if any(nk in context_clean for nk in negative_keywords):
        return False

    return True
