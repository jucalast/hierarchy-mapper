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

router = APIRouter()


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

        # --- ESTÁGIO 1: Classificação de Intenção (Pipeline Routing) ---
        print(f"[AI Pipeline] Estágio 1 - Analisando intenção do usuário com histórico de {len(payload.history or [])} mensagens...")
        intent_info = await classify_user_intent(payload.message, payload.history)
        
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

        # --- BUSCA DE DADOS CONTEXTUAIS ---
        fetched_data = await fetch_contextual_data(intent_info, org_id, payload.message, session)
        internal_context.update(fetched_data)

        # Injeta resultados de ações no contexto
        if whatsapp_result_context:
            internal_context["whatsapp_result"] = whatsapp_result_context
        if email_result_context:
            internal_context["email_result"] = email_result_context

        data_scope = intent_info.get("data_scope", [])
        print(f"[AI Pipeline] Estágio 2 - Alimentando o modelo final com dados da query do tipo: {query_type} | scopes: {data_scope}...")

        # --- BYPASS: Retorno direto sem IA (tarefas, contatos, WhatsApp, Email) ---
        bypass_response = try_bypass_response(intent_info, internal_context, whatsapp_result_context, email_result_context)
        if bypass_response:
            return bypass_response

        # --- ESTÁGIO 2: Geração da Resposta com IA ---
        if query_type == "agent_workflow":
            async def agent_streamer():
                try:
                    # Executa o workflow em background para podermos capturar os logs
                    log_queue = asyncio.Queue()
                    from services.ai.agent_service import AgentService
                    task = asyncio.create_task(AgentService.run_workflow(
                        goal=payload.message, 
                        initial_intent=intent_info,
                        org_id=org_id,
                        selected_entities=payload.selectedCompanies or [],
                        session=session,
                        log_queue=log_queue
                    ))
                    
                    # Enquanto a tarefa roda, emitimos logs
                    while not task.done() or not log_queue.empty():
                        try:
                            # Pequeno timeout para não travar
                            log_msg = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                            yield json.dumps({"type": "log", "content": log_msg}) + "\n"
                        except asyncio.TimeoutError:
                            if task.done(): break
                            continue
                    
                    agent_result = await task
                    
                    # Emite aprovações pendentes (se houver)
                    pending = agent_result.get("pending_approvals", [])
                    if pending:
                        yield json.dumps({"type": "pending_approvals", "actions": pending}) + "\n"
                    
                    # Formata a resposta final
                    full_response = agent_result.get("full_response", "Finalizado.")
                    
                    final_obj = {
                        "type": "final",
                        "response": full_response,
                        "ui_module": "AgentWorkflow",
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
                    yield json.dumps({"type": "final", "response": f"Desculpe, a orquestração falhou: {str(e)}"}) + "\n"

            return StreamingResponse(agent_streamer(), media_type="application/x-ndjson")

        return await generate_ai_response(
            message=payload.message,
            intent_info=intent_info,
            internal_context=internal_context,
            history=payload.history,
            context_override=payload.context
        )
        
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
