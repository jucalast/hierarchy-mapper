"""
business_context.py — Inteligência de Negócio da J.Ferres

Este módulo centraliza o conhecimento sobre a empresa, seus produtos, clientes ideais
e metodologias de prospecção B2B. É a "alma" do agente de vendas.

Todos os prompts de prospecção, cold outreach e análise de leads devem importar
daqui para garantir consistência e fácil manutenção.
"""

from __future__ import annotations

# =============================================================================
# IDENTIDADE DA EMPRESA
# =============================================================================

COMPANY_NAME = "J.Ferres"
COMPANY_SEGMENT = "Embalagens de Papelão Ondulado Sob Medida"
COMPANY_DIFFERENTIALS = [
    "Especialistas em embalagens manuais e personalizadas que as grandes fábricas (Klabin, Irani, Papirus) não conseguem ou não querem produzir",
    "Caixas de exportação CKD (Complete Knock Down) com encaixe e montagem personalizados",
    "Modelo Kanban: estoque em fábrica com retirada just-in-time pelo cliente",
    "Atendimento consultivo — acompanhamos o projeto do protótipo até a entrega em série",
    "Calços, envoltórios e tabuleiros de papelão ondulado para proteção de peças industriais",
    "Alta capacidade de adaptação: mudanças de projeto, gramatura e dimensões em ciclo curto",
]

SELLER_NAME = "João Luccas"
SELLER_ROLE = "Representante Comercial"

# =============================================================================
# CATÁLOGO DE PRODUTOS
# =============================================================================

PRODUCTS = {
    "caixas_onduladas": {
        "name": "Caixas de Papelão Ondulado",
        "description": "Caixas corrugadas personalizadas em qualquer dimensão, ondulação (B, C, BC, E) e impressão",
        "use_cases": [
            "Embalagem de peças automotivas para estoque e distribuição",
            "Transporte de componentes industriais entre plantas",
            "Embalagem de linha de montagem (kitting)",
        ],
    },
    "caixas_ckd": {
        "name": "Caixas de Exportação CKD",
        "description": "Embalagens para exportação de veículos e máquinas desmontadas (Complete Knock Down), com encaixe e proteção específicos para cada peça",
        "use_cases": [
            "Exportação de peças automotivas desmontadas",
            "Envio de maquinário industrial em partes",
            "Projetos de exportação com exigências de qualidade e rastreabilidade",
        ],
    },
    "calcos": {
        "name": "Calços de Papelão",
        "description": "Suportes e espaçadores de papelão ondulado para proteção e fixação de peças durante o transporte",
        "use_cases": [
            "Proteção de peças metálicas, plásticas e elétricas durante transporte",
            "Substituição de calços de espuma (mais sustentável e econômico)",
            "Separadores internos de caixa para linhas de montagem",
        ],
    },
    "envoltórios": {
        "name": "Envoltórios de Papelão",
        "description": "Chapas e envoltórios corrugados para proteção superficial de peças e produtos",
        "use_cases": [
            "Proteção de superfícies pintadas ou polidas",
            "Envoltório de bobinas e rolos industriais",
            "Proteção de perfis metálicos e plásticos",
        ],
    },
    "tabuleiros": {
        "name": "Tabuleiros de Papelão Ondulado",
        "description": "Bandejas e tabuleiros para organização e movimentação de peças em linha de produção",
        "use_cases": [
            "Kitting de linha de montagem automotiva",
            "Organização de peças pequenas para montagem manual",
            "Transporte interno de peças entre setores",
        ],
    },
}

# =============================================================================
# PERFIL DE CLIENTE IDEAL (ICP)
# =============================================================================

ICP = {
    "industries": [
        "Autopeças e montadoras",
        "Máquinas e equipamentos industriais",
        "Ferramentas e instrumentos",
        "Motores e componentes elétricos/mecânicos",
        "Exportadores de peças industriais",
        "Fornecedores de linha de montagem (tier 1 e 2)",
    ],
    "company_profiles": [
        "Empresas de médio e grande porte (100+ funcionários) que fabricam e exportam",
        "Indústrias que consomem embalagem em volume contínuo (necessidade recorrente)",
        "Empresas que têm departamento de Compras, Suprimentos ou Supply Chain estruturado",
        "Fornecedores de montadoras (Toyota, Honda, Volkswagen, FCA, GM, Ford)",
        "Empresas com processo de exportação CKD ou similares",
    ],
    "decision_makers": [
        "Gerente / Analista de Compras",
        "Coordenador de Suprimentos",
        "Gerente de Supply Chain / Logística",
        "Gerente de Produção (em empresas menores)",
        "Engenheiro de Embalagens (em empresas maiores)",
    ],
    "pain_points": [
        "Fornecedor atual atrasa ou tem rupturas de estoque frequentes",
        "Embalagem padrão da Klabin/Irani não serve para peças específicas (precisa de customização)",
        "Lead time longo do fornecedor atual — prejudica a linha de produção",
        "Falta de Plano B de fornecimento — risco de parada de linha",
        "Custo de parada de linha muito alto — qualquer atraso de embalagem é crítico",
        "Dificuldade em conseguir embalagem para exportação CKD com especificações técnicas",
        "Fornecedor atual não faz estoque — precisa pedir com muito antecedência",
    ],
    "disqualifiers": [
        "Empresas de varejo ou food/beverage (embalagem primária, não é nosso foco)",
        "Microempresas sem volume consistente",
        "Empresas que só precisam de caixas simples e de baixo valor agregado (commodities)",
    ],
}

# Clientes de referência (podem ser mencionados em cold outreach para construir credibilidade)
REFERENCE_CLIENTS = [
    {"name": "Toyota TMD", "segment": "Montadora automotiva"},
    {"name": "Cobreq", "segment": "Autopeças — baterias e componentes elétricos"},
    {"name": "SEW-Eurodrive", "segment": "Motores e redutores industriais"},
    {"name": "Fast Tools", "segment": "Ferramentas industriais"},
    {"name": "TSA", "segment": "Sistemas de transmissão automotiva"},
    {"name": "Singer do Brasil", "segment": "Máquinas industriais"},
    {"name": "Dayco", "segment": "Correntes e correias automotivas"},
]

# =============================================================================
# PROPOSTA DE VALOR — TEXTOS DE PROSPECÇÃO
# =============================================================================

VALUE_PROPOSITIONS = {
    "plano_b": (
        "Toda indústria que depende de embalagem personalizada precisa de um Plano B. "
        "A J.Ferres atende empresas como Toyota TMD, SEW e Dayco exatamente por isso: "
        "quando o fornecedor principal atrasa, não tem estoque ou não consegue fazer uma caixa específica, "
        "a J.Ferres resolve."
    ),
    "kanban_stock": (
        "Trabalhamos com modelo Kanban: estocamos em fábrica com base no seu consumo histórico "
        "e você retira conforme a demanda — sem pedido mínimo por lote, sem ruptura de linha."
    ),
    "custom_manufacturing": (
        "Produzimos embalagens que Klabin e Irani não fazem: calços, tabuleiros, envoltórios "
        "e caixas CKD com encaixe específico para cada peça. Trabalho manual, rastreável e com protótipo aprovado."
    ),
    "ckd_export": (
        "Somos especialistas em embalagem CKD para exportação. Se a sua empresa exporta peças desmontadas, "
        "desenvolvemos a embalagem junto com a sua engenharia — desde o protótipo até a produção em série."
    ),
    "just_in_time": (
        "Entregamos just-in-time. Sabemos que parada de linha custa caro. "
        "Por isso nosso compromisso é com o prazo, não com o lote mínimo."
    ),
}

# =============================================================================
# METODOLOGIA DE PROSPECÇÃO B2B
# =============================================================================

PROSPECTING_METHODOLOGY = """
METODOLOGIA DE PROSPECÇÃO J.FERRES — GUIA PARA O AGENTE

PRINCÍPIOS FUNDAMENTAIS:
1. RELEVÂNCIA ANTES DE VOLUME: Uma mensagem personalizada vale por 100 genéricas.
2. REFERÊNCIA DE PARES: Mencionar um cliente do mesmo setor/porte aumenta credibilidade em 3x.
3. CANAL CERTO: Email para primeiro contato formal (Compras prefere email). WhatsApp para follow-up se não houver resposta em 5 dias.
4. URGÊNCIA REAL: Não criar urgência falsa. Usar urgência real do setor (parada de linha, exportação, auditoria de fornecedores).
5. CURTO E DIRETO: Decisores de compras recebem dezenas de abordagens. Máximo 5 linhas no primeiro contato.

SEQUÊNCIA DE CADÊNCIA RECOMENDADA:
- Dia 0: Email de primeiro contato (apresentação + referência de par + CTA de reunião curta)
- Dia 4 (sem resposta): WhatsApp direto ("Olá [nome], vi que enviei um email sobre embalagens — faz sentido conversar?")
- Dia 9 (sem resposta): Email de follow-up com ângulo diferente (foco em Plano B ou caso de sucesso)
- Dia 16 (sem resposta): Email de encerramento ("Entendemos se não for o momento. Se mudar, estamos aqui.")

REGRAS DE ABORDAGEM:
- NUNCA mencionar preço no primeiro contato
- SEMPRE personalizar com o setor/produto da empresa prospectada
- SEMPRE terminar com uma pergunta fechada de baixo comprometimento ("Faz sentido marcarmos 15 minutos?")
- NUNCA copiar/colar template genérico — o comprador percebe na hora
- SE a empresa for exportadora: mencionar CKD/exportação como gancho principal
- SE a empresa for fornecedora de montadora: mencionar Toyota TMD / SEW como referência de par
"""

# =============================================================================
# FUNÇÕES UTILITÁRIAS
# =============================================================================

def get_business_context_for_prompt() -> str:
    """
    Retorna um bloco de texto compacto com o contexto de negócio da J.Ferres
    para ser injetado em prompts de prospecção e cold outreach.
    """
    ref_clients = ", ".join([c["name"] for c in REFERENCE_CLIENTS[:5]])
    products = ", ".join([p["name"] for p in PRODUCTS.values()])
    pain_points = "\n".join([f"- {p}" for p in ICP["pain_points"][:4]])
    value_props = "\n".join([f"- {v}" for v in list(VALUE_PROPOSITIONS.values())[:3]])

    return f"""
=== CONTEXTO DA J.FERRES (Vendedor: {SELLER_NAME}) ===
EMPRESA: {COMPANY_NAME} — {COMPANY_SEGMENT}
PRODUTOS: {products}
CLIENTES DE REFERÊNCIA: {ref_clients}
DIFERENCIAIS PRINCIPAIS:
- Fazemos o que Klabin, Irani e Papirus não fazem: embalagem manual, personalizada e CKD para exportação
- Modelo Kanban com estoque em fábrica — just-in-time, sem ruptura
- Atendimento consultivo desde o protótipo

DORES QUE RESOLVEMOS:
{pain_points}

PROPOSTA DE VALOR PARA LEAD FRIO:
{value_props}

PÚBLICO-ALVO: Compras, Suprimentos, Supply Chain em indústrias de autopeças, maquinário, ferramentas e exportadores.
""".strip()


def get_icp_score(company_info: dict) -> dict:
    """
    Pontua um lead com base no ICP da J.Ferres.
    Retorna um dict com score (0-100) e motivos.

    company_info esperado:
    - segment (str): setor/segmento da empresa
    - size (str): porte ("pequena", "media", "grande")
    - exports (bool): se exporta
    - has_purchasing_dept (bool): se tem depto de compras estruturado
    - known_suppliers (list[str]): fornecedores conhecidos
    """
    score = 0
    reasons = []
    penalties = []

    segment = (company_info.get("segment") or "").lower()

    # Setor — pontuação primária
    high_fit_keywords = ["autopeça", "automotivo", "montadora", "motor", "redutor", "transmissão", "ferramenta", "máquina", "equipamento", "exportação"]
    medium_fit_keywords = ["plástico", "borracha", "eletromecânico", "eletrônico", "metalúrgica", "mecânica"]
    low_fit_keywords = ["alimento", "bebida", "cosmétic", "farmac", "varejo", "têxtil"]

    if any(k in segment for k in high_fit_keywords):
        score += 40
        reasons.append("Setor de alto encaixe (autopeças/industrial)")
    elif any(k in segment for k in medium_fit_keywords):
        score += 20
        reasons.append("Setor de encaixe médio (industrial genérico)")
    elif any(k in segment for k in low_fit_keywords):
        score -= 20
        penalties.append("Setor de baixo encaixe para embalagem industrial")

    # Porte
    size = (company_info.get("size") or "").lower()
    if "grande" in size or "grande" in str(company_info.get("employees", 0)):
        score += 20
        reasons.append("Empresa de grande porte — volume consistente")
    elif "media" in size or "médio" in size:
        score += 10
        reasons.append("Empresa de médio porte")

    # Exportação
    if company_info.get("exports"):
        score += 25
        reasons.append("Empresa exportadora — potencial para caixas CKD")

    # Depto de compras estruturado
    if company_info.get("has_purchasing_dept"):
        score += 15
        reasons.append("Departamento de compras estruturado")

    # Fornecedores conhecidos (concorrentes)
    known_suppliers = [s.lower() for s in (company_info.get("known_suppliers") or [])]
    if any(s in known_suppliers for s in ["klabin", "irani", "papirus", "smurfit"]):
        score += 10
        reasons.append("Usa fornecedor grande — abertura para alternativas especializadas")

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


def get_cold_outreach_angle(company_info: dict) -> str:
    """
    Determina o melhor ângulo de abordagem para uma empresa específica.
    Retorna uma string descrevendo o ângulo e os argumentos a usar.
    """
    segment = (company_info.get("segment") or "").lower()
    exports = company_info.get("exports", False)
    org_name = company_info.get("name", "a empresa")

    if exports or any(k in segment for k in ["exportação", "ckd", "internacional"]):
        return (
            f"ÂNGULO: Exportação CKD\n"
            f"USO: {org_name} provavelmente precisa de embalagem específica para exportação de peças desmontadas.\n"
            f"GANCHO: 'Trabalhamos com Toyota TMD e SEW em embalagens CKD para exportação — seria relevante para vocês?'"
        )

    if any(k in segment for k in ["autopeça", "montadora", "tier 1", "tier 2"]):
        return (
            f"ÂNGULO: Plano B para fornecedores de montadora\n"
            f"USO: Fornecedores de montadora têm zero tolerância a falha de embalagem — parada de linha é muito cara.\n"
            f"GANCHO: 'Empresas como Cobreq e Dayco nos usam como Plano B exatamente por isso — qualquer ruptura do fornecedor atual e a linha não para.'"
        )

    if any(k in segment for k in ["ferramenta", "instrumento", "equipamento"]):
        return (
            f"ÂNGULO: Embalagem personalizada para peças específicas\n"
            f"USO: Ferramentas e equipamentos industriais geralmente precisam de embalagem customizada com calços e separadores.\n"
            f"GANCHO: 'Fazemos calços e tabuleiros personalizados para cada peça — o que as grandes fábricas não conseguem fazer.'"
        )

    # Ângulo genérico industrial
    return (
        f"ÂNGULO: Kanban + Just-in-Time\n"
        f"USO: Toda indústria tem dor com supply chain de embalagem. Oferecer o modelo Kanban diferencia.\n"
        f"GANCHO: 'Trabalhamos com estoque em fábrica no modelo Kanban — sem pedido mínimo, sem ruptura de linha.'"
    )
