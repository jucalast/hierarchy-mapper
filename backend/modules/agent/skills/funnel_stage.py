from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from .base import AgentSkill

@dataclass
class Contact:
    name: str
    phone: Optional[str]
    email: Optional[str]
    role: Optional[str]

@dataclass
class Activity:
    id: int
    subject: str
    type: str
    due_date: str

@dataclass
class SalesContext:
    org_id: int
    org_name: str
    deal_id: int
    deal_stage_id: int
    deal_stage_name: str
    next_stage_id: Optional[int] = None
    next_stage_name: Optional[str] = None
    contacts: List[Contact] = None
    pending_activities: List[Activity] = None
    last_communication: Dict = None
    prospect_evaluation: Dict = None
    temperature: str = None

class SubSkill:
    @property
    def allowed_tools(self) -> List[str]:
        return []
        
    def get_instructions(self, context: Dict[str, Any]) -> str:
        return ""
        
    def get_suggestion_rules(self) -> str:
        return ""

class FunnelStageSkill(AgentSkill):
    def __init__(self, sales_context: SalesContext = None, sub_skills: List[SubSkill] = None):
        self.sales_context = sales_context
        self.sub_skills = sub_skills or []

    @property
    def allowed_tools(self) -> List[str]:
        # Sempre tem pipedrive_update_deal, pipedrive_advance_deal e pipedrive_create_task em allowed_tools
        tools = ["pipedrive_update_deal", "pipedrive_advance_deal", "pipedrive_create_task"]
        for sub in self.sub_skills:
            tools.extend(sub.allowed_tools)
        return list(set(tools))

    def get_advance_prompt(self) -> str:
        if not self.sales_context or not self.sales_context.next_stage_id:
            return ""
        return f"INSTRUÇÃO DE FUNIL: O negócio atual está na etapa '{self.sales_context.deal_stage_name}'. Se a etapa for concluída com sucesso nesta interação, use a ferramenta `pipedrive_advance_deal` passando target_stage='next' para avançar o negócio para '{self.sales_context.next_stage_name}'."
        
    def get_instructions(self, context: Dict[str, Any]) -> str:
        base = ""
        for sub in self.sub_skills:
            sub_inst = sub.get_instructions(context)
            if sub_inst:
                base += f"\n{sub_inst}"
        return base
        
    def get_suggestion_rules(self) -> str:
        base = """
REGRA GLOBAL DE CADÊNCIA (ATIVIDADES PENDENTES):
Se o negócio (deal) não tiver NENHUMA atividade pendente (0 atividades pendentes) E não houver uma próxima ação clara definida pelo usuário, VOCÊ DEVE sugerir a criação de um "Plano de Cadência/Próximos Passos".
- Analise os contatos mapeados: Se o contato SÓ tiver e-mail, crie um plano estritamente focado em envio de e-mails e follow-ups por e-mail. Se tiver WhatsApp/Telefone, intercale os canais de forma inteligente. Nunca sugira ligar/mandar WhatsApp para quem não tem telefone registrado.
- Sugira criar de 2 a 3 tarefas para garantir que o lead não esfrie (ex: 'Enviar e-mail de Prospecção' para hoje, 'Follow-up de e-mail' para 2 dias).
- Prompt sugerido: 'Execute pipedrive_create_task múltiplas vezes para estruturar o plano de cadência personalizado para os canais disponíveis de <EMPRESA>.'
"""
        for sub in self.sub_skills:
            sub_rules = sub.get_suggestion_rules()
            if sub_rules:
                base += f"\n{sub_rules}"
        return base
