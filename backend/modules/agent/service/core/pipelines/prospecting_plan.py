"""
modules.agent.service.core.pipelines.prospecting_plan
======================================================
Pipeline para geração de Plano de Prospecção B2B (SPIN Selling).
Detecta quando o usuário pede um plano de prospecção (via atividade CRM ou chat livre)
e instrui o agente a gerar um plano estruturado usando os dados já coletados.
"""
from typing import Any
from modules.agent.service.core.pipelines.base import BasePipeline


class ProspectingPlanPipeline(BasePipeline):
    """Pipeline voltada para geração de Plano de Prospecção SPIN Selling."""
    name = "ProspectingPlan"
    description = "Pipeline para gerar plano de prospecção B2B com SPIN Selling baseado em dados coletados"
    intent_name = "prospecting_plan"

    _plan_keys = [
        "plano de prospecção", "plano de prospecao", "plano de prospeccao",
        "plano de prospeção", "plano de prospeçao",
        "gerar plano", "criar plano", "montar plano",
        "estratégia de prospecção", "estrategia de prospeccao",
        "como abordar", "como prospectar", "abordagem de vendas",
        "plano de abordagem", "roteiro de prospecção", "roteiro de prospeccao",
        "plano spin", "spin selling", "plano de vendas",
        "sequência de abordagem", "sequencia de abordagem",
    ]

    @classmethod
    def matches(cls, subject: str, act_type: str) -> bool:
        s = subject.lower()
        return any(k in s for k in cls._plan_keys)

    @classmethod
    def build_steps(cls, subject: str, act_id: Any, org_pd_id: Any, deal_id: Any) -> str:
        _act_suffix = f", activity_id={act_id}" if act_id else ""
        _deal_suffix = f", deal_id={deal_id}" if deal_id else ""
        return (
            f"🎯 MISSÃO: Investigar o histórico de relacionamento e gerar um Plano de Prospecção SPIN Selling completo.\n"
            f"ETAPAS (siga com calma e inteligência, EXATAMENTE nesta ordem):\n"
            f"  1. Chame `pipedrive_get_org(org_id={org_pd_id})` para coletar dados da organização e deals do CRM.\n"
            f"  2. Chame `pipedrive_get_persons(org_id={org_pd_id})` para mapear os contatos/decisores cadastrados.\n"
            f"  3. Com os contatos mapeados, chame `batch_communication_search` para buscar todo o histórico de WhatsApp e E-mail de uma só vez.\n"
            f"     ⚠️ OBRIGATÓRIO: Sempre execute a busca de histórico para garantir que o plano use a prospecção real do vendedor.\n"
            f"  4. Chame `generate_prospecting_plan(org_id={org_pd_id}, force_regenerate=true)` para cruzar a investigação e gerar o plano SPIN.\n"
            f"  5. Apresente o plano ao usuário em formato Markdown rico no chat.\n"
            f"  6. Ofereça sugestões de próximas ações usando `suggest_next_actions`.\n"
            + (f"  7. Conclua a atividade: `pipedrive_update_task(activity_id={act_id}, done=true)`.\n" if act_id else "")
            + f"⛔ PROIBIDO: Não invente dados — use APENAS o que foi coletado nas ferramentas.\n"
            f"⛔ PROIBIDO: Não use placeholders genéricos — o plano deve ter nomes e dados reais.\n\n"
        )
