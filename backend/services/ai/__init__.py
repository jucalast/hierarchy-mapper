"""
Módulo AI — Pipeline de Inteligência Artificial em dois estágios.

Estágio 1: Classificação de Intenção (intent_classifier)
Estágio 2: Geração de Resposta (response_generator)

Orquestrado pelo endpoint em api/v1/endpoints/ai.py.
"""
from services.ai.helpers import ChatMessage, ChatResponse, CompanyInfo, MessageInput
from services.ai.intent_classifier import classify_user_intent
from services.ai.action_executor import execute_whatsapp_action, execute_email_action
from services.ai.data_fetcher import resolve_organization, fetch_contextual_data, execute_osint_enrichment
from services.ai.bypass_handler import try_bypass_response
from services.ai.response_generator import generate_ai_response

__all__ = [
    "ChatMessage", "ChatResponse", "CompanyInfo", "MessageInput",
    "classify_user_intent",
    "execute_whatsapp_action", "execute_email_action",
    "resolve_organization", "fetch_contextual_data", "execute_osint_enrichment",
    "try_bypass_response",
    "generate_ai_response",
]
