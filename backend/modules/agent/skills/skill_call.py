from typing import List, Dict, Any
from .funnel_stage import FunnelStageSkill


class CallSkill(FunnelStageSkill):
    """
    Skill para execução de ligações telefônicas.
    Foca em obter o número do CRM, preparar o roteiro e abrir a tela de ligação.
    """

    # Regras estruturadas de vendas para centralizar a inteligência das ligações
    SPIN_SELLING_RULES = """
    DIRETRIZES DA METODOLOGIA B2B "VIDA REAL" (ABORDAGEM HUMANA, DIRETA E IMERSIVA):
    A regra de ouro é: FUJA de falas robóticas, jargões genéricos de telemarketing ou textões. Fale exatamente como uma pessoa real conversando na fábrica. Você deve incorporar AS EXATAS PALAVRAS E O MOLEJO que o vendedor usa na vida real.
    
    ESTRUTURA OBRIGATÓRIA (Gere APENAS o bloco de texto curto para o vendedor ler):
    - ABERTURA (Gatekeeper): "Olá, bom dia, tudo bem? Aqui quem fala é o(a) [Seu Nome] da empresa [Sua Empresa], por gentileza você poderia me transferir para a(o) [Nome do Contato, apenas primeiro e segundo nome]?"
    - ABERTURA (Contato Direto): "Legal [Nome do Cliente], prazer, sou vendedor da [Sua Empresa]. Sendo bem direto, nós somos especialistas em [Sua Solução/Produto Principal]. Coisas que os grandes fornecedores do mercado não conseguem ou não querem atender. Então nós entregamos [Exemplo Prático 1 do seu Produto] e [Exemplo Prático 2], que são mais personalizados. Temos ajudado empresas como a [Cliente de Referência 1 do Plano] e a [Cliente de Referência 2 do Plano] a resolver problemas com [Dor Principal que a Empresa resolve, ex: embalagens que não se adaptam], gerando avarias ou retrabalho. Você tem enfrentado algum gargalo com isso ultimamente?"
    - IMPLICAÇÃO (Sem rodeios): "Legal, obrigado pelo feedback. É o seguinte, quando essas falhas acontecem, vocês já mapearam o quanto mais ou menos de operação e de dinheiro que vocês estão deixando na mesa por conta desse retrabalho ou descarte?"
    - QUALIFICAÇÃO (Validação empática e investigação): "Entendi, nossa [Nome], isso é realmente bem sério, né, bem ruim. Mas e esse impacto de [Mencionar a dor dita pelo cliente na ligação, ex: 10% e dois dias perdidos] é realmente significativo. Para eu entender melhor o cenário e como podemos ajudar: quem fornece a solução atual aí para vocês, e onde exatamente a solução deles está falhando, você tem essa informação com você?"
    - NECESSIDADE (Reconhecimento e Solução): "É, realmente eu imagino. Legal que vocês já fizeram esse levantamento, significa que vocês estão atentos e querendo resolver essa questão de gargalos, né? Nós atendemos clientes como a [Cliente de Referência 1 do Plano] e eles tinham exatamente esse problema. Nós aplicamos nossas soluções personalizadas e quase zeramos esses gargalos. Se eu te mostrasse em 15 minutos como fizemos isso, faria sentido para você?"
    - FECHAMENTO (Primeiro): "Legal, [Nome]. Nossa, isso é muito bom né. E para te mostrar esses exemplos e como aplicamos isso na sua operação, o ideal é que a gente pudesse fazer uma reunião rápida em torno de 15 minutos. Ou terça-feira de manhã ou quinta-feira à tarde, que é o que eu tenho liberado aqui na minha agenda. O que fica melhor para você?"
    - FECHAMENTO (Confirmação): "Legal, [Nome], acredito que vai ser muito bom e fica combinado então. [Dia/Horário] está anotado, eu vou te enviar o convite agora mesmo com os detalhes e já adianto o estudo do seu cenário para otimizarmos o nosso tempo, combinado?"
    
    REGRA CRÍTICA PARA AS VARIÁVEIS (PROIBIDO DEIXAR CHAVES/COLCHETES NA SAÍDA FINAL): 
    Você NUNCA deve cuspir as tags [Sua Solução], [Dor Principal], [Exemplo Prático 1] ou [Cliente de Referência 1] no texto que o vendedor vai ler. 
    Você DEVE OBRIGATORIAMENTE ler o "PLANO DE VOO DA LIGAÇÃO" e o "CONTEXTO DA EMPRESA" e SUBSTITUIR essas tags pelos dados reais (ex: trocar [Dor Principal] por "avarias nas embalagens", trocar [Cliente de Referência 1] por "Toyota", etc.). 
    O vendedor vai ler essa frase ao vivo, então ela tem que estar 100% preenchida, sem nenhum colchete ou variável vazia! Se faltar algum dado exato no plano, adapte de forma inteligente com base no contexto geral da empresa.
    """

    OBJECTION_HANDLING_RULES = """
    REGRAS DE CONTORNO DE OBJEÇÃO B2B (MINDSET TÁTICO):
    
    REGRA SUPREMA: Forneça o roteiro completo e persuasivo para o vendedor ler. O objetivo é que ele não precise pensar no que falar, apenas leia a frase com naturalidade. Toda objeção DEVE ser contornada ANTES de avançar no funil. Adapte aos produtos, diferenciais e clientes de referência da empresa!
    
    GATILHOS DE OBJEÇÃO & BRUSH-OFFS (Marcar objection_detected = true se cliente disser):
    - [BRUSH-OFF - Fuga Educada]: "me manda por e-mail", "agora não posso", "me liga depois", "envia uma proposta que eu avalio". (Atenção: Na indústria B2B, pedir e-mail é a forma educada de desligar na sua cara. Aja com urgência tática).
    - [OBJEÇÃO DE STATUS QUO]: "já temos fornecedor", "estamos satisfeitos", "já compramos de outro".
    - [OBJEÇÃO DE NECESSIDADE]: "não temos problema", "acontece pouco e a gente resolve internamente".

    TÁTICAS DE CONTORNO (Gere o bloco de texto completo e natural usando os dados do CONTEXTO):

    1. BRUSH-OFF DE E-MAIL / "Me liga depois":
       → Use a tag [TÁTICA: PEDIR 20 SEGS].
       Exemplo sugerido: "[TÁTICA: 20 SEGS] Entendo perfeitamente, [Nome do Cliente]. A última coisa que quero é encher sua caixa de e-mails genéricos. Em 20 segundos: vocês têm sofrido com [Dor Principal do Produto] ultimamente?"

    2. STATUS QUO / "Já temos fornecedor":
       → Use a tag [TÁTICA: CURIOSIDADE].
       Exemplo sugerido: "[TÁTICA: CURIOSIDADE] Que excelente que já estão bem atendidos. Por curiosidade, quando o fornecedor falha, com que frequência isso afeta a operação de vocês?"

    3. SEM NECESSIDADE / "Acontece pouco" (O cliente está desengajado):
       → Use a tag [TÁTICA: RECUO ESTRATÉGICO]. NÃO avance para [IMPLICAÇÃO] pesada!
       Exemplo sugerido: "[TÁTICA: RECUO] Menos mal. E quando isso chega a acontecer, quanto tempo em média sua equipe perde resolvendo?"

    4. NÃO CONHEÇO / "Nunca ouvi falar":
       → Use a tag [TÁTICA: AUTORIDADE RELÂMPAGO].
       Exemplo sugerido: "[TÁTICA: AUTORIDADE] Normal. Atendemos a [Cliente de Referência 1] e a [Cliente de Referência 2] resolvendo justamente os problemas que os grandes não conseguem. Por isso liguei."

    5. REJEIÇÃO REPETIDA / AGRESSIVA (Após 2 ou 3 recusas):
       → Use a tag [TÁTICA: DESLIGAMENTO EDUCADO].
       Exemplo sugerido: "[TÁTICA: DESLIGAMENTO] Sem problemas, [Nome do Cliente]. Volto a falar com você mês que vem. Um ótimo dia!"
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

FASE 3 - PÓS-LIGAÇÃO (Quando você receber a transcrição do ALERTA DE LIGAÇÃO FINALIZADA):
8. SE você visualizar no histórico recente o texto "[ALERTA DE CONTEXTO: LIGAÇÃO FINALIZADA]" ou uma transcrição de ligação:
   - VOCÊ DEVE PULAR COMPLETAMENTE AS FASES 1 E 2!
   - NUNCA CHAME novamente `prepare_live_coaching_session` ou `open_ligacao_view`.
   - Cumpra a "SUA MISSÃO AGORA" executando as ações no CRM (ex: pipedrive_update_task, pipedrive_create_note, generate_prospecting_plan).

REGRAS ABSOLUTAS:
- NUNCA chame prepare_live_coaching_session antes de verificar whatsapp e e-mail e executar as buscas obrigatórias.
- NUNCA chame pipedrive_update_task durante a Fase 1 ou Fase 2 (só após a ligação terminar na Fase 3).
- NUNCA invente ou assuma um numero de telefone.
- NUNCA envie e-mails ou mensagens sem solicitacao explicita do usuario.
- PROIBIDO PARAR PELA METADE na Fase 1/2.
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
