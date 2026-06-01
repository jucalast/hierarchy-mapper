from typing import List, Dict, Any
from .funnel_stage import FunnelStageSkill

class ProspectingSkill(FunnelStageSkill):
    """
    Skill for Prospecting and Enrichment.
    """
    
    @property
    def name(self) -> str:
        return "Prospecting & Enrichment"
    
    @property
    def description(self) -> str:
        return "Handles B2B prospecting, data enrichment, and Pipedrive synchronization."
    
    @property
    def allowed_tools(self) -> List[str]:
        return [
            "pipedrive_get_org",
            "pipedrive_get_persons",
            "pipedrive_get_deals",
            "pipedrive_get_activities",
            "deep_company_investigation",
            "evaluate_prospects",
            "open_hierarchy_drawer",
            "pipedrive_update_deal",
            "pipedrive_create_person",
            "pipedrive_update_task",
            "suggest_next_actions"
        ]

    @property
    def core_tools(self) -> List[str]:
        return [
            "deep_company_investigation",
            "pipedrive_get_org",
            "pipedrive_get_persons",
            "evaluate_prospects"
        ]
    
    def get_instructions(self, context: Dict[str, Any]) -> str:
        base = """You are executing the Prospecting & Enrichment skill for B2B sales.
Follow these steps strictly:
1. ALWAYS use Data Enrichment (`deep_company_investigation`) first.
2. Output a summary of the Dossier to the user.
3. Fetch the persons (`pipedrive_get_persons`) and evaluate them (`evaluate_prospects`).
4. Apply Multithreading: Try to identify/save at least 2 key decision makers in the hierarchy to avoid single-point failure.
5. If someone exists in local DB `[ID:LocalDB]`, create them in Pipedrive. If they have a numeric ID, link them to the Deal (`pipedrive_update_deal`).
6. Finish the task. VOCÊ É OBRIGADO A CHAMAR A FERRAMENTA `suggest_next_actions` NO FINAL PARA GERAR OS CARDS DE APROVAÇÃO (ex: concluir tarefa, enviar email). NUNCA escreva sugestões de ação diretamente em formato de texto para o usuário. Sempre use a tool `suggest_next_actions`."""
        return base + super().get_instructions(context)

    def get_suggestion_rules(self) -> str:
        base = """
REGRAS OBRIGATÓRIAS DE PROSPECÇÃO:
1. EVITAR CADASTROS DUPLICADOS (CRÍTICO): Se o nome da pessoa já está listado nos 'Contatos Atuais no Pipedrive' (mesmo com variações), você está ABSOLUTAMENTE PROIBIDO de sugerir criar o contato. Apenas sugira 'pipedrive_create_person' se for um contato 100% novo. (João Moura é o vendedor, nunca cadastre ele).
   Prompt caso novo: 'Execute pipedrive_create_person: name=[NOME], email=[EMAIL], org_name=[EMPRESA]'

2. NÃO DESQUALIFIQUE MICROEMPRESAS/VAREJO: Se a empresa for pequena (ex: microempresa, varejo) e não aderir perfeitamente ao ICP ideal, NÃO a desqualifique. Em vez disso, classifique-a como Cliente Tier C. Sugira atualizar a nota ou negócio indicando 'Tier C' e crie uma tarefa de abordagem customizada focada em produtos padronizados ou ticket menor.

3. INTRODUÇÃO E PRIMEIRO CONTATO: Se decisores relevantes (Tier A) foram identificados e não há histórico de comunicação, sua sugestão principal NÃO deve ser apenas 'Criar tarefa'. Você DEVE sugerir o envio imediato da apresentação!
   - Prompt para e-mail: 'Use email_send com to=[EMAIL DO DECISOR], subject="Apresentação J.Ferres - Soluções em Embalagens", body="[Escreva um e-mail de apresentação B2B curto e de alto valor...]" e attachment_name="apresentacao_linkb2b"'
   - Prompt para WhatsApp (se não tiver e-mail): 'Use whatsapp_send_message com contact=[NOME], phone=[TEL], message="[Mensagem de prospecção B2B...]"'
"""
        return base + super().get_suggestion_rules()
