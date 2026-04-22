"""
Endpoint de Chat com IA — Thin Router.
Orquestra o pipeline de 2 estágios delegando para os módulos em services/ai/.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import re
import asyncio
import json

from core.database import get_db
from services.ai.helpers import ChatMessage, ChatResponse
from services.ai.intent_classifier import classify_user_intent
from services.ai.action_executor import execute_whatsapp_action, execute_email_action
from services.ai.data_fetcher import resolve_organization, fetch_contextual_data, execute_osint_enrichment
from services.ai.bypass_handler import try_bypass_response
from services.ai.response_generator import generate_ai_response
from services.ai.logger import dump_intelligence_context

router = APIRouter()

def clean_history(history: list) -> list:
    """Remove logs e dados pesados do histórico para economizar tokens e evitar erros de limite de payload."""
    if not history: return []
    cleaned = []
    # Pegamos apenas as últimas 5 mensagens para não estourar o contexto
    for entry in history[-5:]:
        # Garante que tratamos tanto dict quanto objeto Pydantic
        is_pydantic = hasattr(entry, "dict")
        h_dict = entry.dict() if is_pydantic else entry.copy()
        
        # Remove campos que poluem o contexto e aumentam o tamanho do request
        if "logs" in h_dict: del h_dict["logs"]
        if "debug" in h_dict: del h_dict["debug"]
        
        # No histórico, o 'data' de mensagens passadas do assistente é irrelevante e pesado
        if h_dict.get("role") == "assistant" and "data" in h_dict:
            del h_dict["data"]
        
        # Truncagem agressiva de conteúdo para caber em modelos menores (Groq Free Tier)
        content = h_dict.get("content", "")
        if content and len(content) > 1200:
            h_dict["content"] = content[:1200] + "... [Conteúdo Truncado para Economia de Contexto]"

        if "data" in h_dict: 
            # Se o dado for muito grande (ex: lista de tarefas), remove ou resume
            if isinstance(h_dict["data"], (list, dict)) and len(str(h_dict["data"])) > 300:
                h_dict["data"] = {"summary": "Dados omitidos para preservar limite de tokens"}
        
        cleaned.append(h_dict)
    return cleaned


class AgentActionRequest(PydanticBaseModel):
    action_id: str
    approved: bool


@router.post("/chat")
async def chat_with_ai(
    payload: ChatMessage,
    session: AsyncSession = Depends(get_db)
):
    """
    Endpoint para chat com IA usando Gemini com RAG (Retrieval Augmented Generation).
    Arquitetura de Pipeline LLM em dois estágios:
    1. Classificação de Intenção (Qual o contexto necessário?)
    2. Geração da Resposta (Com base nos dados precisos fornecidos)
    """
    try:
        if not payload.message or not payload.message.strip():
            raise HTTPException(status_code=400, detail="Mensagem vazia")

        # --- LIMPEZA DE HISTÓRICO ---
        cleaned_history = clean_history(payload.history or [])

        # --- ESTÁGIO 1: Classificação de Intenção (Pipeline Routing) ---
        print(f"[AI Pipeline] Estágio 1 - Analisando intenção do usuário com histórico de {len(cleaned_history)} mensagens...")
        intent_info = await classify_user_intent(payload.message, cleaned_history)
        
        # HEURÍSTICA MECÂNICA: Se o usuário quer mandar email e a IA falhou em detectar o tipo
        if "email para" in payload.message.lower() or "mandar email" in payload.message.lower() or "enviar email" in payload.message.lower():
            if intent_info.get("query_type") != "email":
                print("[AI Pipeline] Corrigindo intenção mecanicamente para 'email'")
                intent_info["query_type"] = "email"
                if not intent_info.get("email_action"):
                    intent_info["email_action"] = "send_email"
        
        # Extração mecânica de email se estiver faltando
        if intent_info.get("query_type") == "email" and not intent_info.get("email_to"):
            emails_found = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', payload.message)
            if emails_found:
                intent_info["email_to"] = emails_found[0]
                print(f"[AI Pipeline] Email extraído mecanicamente: {intent_info['email_to']}")
        
        query_type = intent_info.get("query_type", "general")
        extracted_name = intent_info.get("extracted_company_name")
        print(f"[AI Pipeline] Intenção detectada: {query_type}")

        # --- AÇÃO WHATSAPP ---
        whatsapp_result_context = None
        if query_type == "whatsapp":
            whatsapp_result_context = await execute_whatsapp_action(intent_info, session)

        # --- AÇÃO EMAIL ---
        email_result_context = None
        if query_type == "email":
            email_result_context = await execute_email_action(intent_info)

        # --- RESOLUÇÃO DE ORGANIZAÇÃO ---
        org_id = await resolve_organization(
            payload.orgId,
            payload.selectedCompanies or [],
            extracted_name,
            payload.message,
            session
        )

        # --- AÇÃO DE ENRIQUECIMENTO OSINT ---
        internal_context = {}
        if query_type == "enrichment":
            osint_context = await execute_osint_enrichment(intent_info, org_id, session)
            if osint_context:
                internal_context.update(osint_context)

        # Converte os modelos Pydantic da UI em dicts para não dar erro de serialização no Log
        selected_entities_dicts = [c.dict() for c in (payload.selectedCompanies or [])]

        # --- BUSCA DE DADOS CONTEXTUAIS ---
        fetched_data = await fetch_contextual_data(
            intent_info, org_id, payload.message, session, 
            selected_entities=selected_entities_dicts
        )
        internal_context.update(fetched_data)
        internal_context["selected_entities"] = selected_entities_dicts

        # Injeta resultados de ações no contexto
        if whatsapp_result_context:
            internal_context["whatsapp_result"] = whatsapp_result_context
        if email_result_context:
            internal_context["email_result"] = email_result_context

        data_scope = intent_info.get("data_scope", [])
        print(f"[AI Pipeline] Estágio 2 - Alimentando o modelo final com dados da query do tipo: {query_type} | scopes: {data_scope}...")

        # --- LOG DE CONTEXTO BRUTO (Shadow Logger) ---
        dump_intelligence_context(payload.message, intent_info, internal_context, org_id)

        # --- BYPASS: Retorno direto sem IA (tarefas, contatos, WhatsApp, Email) ---
        bypass_response = try_bypass_response(intent_info, internal_context, whatsapp_result_context, email_result_context)
        
        # --- COOLDOWN PIPEDRIVE ---
        from services.pipedrive.pipedrive_service import pipedrive_service
        pd_cooldown = pipedrive_service.get_retry_after_seconds()

        if bypass_response:
            if isinstance(bypass_response, dict):
                bypass_response["pipedrive_cooldown"] = pd_cooldown
            elif hasattr(bypass_response, "pipedrive_cooldown"):
                bypass_response.pipedrive_cooldown = pd_cooldown
            return bypass_response

        # --- ESTÁGIO 2: Geração da Resposta com IA ---
        if query_type == "agent_workflow":
            async def agent_streamer():
                try:
                    # ...
                    log_queue = asyncio.Queue()
                    from services.ai.agent_service import AgentService
                    from core.database import async_session
                    
                    async with async_session() as agent_session:
                        # Passa o histórico limpo para o agente
                        task = asyncio.create_task(AgentService.run_workflow(
                            goal=payload.message, 
                            initial_intent=intent_info,
                            org_id=org_id,
                            selected_entities=selected_entities_dicts,
                            session=agent_session,
                            log_queue=log_queue,
                            history=cleaned_history,
                            initial_raw_context=internal_context
                        ))
                        
                        # Enquanto a tarefa roda, emitimos logs
                        while not task.done() or not log_queue.empty():
                            try:
                                # Pequeno timeout para não travar
                                log_data = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                                
                                # Se log_data já for um dicionário (log rico), mesclamos o cooldown
                                if isinstance(log_data, dict):
                                    log_data["pipedrive_cooldown"] = pd_cooldown
                                    yield json.dumps(log_data) + "\n"
                                else:
                                    yield json.dumps({"type": "log", "content": log_data, "pipedrive_cooldown": pd_cooldown}) + "\n"
                            except asyncio.TimeoutError:
                                if task.done(): break
                                continue
                        
                        agent_result = await task
                        pending = agent_result.get("pending_approvals", [])
                        if pending:
                            yield json.dumps({"type": "pending_approvals", "actions": pending, "pipedrive_cooldown": pd_cooldown}) + "\n"
                    
                    # Formata a resposta final
                    full_response = agent_result.get("full_response", "Finalizado.")
                    
                    final_obj = {
                        "type": "final",
                        "response": full_response,
                        "ui_module": "AgentWorkflow",
                        "pipedrive_cooldown": pd_cooldown,
                        "data": {
                            "past_activities": agent_result.get("past_activities", []),
                            "new_activities": agent_result.get("new_activities", []),
                            "organization": agent_result.get("organization_data"),
                            "pending_approvals": pending
                        }
                    }
                    yield json.dumps(final_obj) + "\n"
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    yield json.dumps({"type": "log", "content": f"Erro crítico na orquestração: {str(e)}"}) + "\n"
                    yield json.dumps({"type": "final", "response": f"Desculpe, a orquestração falhou: {str(e)}", "pipedrive_cooldown": pd_cooldown}) + "\n"

            return StreamingResponse(agent_streamer(), media_type="application/x-ndjson")

        final_resp = await generate_ai_response(
            message=payload.message,
            intent_info=intent_info,
            internal_context=internal_context,
            history=payload.history,
            context_override=payload.context
        )
        
        # Injeta cooldown na resposta de IA normal
        if hasattr(final_resp, "pipedrive_cooldown"):
            final_resp.pipedrive_cooldown = pd_cooldown
        elif isinstance(final_resp, dict):
            final_resp["pipedrive_cooldown"] = pd_cooldown
            
        return final_resp

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_msg = traceback.format_exc()
        print(f"[AI Chat] Erro ao processar mensagem: {error_msg}")
        print(f"[AI Chat] Traceback:\n{traceback_msg}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {error_msg}")


@router.post("/agent-action")
async def handle_agent_action(
    payload: AgentActionRequest,
    session: AsyncSession = Depends(get_db)
):
    """
    Endpoint para aprovar ou rejeitar ações do agente que requerem permissão.
    Chamado pelo frontend quando o usuário clica em Aprovar ou Rejeitar.
    """
    from services.ai.agent_service import AgentService
    
    try:
        if payload.approved:
            result = await AgentService.execute_approved_action(payload.action_id, session)
        else:
            result = await AgentService.reject_action(payload.action_id)
        
        return result
    except Exception as e:
        print(f"[Agent Action] Erro: {e}")
        raise HTTPException(status_code=500, detail=str(e))
