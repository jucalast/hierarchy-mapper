"""
modules.agent.service.core.pipelines.quote
============================================
Pipeline de Orçamentos e Cotações do agente CRM.
"""
from typing import Any
from modules.agent.service.core.pipelines.base import BasePipeline

class QuotePipeline(BasePipeline):
    """Pipeline voltada para orçamentos, cotações e propostas comerciais."""
    name = "Quote"
    description = "Pipeline para envio e elaboração de orçamentos, cotações e propostas comerciais"

    _quote_keys = [
        "realizar orçamento", "enviar orçamento", "fazer orçamento",
        "cotação", "proposta comercial", "enviar proposta",
    ]

    @classmethod
    def matches(cls, subject: str, act_type: str) -> bool:
        s = subject.lower()
        return any(k in s for k in cls._quote_keys)

    @classmethod
    def build_steps(cls, subject: str, act_id: Any, org_pd_id: Any, deal_id: Any) -> str:
        return (
            f"ETAPAS PARA ESTA ATIVIDADE (siga nesta ordem):\n"
            f"  1. pipedrive_get_persons → identificar contato responsável pela compra\n"
            f"  2. pipedrive_get_deals → detalhes do negócio (produto, volume, histórico)\n"
            f"  3. generate_sales_message(goal='enviar orçamento/cotação') → mensagem de proposta personalizada\n"
            f"  4. email_send / whatsapp_send_message → apresente a proposta ao João ANTES de enviar\n"
            f"  5. pipedrive_update_task(activity_id={act_id}, done=true) → marcar concluído após aprovação\n\n"
        )
