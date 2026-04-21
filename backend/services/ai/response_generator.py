"""
Estágio 2 do Pipeline: Geração da resposta final via LLM.
Monta o prompt com contexto + histórico e gera a resposta estruturada.
"""
import json
from typing import Optional, Dict, Any, List
from services.ai.helpers import ChatResponse, MessageInput, clean_response, format_context_for_prompt
from services.ai.system_prompts import get_system_context


async def generate_ai_response(
    message: str,
    intent_info: dict,
    internal_context: Dict[str, Any],
    history: Optional[List[MessageInput]] = None,
    context_override: Optional[str] = None
) -> ChatResponse:
    """
    Estágio 2: Gera a resposta final com a IA usando dados contextuais.
    """
    from services.external.base_gemini_service import ask_gemini
    
    query_type = intent_info.get("query_type", "general")
    
    # Determina o tipo de contexto do sistema
    system_context_type = query_type
    if query_type == "general" and context_override and context_override != "general":
        system_context_type = context_override
         
    system_context = get_system_context(system_context_type)
    json_instruction = """
Retorne obrigatoriamente um JSON com a seguinte estrutura:
{
  "response": "Sua resposta textual aqui",
  "ui_module": "TaskList" | "ContactGrid" | "CompanyCard" | "WhatsAppThread" | "EmailThread" | null,
  "data_module": { ... }
}
"""
    context_prompt = f"\n\n{format_context_for_prompt(internal_context)}" if internal_context else ""
    history_prompt = ""
    if history:
        hist_lines = [f"{'Você' if m.role == 'user' else 'Eu'} disse: {m.content}" for m in history[-5:]]
        history_prompt = "\n\nHistórico Recente:\n" + "\n".join(hist_lines)
    
    full_prompt = f"{system_context}\n{json_instruction}{context_prompt}{history_prompt}\n\nPergunta: {message}"
    
    response = await ask_gemini(full_prompt, json_mode=True)
    
    if not response:
        return ChatResponse(response="Erro ao processar mensagem.")
    
    response_data = response if isinstance(response, dict) else json.loads(str(response))
    cleaned_response = clean_response(response_data.get("response", ""))
    
    final_data = internal_context.copy()
    ai_data_module = response_data.get("data_module")
    if isinstance(ai_data_module, dict):
        final_data.update(ai_data_module)

    return ChatResponse(
        response=cleaned_response,
        ui_module=response_data.get("ui_module"),
        data=final_data,
        debug={"intent": intent_info}
    )
