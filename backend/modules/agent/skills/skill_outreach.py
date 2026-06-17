from typing import List, Dict, Any
from .funnel_stage import FunnelStageSkill

class OutreachSkill(FunnelStageSkill):
    """
    Skill for cold outreach and value generation.
    """
    
    @property
    def name(self) -> str:
        return "Cold Outreach & Value Generation"
        
    @property
    def description(self) -> str:
        return "Executes B2B cold outreach by researching the company context and generating value-led messages."
        
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
            "email_send", 
            "whatsapp_send_message", 
            "pipedrive_update_task", 
            "deep_company_investigation",
            "evaluate_prospects",
            "discover_and_validate_email",
            "suggest_next_actions"
        ]

    @property
    def core_tools(self) -> List[str]:
        return [
            "pipedrive_get_org",
            "pipedrive_get_persons",
            "deep_company_investigation",
            "evaluate_prospects"
        ]
        
    def get_instructions(self, context: Dict[str, Any]) -> str:
        base = (
            "1. Engineer Serendipity: ALWAYS check the company context first if not available.\n"
            "2. Lead with Value: The outreach message MUST reference a specific intent signal "
            "or company characteristic (CNAE, Size, Focus) and offer a specific insight or case study, "
            "NOT just ask for a 30 min meeting.\n"
            "3. TARGET SELECTION: If the task explicitly names the person to contact, DO NOT use `evaluate_prospects` or evaluate other profiles. Proceed directly with that specific person.\n"
            "4. EMAIL VALIDATION: If the task or channel is email, you MUST use the `discover_and_validate_email` tool on the target contact BEFORE calling `generate_sales_message`. This will validate the contact's email or discover the correct one if the current one is invalid.\n"
            "5. CHANNEL SELECTION: You MUST strictly use the channel requested in the task description. If the task says 'Enviar e-mail' or 'email', you MUST use the 'email' channel in `generate_sales_message` and then call `email_send`. NEVER use WhatsApp if the task specifies e-mail, and NEVER try to send a WhatsApp if the contact has no phone number registered.\n"
            "6. STRICT AUTONOMY RULE: NEVER ask for permission in text! Once you generate the draft with `generate_sales_message`, "
            "you MUST IMMEDIATELY call `email_send` or `whatsapp_send_message` with the resulting text (matching the correct channel). "
            "The system will automatically intercept the tool and show an interactive approval card to the user. "
            "Do NOT stop to ask 'Should I send this?'. Calling the send tool IS how you present the draft for approval."
        )
        return base + super().get_instructions(context)

    def get_suggestion_rules(self) -> str:
        base = """
REGRAS OBRIGATÓRIAS DE COLD OUTREACH:
1. FOCO NA CONVERSÃO: As ações sugeridas devem sempre priorizar o envio do material (apresentação, case, e-mail de introdução).
   - Prompt: 'Execute email_send com subject=[ASSUNTO] e body=[CORPO]' ou 'Execute whatsapp_send_message'

2. NÃO DESQUALIFIQUE ANTES DE TENTAR: Se a empresa parece ser Tier C (micro/varejo), não sugira a desqualificação. Sugira um Cold Outreach customizado (produtos de prateleira) e registre o status Tier C em uma nota ou negócio.
"""
        return base + super().get_suggestion_rules()
