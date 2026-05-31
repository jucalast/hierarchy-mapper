from typing import List, Dict, Any
from .base import AgentSkill

class OutreachSkill(AgentSkill):
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
            "generate_sales_message", 
            "email_send", 
            "whatsapp_send_message", 
            "pipedrive_update_task", 
            "deep_company_investigation",
            "suggest_next_actions"
        ]

    @property
    def core_tools(self) -> List[str]:
        return [
            "pipedrive_get_org",
            "pipedrive_get_persons",
            "deep_company_investigation"
        ]
        
    def get_instructions(self, context: Dict[str, Any]) -> str:
        return (
            "1. Engineer Serendipity: ALWAYS check the company context first if not available.\n"
            "2. Lead with Value: The outreach message MUST reference a specific intent signal "
            "or company characteristic (CNAE, Size, Focus) and offer a specific insight or case study, "
            "NOT just ask for a 30 min meeting.\n"
            "3. Draft the message using `generate_sales_message` and present it to the user. "
            "Send only upon approval."
        )

    def get_suggestion_rules(self) -> str:
        return """
REGRAS OBRIGATÓRIAS DE COLD OUTREACH:
1. FOCO NA CONVERSÃO: As ações sugeridas devem sempre priorizar o envio do material (apresentação, case, e-mail de introdução).
   - Prompt: 'Execute email_send com subject=[ASSUNTO] e body=[CORPO]' ou 'Execute whatsapp_send_message'

2. NÃO DESQUALIFIQUE ANTES DE TENTAR: Se a empresa parece ser Tier C (micro/varejo), não sugira a desqualificação. Sugira um Cold Outreach customizado (produtos de prateleira) e registre o status Tier C em uma nota ou negócio.
"""
