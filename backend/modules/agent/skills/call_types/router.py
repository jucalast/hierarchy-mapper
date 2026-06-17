"""
CallTypeRouter: Classifica o tipo de ligação com base no contexto real encontrado pelo agente.
Decide qual sub-skill de ligação usar: cold_call, followup_call, proposal_return ou gatekeeper.

Essa é a implementação da arquitetura "Skill chamando Sub-Skill":
- CallSkill (skill principal) delega para CallTypeRouter
- CallTypeRouter analisa o contexto e retorna o CallType correto
- O CallType define as regras e a estrutura de etapas do Plano de Voo
"""
from __future__ import annotations
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    pass

CallType = Literal["cold_call", "followup_call", "proposal_return", "gatekeeper"]


def classify_call_type(
    goal: str | None,
    is_company_phone: bool,
    has_previous_contact: bool,
    has_open_proposal: bool,
    deal_stage_id: int | None,
    activity_subject: str | None,
) -> CallType:
    """
    Determina o tipo de ligação com base no contexto real coletado pelo agente.

    Prioridade:
    1. Gatekeeper (se for telefone de empresa/recepção)
    2. Cobrança de Retorno de Proposta (se há proposta em aberto + indicador no goal/subject)
    3. Follow-Up de Relacionamento (se já houve contato anterior)
    4. Cold Call (padrão para primeira abordagem)
    """

    # 1. Gatekeeper sempre tem prioridade
    if is_company_phone:
        return "gatekeeper"

    # 2. Cobrança de retorno de proposta
    # Palavras-chave que indicam que o objetivo é cobrar retorno de proposta/orçamento
    proposal_keywords = [
        "retorno da proposta", "retorno do orçamento", "verificar proposta",
        "verificar orçamento", "cobrar proposta", "cobrar orçamento",
        "follow-up da proposta", "followup da proposta", "proposta enviada",
        "orçamento enviado", "resposta da proposta", "resposta do orçamento",
    ]
    # Etapas do funil que indicam proposta em aberto
    proposal_stages = {27, 28, 17}  # Proposta em Andamento, Em Negociação, Proposta (Carteira)

    goal_lower = (goal or "").lower()
    subject_lower = (activity_subject or "").lower()

    is_proposal_goal = any(kw in goal_lower for kw in proposal_keywords)
    is_proposal_subject = any(kw in subject_lower for kw in ["proposta", "orçamento", "retorno"])
    is_proposal_stage = deal_stage_id in proposal_stages

    if has_open_proposal or is_proposal_goal or (is_proposal_subject and is_proposal_stage):
        return "proposal_return"

    # 3. Follow-up de relacionamento (já houve contato anterior)
    followup_keywords = [
        "follow", "followup", "follow-up", "retorno", "verificar interesse",
        "acompanhamento", "ligar de volta", "retornar ligação",
    ]
    is_followup_goal = any(kw in goal_lower for kw in followup_keywords)
    is_followup_subject = any(kw in subject_lower for kw in followup_keywords)

    if has_previous_contact and (is_followup_goal or is_followup_subject or has_previous_contact):
        return "followup_call"

    # 4. Cold Call (padrão)
    return "cold_call"


def get_call_type_config(call_type: CallType) -> dict:
    """
    Retorna as regras e etapas do plano de voo para o tipo de ligação classificado.
    """
    if call_type == "gatekeeper":
        from .gatekeeper import GATEKEEPER_RULES, GATEKEEPER_STEPS
        return {
            "rules": GATEKEEPER_RULES,
            "steps": GATEKEEPER_STEPS,
            "pre_filled_step": "PABX / RECEPÇÃO",  # Única etapa gerada pelo LLM
            "type_label": "Gatekeeper / PABX",
        }
    elif call_type == "proposal_return":
        from .proposal_return import PROPOSAL_RETURN_RULES, PROPOSAL_RETURN_STEPS
        return {
            "rules": PROPOSAL_RETURN_RULES,
            "steps": PROPOSAL_RETURN_STEPS,
            "pre_filled_step": "ABERTURA + REFERÊNCIA DA PROPOSTA",
            "type_label": "Cobrança de Retorno de Proposta",
        }
    elif call_type == "followup_call":
        from .followup_call import FOLLOWUP_CALL_RULES, FOLLOWUP_CALL_STEPS
        return {
            "rules": FOLLOWUP_CALL_RULES,
            "steps": FOLLOWUP_CALL_STEPS,
            "pre_filled_step": "ABERTURA + RETOMADA",
            "type_label": "Follow-Up de Relacionamento",
        }
    else:  # cold_call
        from .cold_call import COLD_CALL_RULES, COLD_CALL_STEPS
        return {
            "rules": COLD_CALL_RULES,
            "steps": COLD_CALL_STEPS,
            "pre_filled_step": "ABERTURA",
            "type_label": "Cold Call (Prospecção Fria)",
        }
