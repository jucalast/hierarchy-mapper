"""
services.ai.chat_service
========================

ChatOrchestrator — extrai do endpoint `/ai/chat` toda a lógica de pipeline.

Estágios:
1. Limpeza de histórico
2. Classificação de intenção
3. Heurísticas mecânicas (correção de email/whatsapp)
4. Execução de ações de side-effect (whatsapp/email/osint)
5. Resolução de organização-alvo
6. Coleta de contexto interno
7. Bypass de IA quando possível
8. Stage 2 — geração da resposta (modo agent ou direto)

O endpoint vira um thin router que apenas chama
`await ChatOrchestrator.handle(payload, session)`.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import get_logger
from services.ai.action_executor import execute_email_action, execute_whatsapp_action
from services.ai.bypass_handler import try_bypass_response
from services.ai.data_fetcher import (
    execute_osint_enrichment,
    fetch_contextual_data,
    resolve_organization,
)
from services.ai.helpers import ChatMessage
from services.ai.intent_classifier import classify_user_intent
from services.ai.logger import dump_intelligence_context
from services.ai.response_generator import generate_ai_response

log = get_logger(__name__)

EMAIL_TRIGGERS = ("email para", "mandar email", "enviar email")


# =============================================================================
# Helpers
# =============================================================================

def clean_history(history: list, max_msgs: int = 5, max_len: int = 1200) -> list:
    """Remove logs e dados pesados do histórico para economizar tokens."""
    if not history:
        return []
    cleaned: list[dict] = []
    for entry in history[-max_msgs:]:
        is_pydantic = hasattr(entry, "dict")
        h_dict = entry.dict() if is_pydantic else entry.copy()

        # Preserva um resumo dos dados para resolução de contexto (ex: "tarefa 4")
        if h_dict.get("role") == "assistant" and "data" in h_dict:
            data = h_dict["data"]
            if isinstance(data, list):
                # Mantém apenas o básico para o LLM "enxergar" o que foi mostrado
                h_dict["data_summary"] = [
                    f"{i+1}. {item.get('title') or item.get('subject') or item.get('name') or 'Item'}"
                    for i, item in enumerate(data[:15])
                ]
            elif isinstance(data, dict):
                h_dict["data_summary"] = data.get("title") or data.get("name") or str(data)[:100]
            
        h_dict.pop("data", None)
        h_dict.pop("logs", None)
        h_dict.pop("debug", None)

        content = h_dict.get("content", "")
        if content and len(content) > max_len:
            h_dict["content"] = content[:max_len] + "... [Conteúdo Truncado]"

        cleaned.append(h_dict)
    return cleaned


def _patch_email_intent(message: str, intent_info: dict) -> dict:
    """Heurística mecânica para garantir email_action e email_to."""
    msg_lower = message.lower()
    if any(t in msg_lower for t in EMAIL_TRIGGERS):
        if intent_info.get("query_type") != "email":
            log.info("chat.intent.patch_email")
            intent_info["query_type"] = "email"
            intent_info.setdefault("email_action", "send_email")

    if intent_info.get("query_type") == "email" and not intent_info.get("email_to"):
        emails = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", message)
        if emails:
            intent_info["email_to"] = emails[0]
            log.info("chat.intent.email_extracted")
    return intent_info


# =============================================================================
# Orchestrator
# =============================================================================

@dataclass
class _Pipeline:
    payload: ChatMessage
    session: AsyncSession
    cleaned_history: list
    intent_info: dict
    org_id: Optional[int]
    internal_context: dict
    whatsapp_result: Any
    email_result: Any


class ChatOrchestrator:
    """Encapsula o pipeline LLM em 2 estágios para o /ai/chat."""

    @staticmethod
    async def _build_context(
        payload: ChatMessage, session: AsyncSession
    ) -> _Pipeline:
        if not payload.message or not payload.message.strip():
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Mensagem vazia")

        cleaned_history = clean_history(payload.history or [])

        # Estágio 1 — intenção
        intent_info = await classify_user_intent(payload.message, cleaned_history)
        intent_info = _patch_email_intent(payload.message, intent_info)
        query_type = intent_info.get("query_type", "general")
        log.info("chat.intent", query_type=query_type)

        # Side-effects assíncronos podem rodar em paralelo onde fizer sentido
        whatsapp_result = None
        email_result = None
        if query_type == "whatsapp":
            whatsapp_result = await execute_whatsapp_action(intent_info, session)
        if query_type == "email":
            email_result = await execute_email_action(intent_info)

        # Resolução de organização
        org_id = await resolve_organization(
            payload.orgId,
            payload.selectedCompanies or [],
            intent_info.get("extracted_company_name"),
            payload.message,
            session,
        )

        # OSINT (enrichment)
        internal_context: Dict[str, Any] = {}
        if query_type == "enrichment":
            osint_context = await execute_osint_enrichment(intent_info, org_id, session)
            if osint_context:
                internal_context.update(osint_context)

        selected_entities_dicts = [c.dict() for c in (payload.selectedCompanies or [])]

        fetched = await fetch_contextual_data(
            intent_info,
            org_id,
            payload.message,
            session,
            selected_entities=selected_entities_dicts,
        )
        internal_context.update(fetched)
        internal_context["selected_entities"] = selected_entities_dicts
        if whatsapp_result:
            internal_context["whatsapp_result"] = whatsapp_result
        if email_result:
            internal_context["email_result"] = email_result

        log.info(
            "chat.context.built",
            scopes=intent_info.get("data_scope", []),
            query_type=query_type,
        )

        # Shadow logger
        try:
            dump_intelligence_context(
                payload.message, intent_info, internal_context, org_id
            )
        except Exception as e:
            log.warning("chat.shadow_log_failed", error=str(e))

        return _Pipeline(
            payload=payload,
            session=session,
            cleaned_history=cleaned_history,
            intent_info=intent_info,
            org_id=org_id,
            internal_context=internal_context,
            whatsapp_result=whatsapp_result,
            email_result=email_result,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _inject_cooldown(resp, cooldown: int):
        if resp is None:
            return resp
        if isinstance(resp, dict):
            resp["pipedrive_cooldown"] = cooldown
        elif hasattr(resp, "pipedrive_cooldown"):
            resp.pipedrive_cooldown = cooldown
        return resp

    # ------------------------------------------------------------------
    @staticmethod
    async def handle(payload: ChatMessage, session: AsyncSession):
        """Entrada principal — retorna ChatResponse | dict | StreamingResponse."""
        if not payload.message or not payload.message.strip():
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Mensagem vazia")

        cleaned_history = clean_history(payload.history or [])

        # Estágio 1 — Classificação Rápida de Intenção
        intent_info = await classify_user_intent(payload.message, cleaned_history)
        intent_info = _patch_email_intent(payload.message, intent_info)
        query_type = intent_info.get("query_type", "general")
        log.info("chat.intent", query_type=query_type)

        from services.pipedrive.pipedrive_service import pipedrive_service
        cooldown = pipedrive_service.get_retry_after_seconds()

        # SE FOR AGENTE: Retorna streaming IMEDIATAMENTE
        if query_type == "agent_workflow":
            from fastapi.responses import StreamingResponse
            return StreamingResponse(
                ChatOrchestrator._agent_streamer_fast(payload, intent_info, cleaned_history, cooldown),
                media_type="application/x-ndjson",
            )

        # Para outros tipos, segue o fluxo normal de build_context
        pipe = await ChatOrchestrator._build_context_with_intent(payload, intent_info, cleaned_history, session)

        # Bypass tenta responder sem chamar LLM
        bypass = try_bypass_response(
            pipe.intent_info,
            pipe.internal_context,
            pipe.whatsapp_result,
            pipe.email_result,
        )

        if bypass is not None:
            return ChatOrchestrator._inject_cooldown(bypass, cooldown)

        # Geração padrão
        final_resp = await generate_ai_response(
            message=pipe.payload.message,
            intent_info=pipe.intent_info,
            internal_context=pipe.internal_context,
            history=pipe.payload.history,
            context_override=pipe.payload.context,
        )
        return ChatOrchestrator._inject_cooldown(final_resp, cooldown)

    @staticmethod
    async def _agent_streamer_fast(payload: ChatMessage, intent_info: dict, cleaned_history: list, cooldown: int) -> AsyncIterator[str]:
        """Versão otimizada que faz o build do contexto DENTRO do stream para feedback imediato."""
        try:
            from core.database import async_session
            from services.ai.agent_service import AgentService

            log_queue: asyncio.Queue = asyncio.Queue()
            selected_entities_dicts = [
                c.dict() for c in (payload.selectedCompanies or [])
            ]

            async with async_session() as agent_session:
                task = asyncio.create_task(
                    AgentService.run_workflow(
                        goal=payload.message,
                        initial_intent=intent_info,
                        org_id=payload.orgId,
                        selected_entities=selected_entities_dicts,
                        session=agent_session,
                        log_queue=log_queue,
                        history=cleaned_history,
                        initial_raw_context=None, # Força busca interna com logs
                    )
                )

                while not task.done() or not log_queue.empty():
                    try:
                        log_data = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        if task.done(): break
                        continue

                    if isinstance(log_data, dict):
                        log_data["pipedrive_cooldown"] = cooldown
                        yield json.dumps(log_data) + "\n"
                    else:
                        yield json.dumps({
                            "type": "log",
                            "content": log_data,
                            "pipedrive_cooldown": cooldown,
                        }) + "\n"

                agent_result = await task
                pending = agent_result.get("pending_approvals", []) if agent_result else []

                if pending:
                    yield json.dumps({
                        "type": "pending_approvals",
                        "actions": pending,
                        "pipedrive_cooldown": cooldown,
                    }) + "\n"

            full_response = (agent_result or {}).get("full_response", "Finalizado.")
            final_obj = {
                "type": "final",
                "response": full_response,
                "ui_module": "AgentWorkflow",
                "pipedrive_cooldown": cooldown,
                "data": {
                    "past_activities": (agent_result or {}).get("past_activities", []),
                    "new_activities": (agent_result or {}).get("new_activities", []),
                    "organization": (agent_result or {}).get("organization_data"),
                    "pending_approvals": pending,
                },
            }
            yield json.dumps(final_obj) + "\n"

        except Exception as e:
            log.exception("chat.agent_stream_error", error=str(e))
            yield json.dumps({"type": "log", "content": f"Erro no Agente: {str(e)}"}) + "\n"
            yield json.dumps({
                "type": "final",
                "response": f"Desculpe, a orquestração falhou: {str(e)}",
                "pipedrive_cooldown": cooldown,
            }) + "\n"

    @staticmethod
    async def _build_context_with_intent(
        payload: ChatMessage, intent_info: dict, cleaned_history: list, session: AsyncSession
    ) -> _Pipeline:
        """Versão refatorada que aceita a intenção já classificada."""
        query_type = intent_info.get("query_type", "general")
        
        # Side-effects
        whatsapp_result = None
        email_result = None
        if query_type == "whatsapp":
            whatsapp_result = await execute_whatsapp_action(intent_info, session)
        if query_type == "email":
            email_result = await execute_email_action(intent_info)

        # Resolução de organização
        org_id = await resolve_organization(
            payload.orgId,
            payload.selectedCompanies or [],
            intent_info.get("extracted_company_name"),
            payload.message,
            session,
        )

        # Contexto
        internal_context: Dict[str, Any] = {}
        if query_type == "enrichment":
            osint_context = await execute_osint_enrichment(intent_info, org_id, session)
            internal_context.update(osint_context)

        internal_context.update(
            await fetch_contextual_data(
                intent_info,
                org_id,
                payload.message,
                session,
                selected_entities=[c.dict() for c in (payload.selectedCompanies or [])],
            )
        )

        if whatsapp_result:
            internal_context["whatsapp_result"] = whatsapp_result
        if email_result:
            internal_context["email_result"] = email_result

        try:
            dump_intelligence_context(payload.message, intent_info, internal_context, org_id)
        except Exception as e:
            log.warning("chat.shadow_log_failed", error=str(e))

        return _Pipeline(
            payload=payload,
            session=session,
            cleaned_history=cleaned_history,
            intent_info=intent_info,
            org_id=org_id,
            internal_context=internal_context,
            whatsapp_result=whatsapp_result,
            email_result=email_result,
        )


__all__ = ["ChatOrchestrator", "clean_history"]
