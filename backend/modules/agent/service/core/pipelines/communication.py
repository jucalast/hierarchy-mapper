"""
modules.agent.service.core.pipelines.communication
====================================================
Pipeline de Comunicação Escrita (Email/WhatsApp/Apresentação) do agente CRM.
"""
from typing import Any
from modules.agent.service.core.pipelines.base import BasePipeline

class CommunicationPipeline(BasePipeline):
    """Pipeline voltada para comunicações escritas (E-mail, WhatsApp, Apresentação)."""
    name = "Communication"
    description = "Pipeline para envios de e-mail, WhatsApp e apresentações comerciais"

    _email_msg_keys = [
        "enviar email", "mandar email", "escrever email", "email",
        "apresentação", "apresentar", "enviar whatsapp", "mandar whatsapp",
        "mensagem", "prospectar", "prospecção", "enviar mensagem", "abordagem", "contatar"
    ]

    @classmethod
    def matches(cls, subject: str, act_type: str) -> bool:
        s = subject.lower()
        t = (act_type or "").lower()

        # Ativa se o tipo for email/mensagem ou se contiver palavras-chave correspondentes
        return t in ("email", "mensagem", "whatsapp") or any(k in s for k in cls._email_msg_keys)

    @classmethod
    def build_steps(cls, subject: str, act_id: Any, org_pd_id: Any, deal_id: Any) -> str:
        # Detecta canal preferencial pelo assunto
        s = subject.lower()
        canal_preferencial = "Email"
        if "whatsapp" in s or "whats" in s:
            canal_preferencial = "WhatsApp"

        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → mapear os contatos e encontrar o email/canal correto do decisor.\n"
            f"  2. email_get_contact_history E/OU whatsapp_get_messages → buscar histórico de comunicação do contato selecionado para contextualizar.\n"
            f"  3. generate_sales_message → (OBRIGATÓRIO) criar o rascunho da mensagem personalizada usando o histórico e anotações do CRM.\n"
            f"  4. email_send / whatsapp_send_message → apresentar o rascunho de {canal_preferencial} para aprovação do João no chat.\n"
            f"  5. pipedrive_update_task(activity_id={act_id}, done=true) → marcar como concluída após a aprovação do envio.\n"
            f"⛔ PROIBIDO: NÃO chame generate_call_script e NÃO crie roteiros de ligação, pois esta tarefa é de comunicação escrita.\n"
            f"⛔ PROIBIDO: Nunca envie a mensagem antes do João aprovar no card correspondente.\n\n"
        )
