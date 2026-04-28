"""
Estágio 1 do Pipeline: Classificação de Intenção via LLM.
Analisa a mensagem do usuário e determina o tipo de query, ações e escopos de dados.
"""
import json
from typing import Optional, List
from core.logging_config import get_logger
from services.ai.helpers import MessageInput

log = get_logger(__name__)


async def classify_user_intent(message: str, history: Optional[List[MessageInput]] = None) -> dict:
    """
    Estágio 1 da arquitetura de Pipeline: 
    Usa a IA para classificar a intenção, os parâmetros da busca e o ESCOPO GRANULAR de dados
    antes de dar a resposta. O data_scope define quais fatias de dados buscar.
    """
    from services.ai.llm import LLMTier, ask_llm
    from services.ai.prompts import INTENT_CLASSIFIER_PROMPT
    
    history_str = ""
    if history and len(history) > 0:
        history_lines = []
        # Pega as últimas 6 mensagens de contexto para capturar referências a nomes
        for msg in history[-6:]:
            # Suporte para dict ou objeto Pydantic
            msg_role = msg.get("role") if isinstance(msg, dict) else msg.role
            msg_content = msg.get("content", "") if isinstance(msg, dict) else msg.content
            
            role_br = "Usuário" if msg_role == "user" else "Assistente"
            line = f"{role_br}: {msg_content}"
            
            # Inclui resumo de dados para resolução de referências (ex: tarefa 4)
            msg_summary = msg.get("data_summary") if isinstance(msg, dict) else getattr(msg, "data_summary", None)
            if msg_summary:
                line += f" [Dados exibidos: {msg_summary}]"
                
            history_lines.append(line)
        history_str = "Histórico Recente da Conversa:\n" + "\n".join(history_lines)
    
    prompt = f"""{INTENT_CLASSIFIER_PROMPT}

{history_str}

Mensagem atual do usuário: "{message}"
"""
    try:
        # Usa ask_llm (router) para respeitar preferred_model do request atual
        llm_res = await ask_llm(prompt, json_mode=True, tier=LLMTier.FAST, cacheable=True)
        response = llm_res.json_data if llm_res.json_data is not None else {}
        
        if isinstance(response, dict):
            log.debug("intent.raw_response", response=str(response)[:200] if response else None)
            response["_original_message"] = message
            return _extract_intent(response)
        elif isinstance(response, str):
            try:
                parsed = json.loads(response)
                log.debug("intent.raw_response", response=str(parsed)[:200] if parsed else None)
                parsed["_original_message"] = message
                return _extract_intent(parsed)
            except:
                pass
    except Exception as e:
        log.warning("intent.classification_error", error=str(e))
        
    return {
        "query_type": "general", "data_scope": [], "activity_done_filter": 0,
        "extracted_company_name": None, "whatsapp_action": None,
        "whatsapp_number": None, "whatsapp_message": None, "whatsapp_chat_id": None
    }


def _extract_intent(data: dict) -> dict:
    """Extrai e normaliza o intent de um dict."""
    raw_scope = data.get("data_scope", [])
    # Garante que data_scope é sempre uma lista válida
    if not isinstance(raw_scope, list):
        raw_scope = []
    valid_scopes = {"employees", "decision_makers", "persons", "deals", "activities", "notes", "today_tasks", "whatsapp", "emails"}
    data_scope = [s for s in raw_scope if s in valid_scopes]
    
    # Normalização do filtro de atividades
    done_filter = data.get("activity_done_filter")
    if done_filter not in [0, 1, None]:
        done_filter = 0  # Default para segurança/produtividade
    
    # Normalização do filtro de data
    date_filter = data.get("activity_date_filter") or "today"
    if date_filter not in ["today", "tomorrow", "overdue", "future", "all"]:
        date_filter = "today"
    
    result = {
        "query_type": data.get("query_type", "general"),
        "data_scope": data_scope,
        "activity_done_filter": done_filter,
        "activity_date_filter": date_filter,
        "extracted_company_name": data.get("extracted_company_name"),
        "extracted_person_name": data.get("extracted_person_name"),
        "extracted_deal_stage": data.get("extracted_deal_stage"),
        "extracted_person_hint": data.get("extracted_person_hint"),
        "whatsapp_action": data.get("whatsapp_action"),
        "whatsapp_number": data.get("whatsapp_number"),
        "whatsapp_message": data.get("whatsapp_message"),
        "whatsapp_chat_id": data.get("whatsapp_chat_id"),
        "email_action": data.get("email_action"),
        "email_to": data.get("email_to"),
        "email_subject": data.get("email_subject"),
        "email_body": data.get("email_body"),
        "email_folder": data.get("email_folder")
    }

    # --- FALLBACK MECÂNICO PARA ETAPA (Regex de segurança) ---
    # Se a IA falhou mas a mensagem tem "estágio X" ou "etapa X"
    if not result["extracted_deal_stage"]:
        import re
        stage_match = re.search(r'(?:estágio|etapa|fase|funil)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)', data.get("_original_message", ""), re.IGNORECASE)
        if stage_match:
            result["extracted_deal_stage"] = stage_match.group(1).strip()
            log.debug("intent.stage_regex_fallback", stage=result['extracted_deal_stage'])

    return result
