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
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem, SEM PULAR NENHUMA):\n"
            f"  1. pipedrive_get_persons → identificar contato com canal (telefone + e-mail)\n"
            f"  2. pipedrive_get_deals(org_id={org_pd_id}) → contexto do negócio (valor, etapa, histórico)\n"
            f"  3a. whatsapp_get_messages(contact, phone, org_name) → histórico WhatsApp\n"
            f"  3b. email_get_contact_history(contact_name, contact_email, org_name) → histórico e-mail\n"
            f"      ⚠️ OBRIGATÓRIO executar AMBAS as buscas (3a E 3b) mesmo que já tenha uma delas.\n"
            f"  4. generate_sales_message(goal='cobrar retorno') → rascunho estratégico\n"
            f"  5. ⚡ CHAMAR A FERRAMENTA DE ENVIO (NÃO APENAS MOSTRAR TEXTO):\n"
            f"      • Se WhatsApp disponível → chame whatsapp_send_message como FERRAMENTA\n"
            f"      • Caso contrário → chame email_reply OU email_send como FERRAMENTA\n"
            f"      ⚠️ Chamar a ferramenta de envio exibirá um card de confirmação ao usuário.\n"
            f"      ⚠️ NÃO escreva o texto do e-mail em prosa na resposta — CHAME A FERRAMENTA.\n"
            f"  6. pipedrive_update_task(activity_id={act_id}, done=true) → APENAS após o card de envio\n"
            f"      ⚠️ Só chame este passo SE E SOMENTE SE a ferramenta do passo 5 retornou ok=true.\n"
            f"⛔ PROIBIDO: NÃO chame pipedrive_update_task antes da ferramenta de envio retornar ok=true.\n"
            f"⛔ PROIBIDO: NÃO escreva o rascunho do e-mail como texto na resposta — use a ferramenta de envio.\n"
            f"⛔ PROIBIDO: NÃO crie nova tarefa — use pipedrive_update_task na atividade {act_id}.\n\n"
        )
