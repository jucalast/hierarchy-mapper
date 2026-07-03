"""
modules.agent.service.core._activity_prompts
=============================================
Helpers de geração de prompts para atividades do CRM Pipedrive.

Facade que isola as esteiras/pipelines modularizadas no diretório `pipelines/`
mantendo a retrocompatibilidade de assinaturas públicas para o runner e o loop.
"""
from __future__ import annotations
from typing import Any
from modules.agent.service.core.pipelines import PipelineRegistry

def _dispatch_activity_etapas(subject: str, act_id: Any, org_pd_id: Any, deal_id: Any, act_type: str = "") -> str:
    """
    Dispatcher de etapas: mapeia o subject e o tipo de atividade do Pipedrive
    para um roteiro de execução determinístico delegando à Pipeline correspondente.
    """
    return PipelineRegistry.dispatch(
        subject=subject,
        act_type=act_type,
        act_id=act_id,
        org_pd_id=org_pd_id,
        deal_id=deal_id
    )


def _build_task_action_prompt(act_id: Any, subject: str, org: str, org_pd_id: Any, deal_id: Any, act_type: str, note: str, ctx: dict | None = None) -> str:
    """Gera um prompt inteligente e contextualizado para cada tipo de atividade do Pipedrive."""
    if not ctx: ctx = {}
    company_name = ctx.get("company_name", "J.Ferres")
    seller_name = ctx.get("seller_name", "João Luccas")

    _note_hint = f" (nota: {note})" if note else ""

    # Sem nome de empresa — passa o org_id/deal_id como contexto para o agente raciocinar
    if not org:
        _ctx = f"org_id={org_pd_id}" if org_pd_id else (f"deal_id={deal_id}" if deal_id else "sem empresa vinculada")
        _note_ctx = f"\nNota: {note}" if note else ""
        return (
            f"Você é o assistente comercial de {seller_name} (vendedor da {company_name}).\n\n"
            f"ATIVIDADE #{act_id} A EXECUTAR: {subject}\n"
            f"Contexto CRM: {_ctx}{_note_ctx}\n\n"
            f"Raciocine sobre o que a tarefa requer e use as ferramentas disponíveis para executá-la.\n"
            f"Para ações externas (envios, marcar como concluído), apresente o resultado ao {seller_name.split()[0]} e aguarde aprovação."
        )

    _org_hint = f"\nEmpresa: {org} (org_id={org_pd_id})" if org_pd_id else f"\nEmpresa: {org}"
    _deal_hint_full = f"\nDeal: #{deal_id}" if deal_id else ""
    _note_hint_full = f"\nNota: {note}" if note else ""

    # Dispatcher: etapas específicas por tipo de atividade (com passagem do act_type)
    _etapas = _dispatch_activity_etapas(subject, act_id, org_pd_id, deal_id, act_type)

    return (
        f"Você é o assistente comercial de {seller_name} (vendedor da {company_name}).\n"
        f"O cliente é '{org}' — nunca confunda com a {company_name}.\n\n"
        f"ATIVIDADE #{act_id} A EXECUTAR: {subject}"
        f"{_org_hint}{_deal_hint_full}{_note_hint_full}\n\n"
        f"{_etapas}"
        f"FERRAMENTAS DISPONÍVEIS:\n"
        f"  • pipedrive_get_org / pipedrive_get_persons / pipedrive_get_deals / pipedrive_get_activities\n"
        f"  • whatsapp_get_messages / email_get_contact_history\n"
        f"  • discover_and_validate_email (contact_name, org_name, domain)\n"
        f"  • open_hierarchy_drawer (org_name, org_id, deal_id, activity_id)\n"
        f"  • prepare_live_coaching_session (contact_name, phone)\n"
        f"  • generate_sales_message\n"
        f"  • email_send / whatsapp_send_message\n"
        f"  • pipedrive_update_task / pipedrive_get_activities\n"
        f"  • web_search_external\n\n"
        f"REGRAS DE OURO:\n"
        f"  1. PROIBIDO questionar ou pedir confirmação sobre o nome da empresa '{org}'. Ele é um fato absoluto do CRM.\n"
        f"  2. Se `evaluate_prospects` identificar um decisor (ICP) melhor que o contato da tarefa, VOCÊ DEVE priorizar a abordagem para esse novo decisor. Gere a mensagem para ele imediatamente e explique o motivo no seu raciocínio.\n"
        f"  3. VALIDAÇÃO DE E-MAIL (CONDICIONAL): Se o contato JÁ tiver `email_validated: true` no resultado de `pipedrive_get_persons`, USE esse email diretamente sem chamar `discover_and_validate_email`. Só chame `discover_and_validate_email` se o contato não tiver email ou tiver `email_validated: false`.\n"
        f"  4. Use apenas dados reais retornados pelas ferramentas — nunca invente nomes, números ou histórico.\n"
        f"  5. Para ações externas (enviar mensagem, marcar concluído), apresente ao {seller_name.split()[0]} e aguarde aprovação.\n"
        f"  6. Não marque a atividade #{act_id} como concluída a menos que seja o objetivo explícito da tarefa.\n\n"
        f"Execute agora, começando pelo raciocínio sobre o que a tarefa requer."
    )
