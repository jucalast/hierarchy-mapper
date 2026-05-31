from typing import List, Dict, Any
from .base import AgentSkill

class FollowUpSkill(AgentSkill):
    """
    Skill for Multi-Channel Cadence & Follow-Up.
    """

    @property
    def name(self) -> str:
        return "Multi-Channel Cadence & Follow-Up"

    @property
    def description(self) -> str:
        return "Executes multi-channel follow-ups across email and WhatsApp with value-add insights."

    @property
    def allowed_tools(self) -> List[str]:
        return [
            "pipedrive_get_org",
            "pipedrive_get_persons",
            "pipedrive_get_deals",
            "pipedrive_get_activities",
            "whatsapp_get_messages",
            "email_get_contact_history",
            "generate_sales_message",
            "whatsapp_send_message",
            "email_reply",
            "pipedrive_update_task",
            "suggest_next_actions"
        ]

    @property
    def core_tools(self) -> List[str]:
        return [
            "pipedrive_get_org",
            "pipedrive_get_persons",
            "pipedrive_get_deals",
            "pipedrive_get_activities",
            "whatsapp_get_messages",
            "email_get_contact_history"
        ]

    def get_instructions(self, context: Dict[str, Any]) -> str:
        return """You are executing a B2B sales follow-up task. Follow these instructions strictly:

1. Execute a Multi-Channel approach: It is MANDATORY to fetch history from both email and whatsapp before drafting any response.
2. Value-Add: If it's the 3rd or 4th touch, don't just "check in". Send a valuable insight or case study.
3. Don't mention "I will search WhatsApp" if the contact has no phone. Check silently.
4. Draft the response combining both channels' context.
"""

    def get_suggestion_rules(self) -> str:
        return """
REGRAS OBRIGATÓRIAS DE FOLLOW-UP E NEGOCIAÇÃO:
1. CONCLUIR ATIVIDADE: Se há uma atividade pendente de follow-up e o histórico mostra que já houve uma interação/resposta real recente, sugira marcar essa atividade pendente como feita.
   O 'label' da ação DEVE conter: 'Concluir atividade pendente · [Assunto da Tarefa]'.
   Prompt: 'Execute pipedrive_update_task com activity_id=[ID_NUMERICO] e done=true'

2. ANÁLISE DE OBJEÇÃO DE PREÇO: Se o cliente indicou que nosso preço/orçamento está alto ou comparou com a concorrência:
   - NÃO sugira follow-ups genéricos pedindo reunião.
   - Crie um plano sob medida de 5 tarefas: (1) Estudo interno de custos, (2) Mensagem rápida de alinhamento, (3) Enviar Proposta Revisada, (4) Ligação consultiva, (5) Fechamento.
   - Prompt: 'Execute pipedrive_create_task 5 vezes em sequência para criar o plano de negociação com <EMPRESA>'

3. ENVIAR PROPOSTA COM DESCONTO: Se o vendedor prometeu um desconto e ainda não formalizou, sugira o envio imediato via e-mail ou WhatsApp com o teor exato da proposta.

4. RESPONDER E-MAIL / WHATSAPP: Se há um e-mail ou WhatsApp pendente de resposta, sugira uma resposta comercialmente impecável.
   Prompt: 'Execute email_reply com entry_id=[ID] e body=[TEXTO]'

5. DESQUALIFICAR OFICIALMENTE (LOST): Se o histórico deixar claro que é impossível vender (falência, recusa explícita, ramo incompatível), sugira atualizar o status para perdido.
   Prompt: 'Execute pipedrive_update_deal com deal_id=[ID] e status=lost e lost_reason=[MOTIVO]'
"""
