from typing import List, Dict, Any
from .funnel_stage import FunnelStageSkill


class CallSkill(FunnelStageSkill):
    """
    Skill para execução de ligações telefônicas.
    Foca em obter o número do CRM, preparar o roteiro e abrir a tela de ligação.
    """

    # Regras estruturadas de vendas para centralizar a inteligência das ligações
    SPIN_SELLING_RULES = """
    DIRETRIZES DA METODOLOGIA SPIN SELLING (ABORDAGEM HUMANA, PERSUASIVA E B2B SÊNIOR):
    A regra de ouro é: FUJA de perguntas investigativas frias e diretas ("como vocês gerenciam as caixas?"). Você deve "comprar o direito" de perguntar através de ganchos de autoridade e contexto. Use tom empático, validando as respostas antes de avançar.
    
    ESTRUTURA OBRIGATÓRIA:
    - ABERTURA: Comece com familiaridade local (ex: "somos daqui da região/Indaiatuba") e um Hook mencionando uma dor de mercado comum, perguntando se o cliente também enfrenta isso (ex: "Muitas empresas da região têm enfrentado desafios com avarias... vocês também?"). PROIBIDO citar clientes de referência (Toyota, SEW, etc.) na abertura — guarde a prova social para a etapa de NECESSIDADE. O objetivo aqui é apenas abrir a conversa e detectar a dor.
    - SITUAÇÃO + PROBLEMA: Quando o cliente revelar a dor (ex: "temos avarias no transporte"), COMECE COM EMPATIA. Valide o que ele disse de forma humana (ex: "imagino a dor de cabeça", "isso costuma virar uma bola de neve"). Só então faça a pergunta de implicação/problema de forma fluida.
    - IMPLICAÇÃO: Aprofunde as consequências financeiras ou operacionais (ex: "esse tempo extra tem impactado os prazos de entrega ou gerado custo de retrabalho?"). Mantenha a naturalidade, como uma conversa, não uma entrevista. UMA PERGUNTA POR VEZ — nunca faça "metralhadora" de perguntas.
    - QUALIFICAÇÃO (entre Implicação e Necessidade): Antes de propor solução, qualifique o tamanho da oportunidade com perguntas naturais:
      * Volume: "Pra eu ter uma ideia, quantas caixas vocês expedem por mês, mais ou menos?"
      * Fornecedor atual: "Vocês já trabalham com alguma cartonagem hoje? Estão satisfeitos?"
      * Decisor: "Além de você, quem mais participaria de uma decisão de trocar ou testar um fornecedor novo?"
      Não faça as 3 perguntas de uma vez. Escolha a mais natural para o fluxo da conversa e encaixe as outras conforme a abertura do cliente.
    - NECESSIDADE: AGORA sim, ancore a solução em resultados REAIS e cite provas sociais (ex: "Empresas na mesma situação, como a Toyota, conseguiram reduzir 40% das avarias com essa solução... se desenhássemos algo parecido para vocês, faria sentido?"). A prova social AQUI tem peso máximo porque o cliente já confessou a dor. Não ofereça "embalagens personalizadas" de forma vaga — conecte ao problema específico dele.
    - FECHAMENTO: Sugira o próximo passo com convicção e ancoragem de tempo (Técnica Ou/Ou). MAS exija um contra-compromisso do cliente para gerar reciprocidade e qualificar a visita:
      * Proponha a visita: "O ideal é eu fazer uma visita técnica rápida para entender sua linha. Como está sua agenda para terça de manhã ou quinta à tarde?"
      * Peça informações antecipadas: "Pra eu já vir preparado, você pode me adiantar quais medidas de caixa vocês mais usam?"
      * Mapeie stakeholders: "Além de você, quem mais seria bom participar da visita?"
      Isso faz o cliente INVESTIR na reunião (reciprocidade) e te dá informação para preparar algo concreto.
    """

    OBJECTION_HANDLING_RULES = """
    REGRAS DE CONTORNO DE OBJEÇÃO B2B (COLD CALLS):
    
    REGRA SUPREMA: É terminantemente PROIBIDO concordar passivamente com objeções. NUNCA diga apenas "ok, entendo" e passe para a próxima etapa do SPIN. Toda objeção DEVE ser contornada ANTES de avançar no funil.

    GATILHOS DE OBJEÇÃO (se o cliente disser QUALQUER frase similar a estas, objection_detected = true):
    - "não é um bom momento" / "agora não posso" / "estou ocupado" / "estou em reunião" / "me liga depois"
    - "me manda por e-mail" / "me envia um material" / "manda uma proposta"
    - "já temos fornecedor" / "já estamos atendidos" / "estamos satisfeitos"
    - "não tenho interesse" / "não tenho necessidade" / "no momento não preciso"
    - "não conheço vocês" / "nunca ouvi falar"
    - "está caro" / "não temos orçamento" / "não temos budget"

    CONTORNOS POR TIPO (gere o script PRONTO para o vendedor ler):

    1. PRESSA / "me liga depois":
       → "Entendo perfeitamente, Luciana. Só 30 segundos: muitas empresas da região estão perdendo dinheiro com avarias sem perceber. Vocês têm tido esse tipo de problema? Se sim, eu te proponho uma data pra conversarmos com calma — terça ou quinta, 5 minutinhos?"
       OBJETIVO: Plantar a semente da dor em 30s e ancorar uma data específica.

    2. E-MAIL / "me manda material":
       → "Claro, mando sim! Mas pra eu enviar o material certo e não mais um e-mail genérico: vocês têm sofrido com avarias ou atrasos nas embalagens? Se me contar em 20 segundos, eu personalizo pra vocês."
       OBJETIVO: Qualificar a dor ANTES de perder o controle para o e-mail. Se insistir, ancore data: "Envio agora. Que tal quinta às 10h pra eu te ligar e percorrer o material junto?"

    3. JÁ TEM FORNECEDOR / "estamos atendidos":
       → "Entendo, é bom ter parceiro. E com que frequência vocês enfrentam avarias ou atrasos com eles? Pergunto porque muitos clientes nossos vieram exatamente dessa situação."
       OBJETIVO: Gerar dúvida sobre o fornecedor atual sem atacá-lo diretamente.

    4. SEM NECESSIDADE / "não preciso" / "está bom assim":
       → "Faz sentido. Posso te fazer UMA pergunta rápida? Quando vocês perdem uma caixa por avaria, quanto tempo leva pra refazer o pedido e reembalar? Muitas empresas descobrem que esse custo invisível é maior do que imaginam."
       OBJETIVO: Revelar a "dor oculta" que o cliente não sabe que tem.

    5. NÃO CONHEÇO / "nunca ouvi falar":
       → "Normal, somos uma cartonagem de Indaiatuba, focada em soluções técnicas. Atendemos empresas como [cliente referência] justamente porque resolvemos problemas que as grandes fábricas não conseguem."
       OBJETIVO: Construir credibilidade instantânea.
    """

    @property
    def name(self) -> str:
        return "Execução de Ligação Telefônica"

    @property
    def description(self) -> str:
        return "Executa atividades de ligação: obtém número real do CRM, prepara roteiro SPIN Selling e abre a tela de transcrição ao vivo."

    @property
    def allowed_tools(self) -> List[str]:
        return [
            # Investigação de contexto (fase 1)
            "pipedrive_get_org",
            "pipedrive_get_persons",
            "pipedrive_get_deals",
            "pipedrive_get_activities",
            "deep_company_investigation",
            "evaluate_prospects",
            "whatsapp_get_messages",
            "email_get_contact_history",
            # Busca de contato externo quando não há telefone no CRM (fase 1b)
            "find_company_contact",
            # Execução da ligação (fase 2 — só após investigação completa)
            "prepare_live_coaching_session",
            "open_ligacao_view",
            # Pos-ligacao
            "suggest_next_actions",
            "pipedrive_create_task",
            "pipedrive_update_task",
            "pipedrive_create_note",
            "pipedrive_update_deal",
            "generate_prospecting_plan",
            "open_hierarchy_drawer",
        ]

    @property
    def core_tools(self) -> List[str]:
        # Todas estas devem ser executadas ANTES de prepare_live_coaching_session
        return [
            "pipedrive_get_org",
            "pipedrive_get_persons",
            "pipedrive_get_deals",
            "pipedrive_get_activities",
            "whatsapp_get_messages",
            "email_get_contact_history",
        ]

    def get_instructions(self, context: Dict[str, Any]) -> str:
        base = """Você é um assistente de vendas B2B executando uma tarefa de ligação telefônica. Responda SEMPRE em PORTUGUES.

FASE 1 - INVESTIGACAO COMPLETA (execute nesta ordem, nao pule etapas):
1. pipedrive_get_persons - obter o numero de telefone REAL do CRM para o contato alvo (NUNCA invente).
   SE o contato NAO tiver telefone registrado:
   - Chame find_company_contact com o nome/CNPJ da empresa para buscar na Receita Federal.
   - SE find_company_contact tambem nao encontrar telefone: informe o usuario, escreva 'PARADA ANTECIPADA' e pare.
   - SE find_company_contact ENCONTRAR um telefone: PROSSIGA imediatamente para os passos seguintes, é estritamente proibido encerrar seu turno (end_turn) após receber os resultados.
2. pipedrive_get_deals - verificar estagio do negocio.
3. pipedrive_get_activities - verificar tarefas pendentes.
4. whatsapp_get_messages - verificar historico de WhatsApp com o contato alvo.
5. email_get_contact_history - verificar historico de e-mails com o contato alvo.

FASE 2 - PREPARACAO E ABERTURA (somente APOS a Fase 1 estar 100% concluida):
6. prepare_live_coaching_session(contact_name, phone) - gera o roteiro SPIN Selling usando TODO o contexto coletado acima.
7. OBRIGATÓRIO: IMEDIATAMENTE APÓS a tool acima, chame `open_ligacao_view(contact_name, phone)`. 
   ESTRITAMENTE PROIBIDO: NÃO descreva o plano de voo em texto na conversa, NÃO faça perguntas como "Pronto para inciar a ligação?", e NÃO peça a aprovação do usuário. APENAS CHAME AS DUAS FERRAMENTAS sequencialmente!

REGRAS ABSOLUTAS:
- NUNCA chame prepare_live_coaching_session antes de verificar whatsapp e e-mail e executar as buscas obrigatórias.
- NUNCA chame pipedrive_update_task durante esta atividade (so apos a ligacao terminar).
- NUNCA invente ou assuma um numero de telefone.
- NUNCA envie e-mails ou mensagens sem solicitacao explicita do usuario.
- PROIBIDO PARAR PELA METADE: Após chamar `find_company_contact` e receber os dados de sucesso, você é OBRIGADO a seguir diretamente para as demais ferramentas da Fase 1 e Fase 2. Não termine a execução silenciosamente!
"""
        return base + super().get_instructions(context)

    def get_suggestion_rules(self) -> str:
        base = """
REGRAS DE SUGESTAO POS-LIGACAO:
1. Ligacao concluida: sugira marcar a atividade como feita com pipedrive_update_task.
2. Contato nao atendeu: sugira nova tentativa com pipedrive_create_task.
3. Sem telefone: sugira contato via WhatsApp, e-mail ou visita presencial.
"""
        return base + super().get_suggestion_rules()
