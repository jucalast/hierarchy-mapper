from typing import Any, Optional
from .base import AgentSkill
from .funnel_stage import SalesContext, FunnelStageSkill

from .skill_prospecting import ProspectingSkill
from .skill_outreach import OutreachSkill
from .skill_followup import FollowUpSkill
from .skill_call import CallSkill

# Missing specialized skills just fallback to FollowUpSkill for now,
# but we can map them conceptually.

STAGE_TO_SKILL = {
    # Novos Negócios
    2: ProspectingSkill,    # Entrada -> ProspectingSkill
    18: ProspectingSkill,   # Qualificação -> ProspectingSkill
    19: OutreachSkill,      # Contatado -> OutreachSkill
    4: FollowUpSkill,       # Reunião Agendada -> MeetingSkill (fallback to FollowUp)
    26: FollowUpSkill,      # Reunião Realizada -> MeetingSkill (fallback)
    27: FollowUpSkill,      # Proposta em Andamento -> ProposalSkill (fallback)
    28: FollowUpSkill,      # Em Negociação -> NegotiationSkill (fallback)
    # Clientes Carteira
    14: FollowUpSkill,      # Entrada -> CustomerSuccessSkill
    16: FollowUpSkill,      # Contato -> CustomerSuccessSkill
    17: FollowUpSkill,      # Proposta -> CustomerSuccessSkill
    32: FollowUpSkill,      # Programação -> CustomerSuccessSkill
}

def classify_intent(message: str) -> str:
    """Classifies user intent based on the message."""
    message_lower = message.lower()
    
    # Tarefas de ligação têm precedência máxima
    if any(keyword in message_lower for keyword in ["ligar para", "realizar ligação", "fazer ligação", "ligação", "telefonar", "call"]):
        return "call"
    if any(keyword in message_lower for keyword in ["encontrar", "decisor", "mapear", "prospectar"]):
        return "prospect"
    if any(keyword in message_lower for keyword in ["apresentação", "apresentar", "cold", "outreach", "introdução", "introducao", "enviar e-mail", "enviar email", "enviar mensagem"]):
        return "outreach"
    if any(keyword in message_lower for keyword in ["follow", "cobrar", "ligar", "responder"]):
        return "followup"
    if any(keyword in message_lower for keyword in ["reunião", "agendar"]):
        return "meeting"
    if any(keyword in message_lower for keyword in ["proposta", "desconto", "negociar", "fechar"]):
        return "negotiate"
        
    # If the message doesn't match specific intents but sounds like a direct command
    if any(keyword in message_lower for keyword in ["faça", "envie", "marque", "atualize", "execute", "crie"]):
        return "direct_command"
        
    return "unknown"

def get_skill_by_intent(intent: str) -> AgentSkill:
    INTENT_TO_SKILL = {
        "call": CallSkill,
        "prospect": ProspectingSkill,
        "outreach": OutreachSkill,
        "followup": FollowUpSkill,
        "meeting": FollowUpSkill,      # Fallback
        "negotiate": FollowUpSkill,    # Fallback
        "direct_command": None,        # Direct commands rely on stage
        "unknown": FollowUpSkill       # Default fallback
    }
    skill_class = INTENT_TO_SKILL.get(intent)
    return skill_class() if skill_class else None

async def route_task_to_skill(message: str, org_id: Optional[int] = None, intent_info: Optional[dict] = None) -> AgentSkill:
    """
    FunnelAwareSkillRouter
    Routes based on Pipedrive deal stage and user intent.
    """
    intent = None
    if intent_info:
        intent = intent_info.get("skill_intent")
        if intent == "unknown":
            intent = None

    if not intent:
        intent = classify_intent(message)
    deal_stage_id = None
    deal_id = None
    deal_stage_name = ""
    org_name = ""
    
    if org_id:
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            details = await pipedrive_service.get_organization_details(org_id)
            if isinstance(details, dict):
                org_name = details.get("name", "")
                deals = details.get("deals") or []
                open_deals = [d for d in deals if d.get("status") == "open"]
                if open_deals:
                    deal = open_deals[0]
                    deal_stage_id = deal.get("stage_id")
                    deal_id = deal.get("id")
                    deal_stage_name = "Etapa Desconhecida" # Podemos mapear o nome depois se necessário
        except Exception:
            pass

    # Create SalesContext with the found data
    sales_context = SalesContext(
        org_id=org_id or 0, 
        org_name=org_name, 
        deal_id=deal_id or 0, 
        deal_stage_id=deal_stage_id or 0, 
        deal_stage_name=deal_stage_name
    ) if org_id and deal_stage_id else None

    # 1. Se o intent é CLARO (não unknown e não direct_command), ele tem precedência
    # sobre o stage do funil para respeitar a ordem direta do usuário.
    if intent not in ("unknown", "direct_command"):
        skill_by_intent = get_skill_by_intent(intent)
        if skill_by_intent:
            if isinstance(skill_by_intent, FunnelStageSkill):
                skill_by_intent.sales_context = sales_context
            return skill_by_intent

    # 2. Se o intent é unknown ou direct_command, usa o stage do funil como contexto primário
    skill_by_stage_class = STAGE_TO_SKILL.get(deal_stage_id) if deal_stage_id else None
    
    if skill_by_stage_class:
        return skill_by_stage_class(sales_context)
        
    # 3. Fallback final
    default_skill = FollowUpSkill(sales_context)
    return default_skill
