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
            "discover_and_validate_email",
            "generate_prospecting_plan",
            "suggest_next_actions",
            "whatsapp_get_messages",
            "email_get_contact_history",
            "email_send",
            "whatsapp_send_message"
        ]

    @property
    def core_tools(self) -> List[str]:
        return [
            "pipedrive_get_org",
            "pipedrive_get_persons"
        ]
    
    def get_instructions(self, context: Dict[str, Any]) -> str:
        base = """You are executing the Prospecting & Enrichment skill for B2B sales.
Follow these steps strictly:
1. CHECK context first (`pipedrive_get_org`). Only use Data Enrichment (`deep_company_investigation`) if you do NOT have a saved Dossier or Prospecting Plan.
2. Fetch the persons (`pipedrive_get_persons`). 
3. Generate a Prospecting Plan (`generate_prospecting_plan`) if one does not exist yet. ESTA ETAPA É OBRIGATÓRIA antes de decidir quem salvar.
4. Output a summary of the context/Dossier and the Prospecting Plan to the user.
5. Evaluate the persons (`evaluate_prospects`) based on the Prospecting Plan to identify the most suitable decision maker(s) (o contato mais apto).
6. Apply Multithreading: Try to identify/save at least 2 key decision makers in the hierarchy to avoid single-point failure.
7. ONLY AFTER evaluating the most suitable person(s) based on the plan, if they exist in local DB `[ID:LocalDB]`, suggest to create them in Pipedrive. If they have a numeric ID, link them to the Deal (`pipedrive_update_deal`).
8. Finish the task. VOCÊ É OBRIGADO A CHAMAR A FERRAMENTA `suggest_next_actions` NO FINAL PARA GERAR OS CARDS DE APROVAÇÃO (ex: concluir tarefa, enviar email). NUNCA escreva sugestões de ação diretamente em formato de texto para o usuário. Sempre use a tool `suggest_next_actions`."""
        # Injeta instrução de concluir tarefa se o activity_id foi mencionado no prompt
        activity_id = context.get("activity_id")
        if activity_id:
            base += f"\n\n⚠️ TAREFA DE ORIGEM: Esta atividade foi iniciada a partir da tarefa CRM activity_id={activity_id}. Após concluir o mapeamento de contatos e vincular ao negócio, você DEVE incluir como uma das sugestões marcar esta tarefa como concluída: `pipedrive_update_task(activity_id={activity_id}, done=true)`."
        return base + super().get_instructions(context)

    def get_suggestion_rules(self) -> str:
        base = """
REGRAS OBRIGATÓRIAS DE PROSPECÇÃO:
1. EVITAR CADASTROS DUPLICADOS (CRÍTICO): Se o nome da pessoa já está listado nos 'Contatos Atuais no Pipedrive' (mesmo com variações), você está ABSOLUTAMENTE PROIBIDO de sugerir criar o contato. Apenas sugira 'pipedrive_create_person' se for um contato 100% novo. (João Moura é o vendedor, nunca cadastre ele).
   Prompt caso novo: 'Execute pipedrive_create_person: name=[NOME], email=[EMAIL], org_name=[EMPRESA]'

2. NÃO DESQUALIFIQUE MICROEMPRESAS/VAREJO: Se a empresa for pequena (ex: microempresa, varejo) e não aderir perfeitamente ao ICP ideal, NÃO a desqualifique. Em vez disso, classifique-a como Cliente Tier C. Sugira atualizar a nota ou negócio indicando 'Tier C' e crie uma tarefa de abordagem customizada focada em produtos padronizados ou ticket menor.

3. INTRODUÇÃO E PRIMEIRO CONTATO: Se decisores relevantes (Tier A) foram identificados e não há histórico de comunicação, você DEVE sugerir o contato inicial!
   - Apresentação via E-mail: Em vez de envio imediato, sugira SEMPRE a criação de uma tarefa no CRM para o envio da apresentação (ex: 'Execute pipedrive_create_task com subject="Enviar apresentação institucional para [Nome]"').
   - Abordagem via WhatsApp: APENAS se o contato possuir um telefone explícito listado no histórico. NUNCA sugira envio de WhatsApp se não houver número de telefone. Sugira 'Use whatsapp_send_message com contact=[NOME], phone=[TEL], message="[Mensagem...]"'

4. CONCLUIR TAREFA DE ORIGEM (CRÍTICO): Se o usuário mencionou um ID de tarefa (ex: "ID da tarefa no Pipedrive: XXXX" ou "activity_id=XXXX") no prompt original, você DEVE obrigatoriamente incluir como uma das sugestões a conclusão dessa tarefa:
   - Prompt: 'Execute pipedrive_update_task com activity_id=[ID_MENCIONADO] e done=true para marcar a tarefa de busca de contato como concluída.'
   - Esta sugestão deve ter label "Marcar tarefa como concluída" e deve ser incluída SEMPRE que um activity_id estiver presente no contexto.
"""
        return base + super().get_suggestion_rules()
