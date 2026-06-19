"""
modules.agent.service.core.pipelines.followup
================================================
Pipeline de Cobrança / Follow-up do agente CRM.
"""
from typing import Any
from modules.agent.service.core.pipelines.base import BasePipeline

class FollowupPipeline(BasePipeline):
    """Pipeline voltada para follow-up e cobrança de retorno."""
    name = "Followup"
    description = "Pipeline para acompanhamento, cobranças e follow-ups comerciais"
    intent_name = "followup"

    _followup_keys = [
        "cobrar retorno", "cobrar resposta", "follow", "acompanhamento",
        "follow-up", "retorno", "dar retorno", "verificar retorno",
    ]

    @classmethod
    def matches(cls, subject: str, act_type: str) -> bool:
        s = subject.lower()
        return any(k in s for k in cls._followup_keys)

    @classmethod
    def build_steps(cls, subject: str, act_id: Any, org_pd_id: Any, deal_id: Any) -> str:
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → identificar contato com canal (telefone + e-mail)\n"
            f"  2. pipedrive_get_deals(org_id={org_pd_id}) → contexto do negócio (valor, etapa, histórico)\n"
            f"  3a. whatsapp_get_messages(contact, phone, org_name) → histórico WhatsApp\n"
            f"  3b. email_get_contact_history(contact_name, contact_email, org_name) → histórico e-mail\n"
            f"      ⚠️ OBRIGATÓRIO executar AMBAS as buscas (3a E 3b) mesmo que já tenha uma delas.\n"
            f"      O gerador de mensagem usa TODO o histórico combinado — nunca pule o e-mail.\n"
            f"  4. generate_sales_message(goal='cobrar retorno da proposta/cotação') → rascunho de follow-up estratégico\n"
            f"      (usa automaticamente tudo que foi coletado nos passos anteriores)\n"
            f"  5. whatsapp_send_message OU email_reply/email_send → apresente ao João ANTES de enviar\n"
            f"      Canal preferencial: WhatsApp se tiver histórico ativo; e-mail se o último contato foi por e-mail.\n"
            f"  6. pipedrive_update_task(activity_id={act_id}, done=true) → marcar concluído após aprovação\n"
            f"⛔ PROIBIDO: NÃO crie nova tarefa — use pipedrive_update_task na atividade {act_id}.\n"
            f"⛔ PROIBIDO: NÃO gere a mensagem sem antes executar AMBAS as buscas de histórico (3a e 3b).\n\n"
        )
