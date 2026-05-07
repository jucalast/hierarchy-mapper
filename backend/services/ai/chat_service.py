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
from services.ai.llm.gemini_provider import GeminiDailyQuotaExhaustedError
from services.ai.llm.gemini_quota import get_quota_tracker

log = get_logger(__name__)


def _build_quota_exhausted_message(quota_summary: dict) -> str:
    """
    Monta uma mensagem amigável ao usuário quando a cota diária do Gemini é esgotada.
    Mostra o status de cada modelo e quando a cota renova.
    """
    from datetime import datetime, timezone, timedelta
    _PACIFIC_OFFSET = timedelta(hours=-7)
    now_pacific = datetime.now(timezone.utc) + _PACIFIC_OFFSET
    # Próxima meia-noite Pacific
    next_reset = (now_pacific + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    hours_left = round((next_reset - now_pacific).total_seconds() / 3600, 1)

    lines = ["⚠️ A cota diária do Gemini foi esgotada para todos os modelos disponíveis."]
    lines.append("")

    if quota_summary:
        lines.append("**Status dos modelos hoje:**")
        for model, info in quota_summary.items():
            bar_filled = round(info.get("pct", 0) / 10)
            bar = "█" * bar_filled + "░" * (10 - bar_filled)
            lines.append(f"• {model}: {info.get('used', 0)}/{info.get('limit', 0)} [{bar}] {info.get('pct', 0):.0f}%")

    lines.append("")
    lines.append(f"🔄 A cota renova automaticamente à meia-noite (horário do Pacífico) — em aproximadamente **{hours_left}h**.")
    lines.append("")
    lines.append("Você pode continuar usando Claude ou Groq enquanto isso, ou aguardar a renovação do Gemini.")
    return "\n".join(lines)


EMAIL_TRIGGERS = ("email para", "mandar email", "enviar email")

# Padrões que SEMPRE indicam consulta de status, nunca ação — roteados para deal_status
STATUS_QUERY_PATTERNS = (
    "como tá", "como ta ", "como está", "como esta ",
    "qual o andamento", "qual andamento",
    "me dê um status", "me de um status", "me da um status",
    "o que está acontecendo", "o que esta acontecendo",
    "tem novidade", "tem alguma novidade",
    "qual a situação", "qual a situacao",
    "me atualiza", "me atualize",
    "o que rolou", "o que aconteceu",
    "como anda", "como andou",
    "quais foram as últimas", "quais foram as ultimas",
    "me resume", "me explica o que",
    "o que foi feito", "o que aconteceu",
    "qual o status", "qual status",
    "tá rolando", "ta rolando",
)


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


def _patch_status_intent(message: str, intent_info: dict) -> dict:
    """
    Heurística de segurança: se o usuário perguntou (não comandou) sobre o negócio
    mas o classificador rotou para agent_workflow, corrige para deal_status.
    Isso evita que perguntas de status como 'como tá o andamento?' disparem ações.
    """
    # Só corrige se o LLM erroneamente classificou como agent_workflow
    if intent_info.get("query_type") != "agent_workflow":
        return intent_info

    msg_lower = message.lower().strip()

    # Verifica padrões de status query
    if any(pattern in msg_lower for pattern in STATUS_QUERY_PATTERNS):
        log.info("chat.intent.patch_status_query", original="agent_workflow")
        intent_info["query_type"] = "deal_status"

    return intent_info


# =============================================================================
# Suggested Actions Builder
# =============================================================================

def _build_suggested_actions(
    deals: list,
    activities: list,
    contacts: list,
    org_name: str,
    wa_results: list,
    email_results: list,
) -> list:
    """
    Gera lista de ações sugeridas com base no contexto do negócio.
    Geração mecânica — sem chamada LLM extra.
    Retorna até 5 ações no formato: [{label, prompt, icon}]
    """
    actions = []

    # 1. Tarefas pendentes → executar
    pending = [a for a in activities if not a.get("done")]
    for act in pending[:2]:
        subject = act.get("subject", "tarefa pendente")
        person = act.get("person_name", "")
        suffix = f" com {person}" if person else ""
        actions.append({
            "label": subject,
            "prompt": f"Execute '{subject}'{suffix} para a {org_name}",
            "icon": "task",
        })

    # 2. Sincronizar tarefas concluídas que possam estar desatualizadas no CRM
    done = [a for a in activities if a.get("done")]
    if done and pending:
        actions.append({
            "label": "Sincronizar Pipedrive",
            "prompt": f"Analise o histórico da {org_name} e atualize o Pipedrive marcando as tarefas que já foram concluídas",
            "icon": "sync",
        })

    # 3. WhatsApp disponível → enviar mensagem
    if wa_results:
        contact_wa = wa_results[0].get("contact", contacts[0].get("name", "") if contacts else "contato")
        actions.append({
            "label": f"WhatsApp para {contact_wa}",
            "prompt": f"Manda uma mensagem de WhatsApp para {contact_wa} da {org_name} fazendo um follow-up",
            "icon": "whatsapp",
        })

    # 4. E-mail disponível → enviar
    elif email_results:
        contact_em = email_results[0].get("contact", contacts[0].get("name", "") if contacts else "contato")
        actions.append({
            "label": f"E-mail para {contact_em}",
            "prompt": f"Envia um e-mail para {contact_em} da {org_name} fazendo um follow-up",
            "icon": "email",
        })

    # 5. Negócio aberto → avançar etapa
    for deal in deals[:1]:
        if deal.get("status") == "open":
            actions.append({
                "label": "Avançar etapa no pipeline",
                "prompt": f"Avance o negócio da {org_name} para a próxima etapa do pipeline no Pipedrive",
                "icon": "pipeline",
            })

    return actions[:5]


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
    async def _build_context_with_intent(
        payload: ChatMessage,
        intent_info: dict,
        cleaned_history: list,
        session: AsyncSession,
        log_queue=None,
    ) -> "_Pipeline":
        """
        Variante de _build_context que recebe intent_info e cleaned_history
        já computados — evita reclassificar intenção quando já sabemos o tipo.
        """
        from services.ai.action_executor import execute_email_action, execute_whatsapp_action
        from services.ai.data_fetcher import execute_osint_enrichment, fetch_contextual_data, resolve_organization

        query_type = intent_info.get("query_type", "general")

        whatsapp_result = None
        email_result = None
        if query_type == "whatsapp":
            whatsapp_result = await execute_whatsapp_action(intent_info, session)
        if query_type == "email":
            email_result = await execute_email_action(intent_info, session)

        org_id = await resolve_organization(
            payload.orgId,
            payload.selectedCompanies or [],
            intent_info.get("extracted_company_name"),
            payload.message,
            session,
        )

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

        log.info("chat.context.built", scopes=intent_info.get("data_scope", []), query_type=query_type)

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
            email_result = await execute_email_action(intent_info, session)

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

        # 🔄 Detecção de Regeneração (Limpeza do DB)
        # O frontend envia: history = [..., user_msg, assistant_msg]  (termina com assistant)
        # e payload.message == user_msg.content — indicando que o usuário quer regerar a resposta.
        is_regeneration = False
        if payload.thread_id and len(payload.history) >= 2:
            last_msg = payload.history[-1]
            prev_msg = payload.history[-2]
            if last_msg.role == "assistant" and prev_msg.role == "user":
                if prev_msg.content == payload.message:
                    from api.v1.endpoints.conversations import delete_last_assistant_message
                    await delete_last_assistant_message(session, payload.thread_id)
                    # Remove a última mensagem do assistente do histórico local
                    # (clean_history já retorna lista de dicts)
                    if cleaned_history and cleaned_history[-1].get("role") == "assistant":
                        cleaned_history = cleaned_history[:-1]
                    is_regeneration = True
                    log.info("chat.regeneration_detected", thread_id=payload.thread_id)

        # Registra o modelo preferido do usuário no contexto do request.
        # Todos os ask_llm chamados dentro desta Task asyncio usarão automaticamente
        # esse modelo como primeira opção (com fallback nos demais se necessário).
        from services.ai.llm.router import set_preferred_model, get_strict_mode_preference
        preferred_model_req = getattr(payload, "model", None)
        # Ativa strict mode se o usuário selecionou um modelo específico
        strict_mode = preferred_model_req is not None
        set_preferred_model(preferred_model_req, strict_mode=strict_mode)
        if preferred_model_req:
            log.info("chat.model_preference", preferred=preferred_model_req, strict_mode=strict_mode)

        # Estágio 1 — Classificação Rápida de Intenção
        intent_info = await classify_user_intent(payload.message, cleaned_history)
        intent_info = _patch_email_intent(payload.message, intent_info)
        intent_info = _patch_status_intent(payload.message, intent_info)  # evita agent_workflow em perguntas de status

        # Chip de ação sugerida → força execução sem passar pelo classificador
        # O contexto já foi buscado na query deal_status anterior; reutilizar via _internal_context
        if getattr(payload, "suggested_action", False):
            intent_info["query_type"] = "agent_workflow"
            intent_info.setdefault("data_scope", ["activities", "deals", "persons", "notes", "emails", "whatsapp"])
            log.info("chat.intent.forced_agent_workflow", reason="suggested_action_chip")

        query_type = intent_info.get("query_type", "general")
        log.info("chat.intent", query_type=query_type)

        from services.pipedrive.pipedrive_service import pipedrive_service
        cooldown = pipedrive_service.get_retry_after_seconds()

        # SE FOR AGENTE DE EXECUÇÃO: Retorna streaming IMEDIATAMENTE
        if query_type == "agent_workflow":
            from fastapi.responses import StreamingResponse
            return StreamingResponse(
                ChatOrchestrator._agent_streamer_fast(
                    payload, intent_info, cleaned_history, cooldown,
                    is_regeneration=is_regeneration,
                ),
                media_type="application/x-ndjson",
            )

        # SE FOR STATUS DO NEGÓCIO: streaming com pensamentos + briefing final (sem executar ações)
        if query_type == "deal_status":
            from fastapi.responses import StreamingResponse
            # IMPORTANTE: NÃO passa a session do Depends(get_db) para o gerador de streaming.
            # O FastAPI fecha essa sessão assim que o endpoint retorna, antes do stream terminar.
            # O streamer abre suas próprias sessões internamente via async_session().
            return StreamingResponse(
                ChatOrchestrator._deal_status_streamer_fast(
                    payload, intent_info, cleaned_history, None, cooldown,
                    preferred_model=getattr(payload, "model", None),
                    is_regeneration=is_regeneration,
                ),
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
    async def _agent_streamer_fast(
        payload: ChatMessage, intent_info: dict, cleaned_history: list, cooldown: int,
        is_regeneration: bool = False,
    ) -> AsyncIterator[str]:
        """Versão otimizada que faz o build do contexto DENTRO do stream para feedback imediato."""
        all_logs = []
        try:
            import uuid as _uuid
            from core.database import async_session
            from api.v1.endpoints.conversations import save_message, get_thread_cached_context
            from services.ai.agent_service import AgentService

            # Garante que a thread sempre tenha um ID — gerado automaticamente se o frontend
            # não enviar um. Isso permite que o contexto seja cacheado e reutilizado em
            # mensagens de follow-up dentro da mesma sessão.
            active_thread_id = payload.thread_id or str(_uuid.uuid4())

            log_queue: asyncio.Queue = asyncio.Queue()
            selected_entities_dicts = [
                c.dict() for c in (payload.selectedCompanies or [])
            ]

            async with async_session() as agent_session:
                # 1. Salvar mensagem do usuário (pula se for regeneração — mensagem já existe no DB)
                if not is_regeneration:
                    try:
                        await save_message(
                            session=agent_session,
                            thread_id=active_thread_id,
                            role="user",
                            content=payload.message
                        )
                    except Exception as e:
                        log.warning("chat.save_user_msg_failed", error=str(e))

                # 2. Buscar contexto cacheado da thread (evita re-busca de dados)
                cached_context = None
                if payload.orgId:
                    try:
                        cached_context = await get_thread_cached_context(
                            session=agent_session,
                            thread_id=active_thread_id,
                            org_id=payload.orgId,
                            max_age_minutes=30
                        )
                        if cached_context:
                            log.info("chat.using_cached_context", thread_id=active_thread_id)
                    except Exception as e:
                        log.warning("chat.cached_context_error", error=str(e))

                task = asyncio.create_task(
                    AgentService.run_workflow(
                        goal=payload.message,
                        initial_intent=intent_info,
                        org_id=payload.orgId,
                        selected_entities=selected_entities_dicts,
                        session=agent_session,
                        log_queue=log_queue,
                        history=cleaned_history,
                        initial_raw_context=cached_context,  # Usa cache se disponível
                        thread_id=active_thread_id,
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
                        all_logs.append(log_data)
                        yield json.dumps(log_data) + "\n"
                    else:
                        msg_log = {
                            "type": "log",
                            "content": log_data,
                            "pipedrive_cooldown": cooldown,
                        }
                        all_logs.append(msg_log)
                        yield json.dumps(msg_log) + "\n"

                agent_result = await task
                pending = agent_result.get("pending_approvals", []) if agent_result else []

                if pending:
                    yield json.dumps({
                        "type": "pending_approvals",
                        "actions": pending,
                        "pipedrive_cooldown": cooldown,
                    }) + "\n"

                full_response = (agent_result or {}).get("full_response", "Finalizado.")
                data_payload = {
                    "past_activities": (agent_result or {}).get("past_activities", []),
                    "new_activities": (agent_result or {}).get("new_activities", []),
                    "organization": (agent_result or {}).get("organization_data"),
                    "pending_approvals": pending,
                }
                
                final_obj = {
                    "type": "final",
                    "response": full_response,
                    "ui_module": "AgentWorkflow",
                    "pipedrive_cooldown": cooldown,
                    "data": data_payload,
                    # Retorna o thread_id para o frontend poder reutilizá-lo em mensagens
                    # de follow-up, ativando o cache de contexto de 30 minutos.
                    "thread_id": active_thread_id,
                }
                yield json.dumps(final_obj) + "\n"

                # 2. Salvar resposta do assistente (com logs, data e contexto para cache)
                internal_context = agent_result.get("_internal_context") if agent_result else None
                try:
                    await save_message(
                        session=agent_session,
                        thread_id=active_thread_id,
                        role="assistant",
                        content=full_response,
                        ui_module="AgentWorkflow",
                        data=data_payload,
                        logs=all_logs,
                        internal_context=internal_context
                    )
                except Exception as e:
                    log.warning("chat.save_assistant_msg_failed", error=str(e))

        except GeminiDailyQuotaExhaustedError as e:
            quota_summary = e.summary if hasattr(e, "summary") else {}
            log.warning("chat.agent_stream_error.gemini_quota_exhausted", summary=quota_summary)
            yield json.dumps({
                "type": "final",
                "response": _build_quota_exhausted_message(quota_summary),
                "ui_module": "GeminiQuotaExhausted",
                "data": {"quota_summary": quota_summary},
                "pipedrive_cooldown": cooldown,
            }) + "\n"

        except Exception as e:
            log.exception("chat.agent_stream_error", error=str(e))
            yield json.dumps({"type": "log", "content": f"Erro no Agente: {str(e)}"}) + "\n"
            yield json.dumps({
                "type": "final",
                "response": f"Desculpe, a orquestração falhou: {str(e)}",
                "pipedrive_cooldown": cooldown,
            }) + "\n"

    @staticmethod
    async def _deal_status_streamer_fast(
        payload: ChatMessage, intent_info: dict, cleaned_history: list,
        session: Optional[AsyncSession], cooldown: int, preferred_model: str = None,
        is_regeneration: bool = False,
    ):
        """
        Versão streaming REAL do deal_status — emite pensamentos DENTRO do processo de busca.
        Session pode ser None (quando chamado via StreamingResponse) — nesse caso abre a própria.
        """
        def emit(obj: dict) -> str:
            obj.setdefault("pipedrive_cooldown", cooldown)
            return json.dumps(obj) + "\n"

        try:
            import uuid as _uuid
            from core.database import async_session as _async_session_factory
            from api.v1.endpoints.conversations import save_message

            # Garante que a thread sempre tenha um ID
            active_thread_id = payload.thread_id or str(_uuid.uuid4())
            log_queue: asyncio.Queue = asyncio.Queue()
            all_logs = []

            # Quando session=None (StreamingResponse sem sessão da injeção de dependência),
            # criamos uma sessão própria que dura todo o ciclo de vida do stream.
            async with _async_session_factory() as owned_session:
                active_session = owned_session

                # 1. Salvar mensagem do usuário (pula se for regeneração)
                if not is_regeneration:
                    try:
                        await save_message(
                            session=active_session,
                            thread_id=active_thread_id,
                            role="user",
                            content=payload.message
                        )
                    except Exception as e:
                        log.warning("chat.save_user_msg_failed", error=str(e))

                # Rodamos o handler em uma task separada para poder consumir a log_queue simultaneamente
                task = asyncio.create_task(
                    ChatOrchestrator._deal_status_handler(
                        payload, intent_info, cleaned_history, active_session,
                        preferred_model=preferred_model,
                        log_queue=log_queue
                    )
                )

                # Consome a queue enquanto a task roda
                while not task.done() or not log_queue.empty():
                    try:
                        log_data = await asyncio.wait_for(log_queue.get(), timeout=0.1)
                        all_logs.append(log_data)
                        yield emit(log_data)
                    except asyncio.TimeoutError:
                        if task.done(): break
                        continue

                result = await task
                response_text = result.get("response", "")
                data = result.get("data", {})

                # Emite o resultado final
                suggested_actions = result.get("suggested_actions", [])
                yield emit({
                    "type": "final",
                    "response": response_text,
                    "ui_module": "DealStatus",
                    "data": {**data, "suggested_actions": suggested_actions},
                    "suggested_actions": suggested_actions,
                    "thread_id": active_thread_id,  # Retorna ID para o frontend
                })

                # 2. Salvar resposta do assistente (com logs e contexto)
                internal_context = result.get("_internal_context") if result else None
                try:
                    await save_message(
                        session=active_session,
                        thread_id=active_thread_id,
                        role="assistant",
                        content=response_text,
                        ui_module="DealStatus",
                        data={**data, "suggested_actions": suggested_actions},
                        logs=all_logs,
                        internal_context=internal_context
                    )
                except Exception as e:
                    log.warning("chat.save_assistant_msg_failed", error=str(e))

        except GeminiDailyQuotaExhaustedError as e:
            quota_summary = e.summary if hasattr(e, "summary") else {}
            log.warning("chat.deal_status_stream_error.gemini_quota_exhausted", summary=quota_summary)
            yield emit({
                "type": "final",
                "response": _build_quota_exhausted_message(quota_summary),
                "ui_module": "GeminiQuotaExhausted",
                "data": {"quota_summary": quota_summary},
            })

        except Exception as e:
            log.exception("chat.deal_status_stream_error", error=str(e))
            yield emit({"type": "log", "content": f"Erro ao carregar status: {e}"})
            yield emit({"type": "final", "response": f"Não consegui carregar o status: {e}"})

    @staticmethod
    async def _deal_status_handler(
        payload: ChatMessage, intent_info: dict, cleaned_history: list, session: AsyncSession,
        preferred_model: str = None, log_queue: Optional[asyncio.Queue] = None,
    ):
        """
        Modo leitura: coleta dados completos (deals, atividades, emails, WA) e gera um briefing.
        NÃO executa nenhuma ação — apenas informa o estado real do negócio.
        """
        from services.ai.agent_service import AgentService
        from services.ai.prompts import DEAL_STATUS_PROMPT
        from services.ai.llm import LLMTier, ask_llm

        # Força o data_scope completo para ter visão total
        intent_info["data_scope"] = ["activities", "deals", "persons", "notes", "emails", "whatsapp"]
        intent_info["activity_done_filter"] = None  # inclui concluídas e pendentes
        intent_info["activity_date_filter"] = "all"

        if log_queue:
            log_queue.put_nowait({"type": "status", "content": "Iniciando investigação do negócio...", "icon": "search"})

        # Busca os dados sem emitir os cards de data_found ainda (log_queue=None)
        # Mas mantemos o status de "Carregando" visível
        pipe = await ChatOrchestrator._build_context_with_intent(
            payload, intent_info, cleaned_history, session, log_queue=None
        )
        ctx = pipe.internal_context

        # ── OTIMIZAÇÃO DE LATÊNCIA ──────────────────────────────────────────────
        # Inicia a destilação de comunicações em background assim que temos o ctx.
        # Ela vai rodar em paralelo com a emissão dos cards narrativos (~10-15s ganhos).
        _distill_task = asyncio.create_task(
            AgentService._distill_communications(
                ctx.get("email_result", {}),
                ctx.get("whatsapp_result", {}),
                org_id=pipe.org_id,
            )
        )

        # narrative é compartilhado entre o bloco de pensamentos e o DEAL_STATUS_PROMPT
        # para evitar que a análise final repita o que os cards já mostram.
        _narrative_bridge: dict = {}   # frases de bridge geradas pelo NARRATIVE_PROMPT
        _already_shown: list  = []    # resumo do que os cards visuais exibiram

        if log_queue:
            deals = ctx.get("pipedrive_details", {}).get("deals", [])
            activities = ctx.get("pipedrive_details", {}).get("activities", [])
            notes = ctx.get("pipedrive_details", {}).get("notes", [])
            org_name = ctx.get("organization", {}).get("name", "Empresa")
            
            # 1. Gera o roteiro narrativo baseado nos fatos reais (Igual ao workflow)
            try:
                from services.ai.llm import LLMTier, ask_llm
                
                # Prepara dados para o prompt (incluindo estados e datas reais)
                deal_info_list = []
                for d in deals:
                    status_label = "Aberto" if d.get("status") == "open" else "Perdido" if d.get("status") == "lost" else "Ganho"
                    deal_info_list.append(f"{d.get('title')} ({d.get('formatted_value')}) - STATUS: {status_label}")
                deal_info = ", ".join(deal_info_list)

                act_subs = [f"{a.get('subject')} ({a.get('due_date')})" for a in activities[:15]]
                note_snippet = notes[0].get("content", "")[:150] if notes else "Sem notas"
                
                # Conta comunicações e pega a data da última
                email_threads = ctx.get("email_result", {}).get("resultado", {}).get("messages_by_contact", [])
                wa_threads = ctx.get("whatsapp_result", {}).get("resultado", {}).get("messages_by_contact", [])
                
                num_emails = sum(len(t.get("human_threads", [])) for t in email_threads)
                num_wa = sum(len(m.get("messages", [])) for m in wa_threads)
                
                # Busca data da última interação
                last_interaction = "Não identificada"
                all_msgs = []
                for t in email_threads: all_msgs.extend(t.get("human_threads", []))
                for t in wa_threads: all_msgs.extend(t.get("messages", []))
                if all_msgs:
                    # Tenta pegar a data mais recente (simplificado para o prompt)
                    last_interaction = "recente (ver detalhes nos cards)" 

                DEAL_STATUS_NARRATIVE_PROMPT = f"""Você é um assistente de vendas. Gere 3 frases curtas de transição para um briefing visual.
                Cada frase apresenta o bloco visual que vem logo a seguir — não analisa, só contextualiza.

                DADOS:
                - Negócios: {deal_info or 'Nenhum'}
                - Atividades: {", ".join(act_subs) or 'Nenhuma'}
                - Canal dominante: {"WhatsApp" if num_wa >= num_emails else "Email"} ({num_wa} msgs WA, {num_emails} threads email)

                REGRAS:
                1. "intro": 1 frase apresentando o deal e seu valor/fase. Ex: "R$ X em negociação com Y — fase Z."
                2. "tasks": 1 frase sobre o que o timeline vai mostrar. Ex: "Pipeline com N etapas, X concluídas e Y pendente para DD/MM."
                3. "analysis": 1 frase sobre as comunicações que serão exibidas. Ex: "N mensagens de WhatsApp registram toda a negociação."
                4. SOMENTE DATAS QUE ESTÃO NOS DADOS. Não invente.
                5. Máximo 15 palavras por frase.

                Retorne JSON:
                {{"intro": "...", "tasks": "...", "analysis": "..."}}"""
                
                script_res = await ask_llm(
                    DEAL_STATUS_NARRATIVE_PROMPT, json_mode=True, tier=LLMTier.STANDARD,
                    cacheable=False,
                )
                narrative = script_res.json_data or {}
                _narrative_bridge = narrative  # compartilha com DEAL_STATUS_PROMPT
                
                def _humanize_thought(content: Any) -> str:
                    """Converte objetos estruturados (fato/impl/val) em strings para o React."""
                    if not content: return ""
                    
                    # Se for uma lista de pensamentos, processa cada um e junta
                    if isinstance(content, list):
                        return " ".join([_humanize_thought(item) for item in content])
                        
                    if isinstance(content, str): return content
                    
                    if isinstance(content, dict):
                        f = content.get("fato") or content.get("fact")
                        i = content.get("implicacao") or content.get("implication") or content.get("implicacao_comercial")
                        v = content.get("validacao") or content.get("validation") or content.get("o_que_vamos_validar")
                        parts = []
                        if f: parts.append(str(f))
                        if i: parts.append(f"Isso sugere que {str(i).lower()}")
                        if v: parts.append(f"Vou focar em {str(v).lower()}")
                        return ". ".join(parts)
                    return str(content)

                def _get_thought(key_map: list) -> str:
                    for k in key_map:
                        val = narrative.get(k)
                        if val: return _humanize_thought(val)
                    return ""

                intro = _get_thought(["intro", "introducao", "contexto", "pipeline"])
                if intro:
                    log_queue.put_nowait({"type": "thought", "content": intro})
                    await asyncio.sleep(0.8)
                
                if deals:
                    # Registra o que os cards de deal vão mostrar
                    for d in deals:
                        _already_shown.append(
                            f"Card deal: {d.get('title')} | {d.get('formatted_value')} | Fase: {d.get('stage_name')} | Status: {d.get('status')}"
                        )
                    # Emite apenas a organização uma vez (evita duplicação)
                    org_emitted = False
                    for d in deals:
                        log_queue.put_nowait({"type": "data_found", "entity": "deal", "data": d})
                        if not org_emitted and d.get("org_id"):
                            # Inclui dados de funcionários e logo da organização do contexto
                            org_data = ctx.get("organization", {})
                            org_payload = {
                                "id": d.get("org_id"),
                                "name": d.get("org_name"),
                                "logo": org_data.get("logo_url") or org_data.get("logo") or org_data.get("organization_logo"),
                                "logo_url": org_data.get("logo_url") or org_data.get("logo"),
                                "employees_count": org_data.get("employees_count", 0),
                                "employees": org_data.get("employees", [])
                            }
                            log_queue.put_nowait({"type": "data_found", "entity": "organization", "data": org_payload})
                            org_emitted = True
                    await asyncio.sleep(0.5)

                tasks_thought = _get_thought(["tasks_analysis", "tasks", "tarefas", "atividades", "activities", "gargalo"])
                if tasks_thought:
                    log_queue.put_nowait({"type": "thought", "content": tasks_thought})
                    await asyncio.sleep(0.8)

                if activities:
                    # Registra o que o timeline vai mostrar
                    for a in activities:
                        status = "✅" if a.get("done") else "⏳"
                        _already_shown.append(f"Atividade card: {status} {a.get('subject')} ({a.get('due_date')})")
                    # Emite atividades como um grupo para renderizar com linhas de conexão
                    log_queue.put_nowait({"type": "data_found", "entity": "activities_group", "data": activities})
                    await asyncio.sleep(0.5)

                # Mostra contatos e comunicações
                log_queue.put_nowait({"type": "log", "content": "Cruzando histórico de comunicações..."})
                
                contacts = ctx.get("pipedrive_details", {}).get("persons", [])
                def _clean_p(p):
                    cp = p.copy()
                    for field in ["phone", "email"]:
                        val = cp.get(field)
                        if isinstance(val, list) and len(val) > 0:
                            cp[field] = val[0].get("value") if isinstance(val[0], dict) else val[0]
                    return cp

                for c in contacts:
                    log_queue.put_nowait({"type": "data_found", "entity": "contact", "data": _clean_p(c)})
                
                # Emite Threads de comunicação
                email_results = ctx.get("email_result", {}).get("resultado", {}).get("messages_by_contact", [])
                for er in email_results:
                    log_queue.put_nowait({"type": "data_found", "entity": "email", "data": er})
                if email_results:
                    _already_shown.append(f"Cards email: {len(email_results)} thread(s) exibida(s) com histórico completo")

                wa_results = ctx.get("whatsapp_result", {}).get("resultado", {}).get("messages_by_contact", [])
                for wr in wa_results:
                    # Formata os dados no formato esperado pelo frontend (whatsapp_result.resultado.messages)
                    formatted_wa = {
                        "whatsapp_result": {
                            "contact": {
                                "name": wr.get("contact"),
                                "phone": wr.get("phone")
                            },
                            "resultado": {
                                "messages": wr.get("messages", [])
                            }
                        }
                    }
                    log_queue.put_nowait({"type": "data_found", "entity": "whatsapp", "data": formatted_wa})
                if wa_results:
                    total_wa_msgs = sum(len(w.get("messages", [])) for w in wa_results)
                    _already_shown.append(f"Cards WhatsApp: {total_wa_msgs} mensagens exibidas com histórico completo")

                # ── DETECÇÃO DE LEAD FRIO ──
                has_comms = len(email_results) > 0 or len(wa_results) > 0
                if not has_comms:
                    log_queue.put_nowait({
                        "type": "suggest_mapping",
                        "org_name": org_name,
                        "message": f"Nenhum histórico de e-mail ou WhatsApp encontrado para {org_name}."
                    })

                await asyncio.sleep(0.5)

                final_insight = _get_thought(["analysis", "analise", "conclusao", "insight", "comunicacao", "strategy"])
                if final_insight:
                    log_queue.put_nowait({"type": "thought", "content": final_insight})
                    await asyncio.sleep(0.5)

                # Sugestões Proativas: cruza o diagnóstico narrativo com o planner
                # para detectar tarefas que deveriam existir no CRM mas ainda não existem.
                try:
                    from services.ai.agent_service import AgentService, PipelineContext
                    planner_contacts = {c.get("name"): {"email": c.get("email"), "phone": c.get("phone")} for c in contacts}

                    # Monta um PipelineContext mínimo com os dados disponíveis aqui.
                    # _precomputed_distilled pode já existir se o cache veio do run_workflow.
                    precomputed = ctx.get("_precomputed_distilled", "")
                    facts = [f for f in precomputed.split("\n") if f.strip()] if precomputed else []

                    sync_ctx = PipelineContext.from_raw(ctx)
                    sync_ctx.deal_state = final_insight or ""
                    if facts:
                        sync_ctx.distilled_facts = facts

                    plan_res = await AgentService._create_logical_plan(
                        goal=f"Sincronizar CRM para {org_name} com base no histórico",
                        ctx=sync_ctx,
                        contact_map=planner_contacts,
                        selected_entities=payload.selectedCompanies or [],
                        history=cleaned_history,
                    )

                    plan = plan_res.get("plan", []) if isinstance(plan_res, dict) else []
                    if plan:
                        sync_steps = [s for s in plan if s.get("action") in ["create_pipedrive_task", "update_pipedrive_task"]]
                        if sync_steps:
                            log.info("chat.proactive_sync", steps=len(sync_steps), org=org_name)
                            log_queue.put_nowait({
                                "type": "agent_workflow",
                                "content": "Sincronização Sugerida",
                                "data": {"plan": sync_steps}
                            })
                            await asyncio.sleep(0.3)
                except Exception as sync_err:
                    log.warning("chat.proactive_sync_failed", error=str(sync_err))

            except Exception as e:
                log.warning("chat.narrative_failed", error=str(e))
                log_queue.put_nowait({"type": "thought", "content": "Analisando histórico de comunicações..."})

        # Aguarda a destilação que foi iniciada em background (já deve estar quase pronta)
        try:
            distilled = await _distill_task
        except Exception:
            distilled = "Falha ao analisar comunicações."

        # Monta o contexto para o prompt de status
        pd = ctx.get("pipedrive_details", {}) or {}
        deals = pd.get("deals", [])
        activities = pd.get("activities", [])
        notes = pd.get("notes", [])
        org = ctx.get("organization", {}) or {}
        # NOTA: calculated_status (métrica de silêncio) removida intencionalmente.
        # Injetar "X dias de silêncio" causava alucinação de datas pelo modelo.

        lines = []
        lines.append(f"EMPRESA: {org.get('name', 'Desconhecida')}")

        if deals:
            lines.append("\nNEGÓCIOS ATIVOS:")
            for d in deals[:3]:
                lines.append(f"  - {d.get('title')} | {d.get('formatted_value')} | Fase: {d.get('stage_name')} | Status: {d.get('status')}")
        else:
            lines.append("\nNEGÓCIOS ATIVOS: Nenhum encontrado.")

        if activities:
            lines.append("\nATIVIDADES DO CRM (Últimas 10):")
            for a in activities[:10]:
                done = "✅ Concluída" if a.get("done") else "⏳ Pendente"
                person = a.get('person_name') or ''
                person_tag = f" [Contato: {person}]" if person else ""
                note_text = a.get('note') or ''
                note_tag = f" — Nota: {note_text[:60]}" if note_text else ""
                lines.append(f"  - {a.get('due_date', '?')}: {a.get('subject')} [{done}]{person_tag}{note_tag}")

        if notes:
            lines.append("\nÚLTIMAS NOTAS:")
            for n in notes[:2]:
                snippet = (n.get("content") or "")[:150].replace("\n", " ")
                lines.append(f"  - {snippet}")

        # Limita o histórico destilado para não explodir o contexto
        distilled_lean = distilled[:3000] + ("..." if len(distilled) > 3000 else "")
        lines.append(f"\nHISTÓRICO DE COMUNICAÇÕES (destilado):\n{distilled_lean}")

        context_block = "\n".join(lines)

        # Injeta contexto compartilhado: o que as frases de bridge e os cards já comunicaram.
        # O DEAL_STATUS_PROMPT usa isso para NÃO repetir — só acrescenta inteligência.
        already_shown_block = ""
        if _already_shown or _narrative_bridge:
            parts = []
            if _narrative_bridge:
                bridge_texts = [v for v in _narrative_bridge.values() if isinstance(v, str) and v]
                if bridge_texts:
                    parts.append("FRASES JÁ EXIBIDAS AO USUÁRIO:\n" + "\n".join(f"- {t}" for t in bridge_texts))
            if _already_shown:
                parts.append("CARDS VISUAIS JÁ EXIBIDOS (NÃO repita):\n" + "\n".join(f"- {s}" for s in _already_shown))
            if parts:
                already_shown_block = "\n\n" + "\n\n".join(parts) + "\n\nINSTRUÇÃO CRÍTICA: Tudo listado acima o usuário JÁ VIU nos cards visuais. Sua análise deve CRUZAR esses dados e extrair um insight que os cards sozinhos não mostram. Se sua frase poderia ser escrita sem ler os dados, ela está ruim."

        try:
            from datetime import date as _date
            from services.ai.llm.router import get_strict_mode_preference
            today_str = _date.today().strftime("%d/%m/%Y")
            # Usamos o tier DEEP para análise de status e respeitamos o strict_mode
            # Usamos o tier DEEP para análise de status e respeitamos o strict_mode
            # do usuário se ele tiver uma preferência específica.
            res = await ask_llm(
                DEAL_STATUS_PROMPT.format(context=context_block + already_shown_block, today=today_str),
                tier=LLMTier.DEEP,
                cacheable=False,
                preferred_model=preferred_model,
                strict_model=get_strict_mode_preference(),
                json_mode=True,
                cache_prefix=f"org:{pipe.org_id}" if pipe.org_id else None,
            )
            response_data = res.json_data if hasattr(res, "json_data") and res.json_data else {}
            if not response_data and hasattr(res, "json") and res.json:
                response_data = res.json
            if not response_data and res.text:
                import json as _json
                try:
                    response_data = _json.loads(res.text)
                except Exception:
                    response_data = {"analysis": res.text}
        except GeminiDailyQuotaExhaustedError as qe:
            quota_summary = await get_quota_tracker().get_summary()
            response_data = {"analysis": _build_quota_exhausted_message(quota_summary)}
        except Exception as e:
            response_data = {"analysis": f"Não consegui gerar o briefing neste momento ({e})."}

        combined_response = (
            response_data.get("analysis")
            or response_data.get("intro")
            or "Status processado."
        )

        # ── AÇÕES SUGERIDAS ──────────────────────────────────────────────────
        wa_results = ctx.get("whatsapp_result", {}).get("resultado", {}).get("messages_by_contact", [])
        email_results = ctx.get("email_result", {}).get("resultado", {}).get("messages_by_contact", [])
        contacts = ctx.get("pipedrive_details", {}).get("persons", []) or []
        suggested_actions = _build_suggested_actions(
            deals=deals,
            activities=activities,
            contacts=contacts,
            org_name=org_name,
            wa_results=wa_results,
            email_results=email_results,
        )

        return {
            **response_data,
            "response": combined_response,
            "query_type": "deal_status",
            "data": {
                "deals": deals,
                "activities": activities,
                "organization": org,
                "persons": ctx.get("pipedrive_details", {}).get("persons", []),
                "notes": notes,
            },
            "ui_module": "DealStatus",
            "suggested_actions": suggested_actions,
        }
