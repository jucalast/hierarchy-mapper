from typing import List, Dict, Any
from .funnel_stage import FunnelStageSkill


class CallSkill(FunnelStageSkill):
    """
    Skill para execução de ligações telefônicas.
    Foca em obter o número do CRM, preparar o roteiro e abrir a tela de ligação.
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
