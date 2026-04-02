import re
import unicodedata
from typing import List, Dict, Optional

# Definições modulares de negócio para mapeamento de Supply Chain
ROLE_LEVELS = [
    (6, r'\b(ceo|sócio|socio|dono|proprietário|presidente|founder|owner|partner|chief|board|conselho|administrador|executive|executivo)\b'),
    (5, r'\b(diretor|director|vice president|vp|general manager|superintendente|direção|head of|headof|regional head)\b'),
    (4, r'\b(gerente|manager|head|group leader|coordenador geral|regional manager|gerência|management|strategy|estratégia|pmo|leader|lead)\b'),
    (3, r'\b(coordenador|coord|supervisor|supv|líder|leader|lead|coordenadora)\b'),
    (2, r'\b(especialista|specialist|senior|sênior|pleno|analista sênior|key account|strategic|sourcing|commodity|category)\b'),
    (1, r'\b(analista|analyst|engenheiro|engineer|buyer|comprador|procurement|suprimentos|negociador|trainee|estagiário|junior|júnior|pj|professional|linkedin)\b')
]

DEPARTMENT_MAP = [
    ("Comex & Comércio Exterior", r'\b(comex|comercio exterior|foreign trade|international trade|export|import|alfandeg|despachante|aduaneiro)\b'),
    ("Compras Estratégicas", r'\b(strategic sourcing|category manager|especialista em embalagem|packaging buyer|raw material buyer|commodity manager|sourcing|intelligence)\b'),
    ("Compras Indiretas / MRO", r'\b(indirect procurement|mro buyer|facility buyer|compras indiretas|comprador mro|compras serviços|facilities|servico|manutencao)\b'),
    ("Logística & Transportes", r'\b(logística|logistic|logistics|supply chain|operações|operations|warehouse|distribuição|transporte|expedição|almoxarife|estoque|frete|shipping|transportation)\b'),
    ("Compras Gerais (Suprimentos)", r'\b(comprador|buyer|compras|procurement|purchasing|suprimentos|negociador|suprimento)\b'),
    ("Diretoria Executiva", r'\b(ceo|presidente|founder|sócio|socio|dono|cpo|diretor|director|vice president|vp|chief|head|regional head)\b')
]

def normalize_str(s: str) -> str:
    """Normaliza strings removendo acentos e convertendo para minúsculas."""
    return "".join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()

def get_seniority_level(role: str) -> int:
    """Classificação hierárquica (1-5) baseada em Expressões Regulares (Word Boundaries)."""
    role = normalize_str(role)
    for level, pattern in ROLE_LEVELS:
        if re.search(pattern, role):
            # Check context to avoid false positives like "Assistente do Diretor" matching "Diretor"
            if level >= 5 and re.search(r'\b(assistente|estagiário|aprendiz|secretária)\b', role):
                return 1
            return level
    return 1  # Nível padrão (Operacional)

def get_department_tag(role: str) -> str:
    """Classificação departamental baseada em Expressões Regulares."""
    role = normalize_str(role)
    for dept, pattern in DEPARTMENT_MAP:
        if re.search(pattern, role):
            return dept
    return "Operations"

def apply_strict_filters(name: str, title: str, body: str, core_company_name: str, brand_name: str, location_focus: str = None, query: str = ""):
    """
    Motor de filtros de ALTA ROBUSTEZ: 
    Agnóstico a empresas, trata variações de marca e amontoados de nomes do LinkedIn.
    """
    full_context = (title + " " + body).lower()
    full_context_norm = normalize_str(full_context)
    
    # 🧩 1. EXPLOSÃO DE VARIANTES DE MARCA (Robustez Total)
    brand_variants = {core_company_name.lower(), brand_name.lower()}
    # Adiciona versão sem espaços para detectar "Böttcherdo", "BöttcherBrasil"
    brand_variants.add(brand_name.replace(" ", "").lower())
    
    # Termos genéricos que NUNCA podem servir de âncora sozinhos
    generic_blacklist = {
        "brasil", "brazil", "group", "holding", "solucoes", "servicos", "industria", 
        "comercio", "ltda", "cia", "ind", "solutions", "services", "unidade", "filial"
    }

    # Adiciona partes do nome da empresa (len >= 3) EXCLUINDO genéricos
    company_parts = [p.lower() for p in re.split(r"[\s,\.-]", brand_name) if len(p) >= 3 and p.lower() not in generic_blacklist]
    brand_variants.update(company_parts)
    brand_variants = {v for v in brand_variants if v}
    brand_regex = r"\b(" + "|".join([re.escape(v) for v in brand_variants]) + r")\b"

    # 🧩 2. DETECÇÃO DE PERFIS COLADOS (Anti-Smash 4.0)
    # Trata especificamente o caso "Böttcherdo", "atBöttcher", "BöttcherBrasil"
    for bv in list(brand_variants):
        clean_bv = re.escape(bv)
        patterns = [
            rf"([a-z]+)({clean_bv})", 
            rf"({clean_bv})([a-z]+)",
            rf"(?i)(at|na|no|da|do|em|na|atualmente|trabalha)({clean_bv})",
        ]
        for p in patterns:
            title = re.sub(p, r"\1 \2", title, flags=re.IGNORECASE)
            body = re.sub(p, r"\1 \2", body, flags=re.IGNORECASE)

    # 🧩 3. FILTRO DE NOME
    if len(name.split()) < 2 or any(kw in name.lower() for kw in ["linkedin", "perfil", "vaga", "job", "...", "perfil profissional"]):
        return None

    # 🧩 4. ISOLAMENTO DE FRAGMENTO (Anti-Contágio / Split de Perfis)
    clean_text = re.sub(r"([||\-–·•])", r" \1 ", title + " " + body[:350])
    fragments = [f.strip() for f in re.split(r"\s*(?:[…\.]{2,}|[||\-–·•])\s*", clean_text) if len(f.strip()) > 5]
    
    name_parts = [p.lower() for p in name.split() if len(p) >= 2]
    context_to_check = ""
    start_idx = -1
    
    for i, frag in enumerate(fragments):
        if any(p in frag.lower() for p in name_parts):
            start_idx = i
            context_to_check = frag
            for jump in range(1, 3):
                if i + jump < len(fragments):
                    next_frag = fragments[i+jump]
                    if re.match(r"^[A-Z][a-z]+\s[A-Z][a-z]+", next_frag): break
                    context_to_check += " " + next_frag
                    if any(bv in next_frag.lower() for bv in brand_variants): break
            break
            
    context_to_check = (context_to_check or (title + " " + body[:350]))
    context_norm = normalize_str(context_to_check)
    
    # 🎯 Match de Proximidade e Explicitude
    supply_keywords_simple = ["procurement", "supply", "compras", "suprimentos", "logistica", "buyer", "comprador", "compradora", "sourcing", "purchas", "cadeia", "warehouse", "comex", "trade", "mro", "s&op"]
    
    words = context_norm.split()
    name_search = name.split()[0].lower()
    
    brand_idx = -1
    name_idx = -1
    for i, w in enumerate(words):
        if name_search in w and name_idx == -1: name_idx = i
        if any(bv in w for bv in brand_variants) and name_search not in w: brand_idx = i

    is_closely_linked = (name_idx != -1 and brand_idx != -1 and abs(name_idx - brand_idx) <= 60)
    
    clean_title = title.lower().replace(name.lower(), "")
    is_explicit = bool(re.search(brand_regex, clean_title, re.IGNORECASE) or re.search(brand_regex, context_norm, re.IGNORECASE))
    
    # 🧩 6. DETECÇÃO DE EX-FUNCIONÁRIO (REFINADA)
    # Buscamos se o marcador de "Presente" está de fato ligado à NOSSA marca.
    is_current_at_our_brand = False
    for bv in brand_variants:
        # Regex que busca a marca seguida de "aprox. 100 caracteres" que contenham "Presente"
        # Ou a marca aparecendo logo após "atualmente na/em"
        if re.search(rf"{re.escape(bv)}.*?\b(presente|present|o momento|momentos|atual|current|atualmente)\b", context_norm, re.IGNORECASE | re.DOTALL):
            is_current_at_our_brand = True
            break
        if re.search(rf"\b(atualmente na|trabalha na|no momento na)\b.*?{re.escape(bv)}", context_norm, re.IGNORECASE | re.DOTALL):
            is_current_at_our_brand = True
            break

    # Se detectamos outra marca explícita (Miba, Ypê, Advance) e ela tem o marcador de "Presente"
    # E a NOSSA marca não tem o marcador de presente no mesmo bloco, é ex-funcionário.
    has_past_keyword = any(re.search(p, context_norm) for p in [
        r'\bex\b', r'\bformerly\b', r'\bpreviously\b', r'\bencerrar ciclo\b', 
        r'\bagradeço à\b', r'\bpassagem pela\b', r'\batou na\b', r'\btrabalhou na\b'
    ])
    
    # Se não está explicitamente como "Presente" na nossa marca E tem indícios de passado, BLOQUEIA.
    if not is_current_at_our_brand and (has_past_keyword or re.search(r'[-–]\s*(\d{4}|\w{3}\.?\s+de\s+\d{4})', context_norm)):
        # Se achamos data de fim (ex: - 2024) colada na nossa marca, bloqueia.
        for bv in brand_variants:
            if re.search(rf"{re.escape(bv)}.*?\b(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.?\s+de\s+\d{{4}}", context_norm, re.I):
                # Se tem data de início mas NÃO tem a palavra "Presente" colada nela, é suspeito
                if not re.search(rf"{re.escape(bv)}.*?\b(presente|present|o momento|atual)\b", context_norm, re.I):
                    return None

    # 🧩 7. FILTRO DE MARCAS INVASORAS (Lógica Universal)
    other_brand_detected = ""
    
    # 🔍 1. Tenta extrair a empresa do Título (Padrão: Nome - Cargo - Empresa | LinkedIn)
    title_parts = [p.strip() for p in re.split(r"[|–\-•·]", title) if len(p.strip()) > 3]
    if len(title_parts) >= 2:
        potential_companies = [pc for pc in title_parts[-2:] if not any(np in normalize_str(pc) for np in name_parts)]
        for pc in potential_companies:
            pc_norm = normalize_str(pc)
            is_our_brand = any(pc_norm in normalize_str(bv) or normalize_str(bv) in pc_norm for bv in brand_variants)
            
            # 🚨 CORREÇÃO CRÍTICA: Ignora se a "empresa detectada" for na verdade um termo de Supply Chain
            is_supply_term = any(skw in pc_norm for skw in supply_keywords_simple)
            
            if not is_our_brand and not is_supply_term and len(pc.split()) <= 4 and not any(kw in pc.lower() for kw in ["perfil", "linkedin", "vagas", "brasil", "conexões", "connections"]):
                 other_brand_detected = pc
                 break

    # 🔍 2. Busca conectores de vinculação explícita no fragmento: "at Samsung", "na GM"
    # Adicionado suporte a "Trabalha na", "Gerente na"
    employment_link = re.search(rf"(at|atualmente na|trabalha na|gerente na|diretora na|na|no|da|do|em|from)\s+([A-Z][a-z\d]+(?:\s+[A-Z][a-z\d]+)?)", context_to_check)
    if employment_link and not other_brand_detected:
        detected_comp = employment_link.group(2)
        is_our_brand = any(normalize_str(detected_comp) in normalize_str(bv) for bv in brand_variants)
        if not is_our_brand:
            other_brand_detected = detected_comp

    # 🔍 3. Detecção Agressiva de Marca Invasora no Contexto (Se tiver Outra Marca + Data Fechada perto de NOUSA marca)
    if not other_brand_detected:
        # Se achamos nossa marca e depois dela vem uma data fechada, é ex-funcionário
        for bv in brand_variants:
            if bv in context_norm:
                after_brand = context_norm[context_norm.find(bv):context_norm.find(bv)+100]
                if re.search(r'(\d{4}|\w{3}\.?\s+de\s+\d{4})\s*[-–]\s*(\d{4}|\w{3}\.?\s+de\s+\d{4})', after_brand):
                    # Nossa marca está associada a uma data fechada
                    if not is_current_at_our_brand:
                        return None

    # 🧩 8. DEPARTAMENTO (Supply Core + Executives)
    # Lista de exclusão setorial (Noise Filter)
    negative_keywords = [
        "customer service", "vendedor", "vendedora", "rh", "hr", "juridicio", "pessoal", "enfermagem", 
        "fiscal", "comunicação", "communication", "it ", "software", "desenvolvedor",
        "sistemas", "totvs", "datasul", "production", "produção", "marketing", "vendas", 
        "comercial", "assistencia", "técnica", "ti ", "engenheiro de produto", "qualidade",
        "manutenção", "mecanico", "mecânico", "usinagem", "operator", "operador",
        "professor", "acadêmico", "estudante", "student", "freelancer", "autônomo"
    ]
    
    # Detecção de Supply Robusta (Adicionado typoss como 'suplly', 'suppl', 'suplimento')
    supply_pattern = r"(procurement|supply\s*chain|suppl[iy]|suplly|compras|purchas|suprimentos|logistica|logística|comprador|compradora|buyer|sourcing|planner|planejamento|pdm|pcp|logistics|suplimento|cadeia\s+de\s+suprimentos|warehouse|armazém|almoxarifado|distribuição|distribution|comex|importação|exportação|trade|mro|s&op|planning|strategic|suprimento)"
    
    # Valida se o termo negativo está no TÍTULO (Mais fatal) ou no contexto
    is_neg = any(kw in clean_title for kw in negative_keywords) or \
             (any(kw in context_norm for kw in negative_keywords) and not any(skw in clean_title for skw in ["compras", "supply", "buyer", "procurement"]))
    
    # Detecção de Supply
    is_procurement = bool(re.search(supply_pattern, context_norm, re.IGNORECASE) or re.search(supply_pattern, full_context_norm, re.IGNORECASE))
    
    # 🚨 REGRA DE OURO (REFINILADÍSSIMA): 
    is_brand_in_full = bool(re.search(brand_regex, full_context_norm, re.IGNORECASE))
    
    # Se detectamos que a query do usuário é de alto nível (Head/Procurement/Manager) e a marca está presente,
    # permitimos a passagem mesmo sem o termo explícito no snippet.
    is_query_strong = any(kw in query.lower() for kw in ["head", "procurement", "manager", "diretor", "gerente", "sourcing"])
    if is_query_strong and is_brand_in_full:
        is_procurement = True

    # Se não detectamos NENHUMA outra marca, e é um cargo de Supply Chain, 
    # confiamos na busca (que já era filtrada por site:linkedin "empresa")
    if is_procurement and not other_brand_detected:
        is_explicit = True # Confiamos na fonte da busca
    
    # BLOQUEIO CRÍTICO: Se detectamos outra marca explícita E ela não é a nossa, BLOQUEIA.
    if other_brand_detected:
        # Só permite se a nossa marca estiver AINDA MAIS próxima (explicitude no título)
        if not is_explicit:
            return None

    # 🎯 MATCH DE CONFIANÇA (Estratégia de Descoberta)
    # Se encontramos a marca e o nome, e não há marca invasora, confiamos na query original do buscador
    is_management = any(kw in context_norm for kw in ["gerente", "manager", "diretor", "director", "diretora", "head", "coordenador", "coordenadora", "coordinator", "supervisor", "lead", "lider"])
    
    # Se a marca é EXATA no título e não há outra marca, permitimos cargos de gestão ou de suprimentos
    is_trusted_match = (is_explicit and not other_brand_detected)
    
    if is_procurement:
        # Aprovação padrão por palavra-chave
        pass 
    elif is_trusted_match and (is_management or is_brand_in_full):
        # Aprovação por confiança na Marca + Cargo de Gestão ou Presença forte da Marca
        # Isso evita bloquear o "Wesley Pinheiro" quando o snippet é "Wesley - Böttcher (Experiência: Böttcher)"
        is_procurement = True 
    else:
        # Se não é procurement nem uma gestão confiável da marca, bloqueia
        return None

    if is_neg:
        return None
        
    is_exec = any(kw in context_norm for kw in ["ceo", "diretor", "director", "cpo", "founder", "gerente", "head", "pmo", "socio", "sócio", "presidente"])

    # Removido o bloqueio absoluto anterior para permitir o is_trusted_match


    # 🧩 9. LOCALIZAÇÃO (Hubs Regionais Agnosticos)
    if location_focus:
        target_city = normalize_str(location_focus.split(",")[0])
        hubs = [target_city, "campinas", "sorocaba", "itu", "jundiai", "indaiatuba", "rmc", "saopaulo", "sp", "brasil", "brazil"]
        is_regional_match = any(h in full_context_norm for h in hubs)
        
        branch_match = re.search(r"\b(unidade|filial|em|na|at|branch)\b\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", title + " " + body)
        if branch_match:
            detected_branch = normalize_str(branch_match.group(2))
            distant_hubs = ["curitiba", "manaus", "fortaleza", "recife", "belem", "porto alegre"]
            if detected_branch in distant_hubs and detected_branch != target_city:
                if not is_regional_match: return None

    return {
        "context_to_check": context_to_check,
        "is_proximate": True 
    }
