"""
modules.agent.service.core.pipelines.meeting
==============================================
Pipeline de Reunião / Visita do agente CRM.
"""
from typing import Any
from modules.agent.service.core.pipelines.base import BasePipeline

class MeetingPipeline(BasePipeline):
    """Pipeline voltada para agendamento de reuniões e visitas."""
    name = "Meeting"
    description = "Pipeline para agendar e marcar reuniões ou visitas comerciais"
    intent_name = "meeting"

    _meeting_keys = [
        "agendar reunião", "agendar meeting", "marcar reunião",
        "agendar visita", "marcar visita", "agendar apresentação",
    ]

    @classmethod
    def matches(cls, subject: str, act_type: str) -> bool:
        s = subject.lower()
        t = (act_type or "").lower()
        return t == "meeting" or any(k in s for k in cls._meeting_keys)

    @classmethod
    def build_steps(cls, subject: str, act_id: Any, org_pd_id: Any, deal_id: Any) -> str:
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → identificar decisor com canal disponível\n"
            f"  2. pipedrive_get_deals → contexto do negócio em andamento\n"
            f"  3. generate_sales_message(goal='agendar reunião/visita') → proposta personalizada de agenda\n"
            f"  4. whatsapp_send_message / email_send → apresentar o convite ao João ANTES de enviar\n"
            f"  5. pipedrive_update_task(activity_id={act_id}, done=true) → marcar concluído após aprovação\n\n"
        )
