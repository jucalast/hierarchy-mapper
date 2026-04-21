"""
Lógica de Bypass — retorna dados brutos ao frontend sem passar pela IA (Estágio 2),
quando a intenção é clara o suficiente (tarefas, contatos, WhatsApp, Email).
"""
from typing import Optional, Dict, Any
from services.ai.helpers import ChatResponse
from services.ai.contact_enrichment import enrich_contacts_for_grid, complete_partial_emails


def try_bypass_response(
    intent_info: dict,
    internal_context: Dict[str, Any],
    whatsapp_result_context: Optional[Dict],
    email_result_context: Optional[Dict]
) -> Optional[ChatResponse]:
    """
    Tenta retornar uma resposta bypass (sem IA) para tipos de query que não precisam
    de processamento de linguagem natural adicional.
    
    Retorna ChatResponse se bypass foi ativado, None caso contrário.
    """
    query_t = intent_info.get("query_type")
    
    # ==========================================
    # BYPASS PARA TAREFAS E CONTATOS
    # ==========================================
    if query_t in ["pipedrive_tasks", "contacts"]:
        return _bypass_tasks_or_contacts(query_t, intent_info, internal_context)

    # ==========================================
    # BYPASS PARA WHATSAPP (Ações de Envio de Mensagem)
    # ==========================================
    is_wa_send = intent_info.get("query_type") == "whatsapp" and intent_info.get("whatsapp_action") in ["send_message", "send"]
    wa_ctx = internal_context.get("whatsapp_result", {})
    
    if is_wa_send:
        if wa_ctx.get("status") == 200:
            print("[AI Pipeline] ⚡ Bypass WhatsApp acionado (Sucesso).")
            return ChatResponse(
                response=f"Sua mensagem para {wa_ctx.get('contact', {}).get('name', 'o contato')} foi enviada!",
                ui_module="WhatsAppThread",
                data=internal_context,
                debug={"intent": intent_info, "bypass": True}
            )

    # ==========================================
    # BYPASS PARA EMAIL (Ações de Envio de Email)
    # ==========================================
    is_email_send = intent_info.get("query_type") == "email" and intent_info.get("email_action") == "send_email"
    email_ctx = internal_context.get("email_result", {})
    
    if is_email_send:
        if email_ctx.get("status") == 200:
            print("[AI Pipeline] ⚡ Bypass Email acionado (Sucesso).")
            return ChatResponse(
                response=f"Seu e-mail para {email_ctx.get('to')} foi enviado com sucesso via Outlook!",
                ui_module="EmailThread",
                data=internal_context,
                debug={"intent": intent_info, "bypass": True}
            )
        else:
            # Se deu erro, deixa seguir para o Estágio 2 onde a IA vai explicar o erro.
            print(f"[AI Pipeline] ⚠️ Falha no envio de e-mail detectada (Status {email_ctx.get('status')}). Seguindo para explicação da IA.")

    return None


def _bypass_tasks_or_contacts(query_t: str, intent_info: dict, internal_context: Dict[str, Any]) -> ChatResponse:
    """Bypass para TaskList e ContactGrid."""
    org_name = internal_context.get("organization", {}).get("name")
    
    if query_t == "pipedrive_tasks":
        target_text = f" da {org_name}" if org_name else " agendadas"
        response_msg = f"Aqui estão as tarefas{target_text} no Pipedrive:"
        u_mod = "TaskList"
    else:
        target_text = f" da {org_name}" if org_name else ""
        stats = internal_context.get("statistics", {})
        count = stats.get("total_employees_mapped") or stats.get("total_employees") or 0
        
        # PREPARAÇÃO DE DADOS PARA CONTACTGRID (ACHATAR LISTA E MAPEAR SENIORIDADE)
        filtered_list = enrich_contacts_for_grid(internal_context)
        
        # Injeta a lista flat no contexto para o front-end
        internal_context["persons"] = filtered_list
        
        # --- ENRIQUECIMENTO DE DADOS PARA O CARD ---
        complete_partial_emails(filtered_list, internal_context)

        response_msg = f"Localizei {count} funcionários mapeados{target_text}:" if count > 0 else f"Não encontrei funcionários mapeados{target_text}."
        u_mod = "ContactGrid"

    print(f"[AI Pipeline] ⚡ Bypass de IA ativado para {query_t}. Retornando dados brutos.")
    return ChatResponse(
        response=response_msg,
        ui_module=u_mod,
        data=internal_context,
        debug={"intent": intent_info, "bypass": True}
    )
