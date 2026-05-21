"""
Runner do Agente: pontos de entrada públicos.

  run_agent()                 — gerador assíncrono, emite NDJSON
  resume_after_confirmation() — retoma após aprovação de ação de escrita
"""
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List

from modules.agent.service.helpers import _emit, _raw_log, _fix_corrupted_name
from modules.agent.service.sanitizers import _sanitize_result
from modules.agent.service.tools import TOOLS, execute_write_tool, get_tools_anthropic_schema
from modules.agent.service.prompts import (
    SYSTEM_PROMPT_POWERFUL, SYSTEM_PROMPT_BASIC, SYSTEM_PROMPT_DIRECT,
    SYSTEM_PROMPT_TASK_AGENT, SYSTEM_PROMPT_TASK_AGENT_BASIC,
)
from modules.agent.service.core.loop import _agent_loop, _PENDING
from core.observability.logging_config import get_logger

log = get_logger(__name__)

MAX_ITERATIONS = 20

async def run_agent(
    message: str,
    history: List[Dict],
    org_id: int | None = None,
    preferred: str | None = None,
    strict_mode: bool = False,
    thread_id: str | None = None,
    direct_action: bool = False,
    parent_message_id: str | None = None,
    action_index: int | None = None,
    is_regeneration: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Gerador assíncrono — yields strings NDJSON.
    Usa native tool calling da API Anthropic.
    """
    tools = get_tools_anthropic_schema()
    if direct_action:
        # Filtra ferramentas para as mencionadas na mensagem + ferramentas de decisão sempre presentes.
        # "Ferramentas de decisão" são as que o agente pode precisar independente do prompt antigo:
        # - generate_call_script: para quando encontra telefone
        # - open_hierarchy_drawer: para quando não tem contato
        # - pipedrive_create_task: para criar tarefa de rastreamento
        # Para tarefas de follow-up/cobrar retorno, generate_call_script é irrelevante
        _msg_lower = message.lower()
        _is_followup_task = any(kw in _msg_lower for kw in [
            "cobrar retorno", "follow-up", "follow up", "followup",
            "acompanhar", "cobrar informações", "aguardar retorno",
        ])
        _ALWAYS_AVAILABLE_IN_TASK = {
            "open_hierarchy_drawer", "pipedrive_create_task",
            # generate_call_script só disponível se NÃO for follow-up
            *( set() if _is_followup_task else {"generate_call_script"} ),
        }
        from modules.agent.service.tools import TOOLS
        matched_tools = [name for name in TOOLS.keys() if name in message]
        if matched_tools:
            allowed = set(matched_tools) | _ALWAYS_AVAILABLE_IN_TASK
            if _is_followup_task:
                allowed.discard("generate_call_script")
            tools = [t for t in tools if t["name"] in allowed]
            log.info("agent.direct_action.tools_filtered", matched=list(allowed), is_followup=_is_followup_task)
        elif _is_followup_task:
            tools = [t for t in tools if t["name"] != "generate_call_script"]
            log.info("agent.direct_action.followup_call_script_removed")

    # Resolve o nome real da org no Pipedrive quando org_id é fornecido
    # Evita que o modelo use nomes errados/variantes (ex: "GmbH" vs "Gmb H")
    org_context = ""
    if org_id:
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            orgs = await pipedrive_service.list_organizations()
            org = next((o for o in (orgs or []) if o.get("id") == org_id), None)
            if org:
                org_context = (
                    f"\n[OBRIGATÓRIO - ESCOPO EXCLUSIVO DA EMPRESA]: Você está no chat dedicado da empresa '{org['name']}' (org_id={org_id}). "
                    f"Todas as suas respostas, investigações, buscas e ações de ferramentas devem ser direcionadas "
                    f"ESTRITAMENTE a esta empresa e seus contatos associados. Não cite, não investigue e não execute tarefas de outras empresas "
                    f"ou contatos fora deste escopo."
                )
        except Exception:
            pass
    else:
        # Chat geral — busca por menções de "@"
        import re
        mentions = re.findall(r'@([A-Za-z0-9\sà-úÀ-Ú\-]+)', message)
        if mentions:
            mention_contexts = []
            from modules.crm.service.pipedrive_service import pipedrive_service
            for m in mentions:
                term = m.strip()
                if len(term) >= 2:
                    try:
                        # 1. Tenta buscar organização por nome
                        matched_orgs = await pipedrive_service.search_organization(term)
                        if matched_orgs:
                            first_org = matched_orgs[0]
                            org_id_val = first_org.get("id")
                            org_name_val = first_org.get("name")
                            if org_id_val:
                                mention_contexts.append(
                                    f"• Marcação '@{term}': Refere-se à empresa '{org_name_val}' (org_id={org_id_val})."
                                )
                                # Define dinamicamente o org_id se não estiver setado
                                if not org_id:
                                    org_id = int(org_id_val)
                        else:
                            # 2. Tenta buscar pessoa por nome
                            resp = await pipedrive_service._request("GET", "persons/search", params={"term": term, "limit": 5})
                            if resp and resp.status_code == 200:
                                p_data = resp.json()
                                if p_data.get("success"):
                                    items = p_data.get("data", {}).get("items") or []
                                    if items:
                                        person_item = items[0].get("item")
                                        if person_item:
                                            p_name = person_item.get("name")
                                            org_info = person_item.get("organization") or {}
                                            org_name_val = org_info.get("name") or "Sem empresa vinculada"
                                            org_id_val = org_info.get("id")
                                            
                                            context_str = f"• Marcação '@{term}': Refere-se ao contato '{p_name}' da empresa '{org_name_val}'"
                                            if org_id_val:
                                                context_str += f" (org_id={org_id_val})."
                                                if not org_id:
                                                    org_id = int(org_id_val)
                                            else:
                                                context_str += "."
                                            mention_contexts.append(context_str)
                    except Exception:
                        pass
            if mention_contexts:
                org_context = (
                    f"\n[OBRIGATÓRIO - MARCAÇÕES DETECTADAS]: O usuário usou @ para marcar itens específicos:\n"
                    + "\n".join(mention_contexts)
                    + "\nFoque sua resposta, buscas de ferramentas e investigações exclusivamente nestes itens marcados."
                )
        else:
            # Sem menção e sem empresa selecionada -> escopo geral global
            org_context = (
                "\n[INSTRUÇÃO DE ESCOPO GERAL]: Nenhuma empresa específica foi selecionada e nenhuma marcação '@' foi detectada. "
                "Fale sobre TODAS as empresas cadastradas no CRM de forma ampla e global, trazendo um panorama geral, insights amplos e comparativos "
                "das atividades de todas as empresas disponíveis, sem se limitar a uma específica."
            )

    # Constrói o histórico de conversa
    messages: list = []
    for m in history[-15:]:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})

    # Mensagem atual com contexto de nome correto
    user_content = message + org_context

    # Detecta micro-ação sobre contexto já investigado e injeta diretiva de não-reinvestigação
    _context_followup_active = False
    if not direct_action:
        _ctx_directive = _detect_context_followup(message, history)
        if _ctx_directive:
            user_content += _ctx_directive
            _context_followup_active = True
            log.info("agent.context_followup_mode_active", message_preview=message[:80])

    messages.append({"role": "user", "content": user_content})

    process_id = f"proc_{uuid.uuid4().hex[:8]}"
    _raw_log(process_id, "agent_start", {"message": message, "org_id": org_id, "preferred": preferred})

    # Classifica a intenção para guiar o loop do agente de forma inteligente
    from modules.ai.service.intent.intent_classifier import classify_user_intent
    try:
        intent_info = await classify_user_intent(message, history)
        query_type = intent_info.get("query_type", "general")
    except Exception as e:
        log.warning("agent.intent_classification_failed", error=str(e))
        query_type = "agent_workflow"

    # Quando MODO CONTEXTO está ativo, força query_type="general" para usar prompt leve
    # e remover o requisito de pipeline de investigação completa antes de write tools.
    if _context_followup_active:
        query_type = "general"
        log.info("agent.context_followup.query_type_override")

    final_response = ""
    collected_events = []
    async for chunk in _agent_loop(
        messages,
        tools,
        org_id=org_id,
        preferred=preferred,
        strict_mode=strict_mode,
        process_id=process_id,
        direct_action=direct_action,
        parent_message_id=parent_message_id,
        action_index=action_index,
        query_type=query_type,
    ):
        # Rastreia a resposta final antes de emitir
        try:
            data = _json.loads(chunk)
            collected_events.append(data)
            if data.get("type") == "final":
                final_response = data.get("response", "")
        except Exception:
            pass
        yield chunk

    # Persiste as mensagens no banco após o stream completo
    if thread_id:
        try:
            from core.infra.database import async_session as _async_session
            async with _async_session() as db:
                if parent_message_id and action_index is not None:
                    # ─── Suggested action saving logic ───
                    # Carrega a mensagem do assistente pai e atualiza os eventos dela com os resultados dessa execução
                    from sqlalchemy import select
                    from models.conversation import ConversationMessage
                    result = await db.execute(
                        select(ConversationMessage).where(ConversationMessage.id == parent_message_id)
                    )
                    parent_msg = result.scalar_one_or_none()
                    if parent_msg:
                        has_confirm = any(e.get("type") == "confirmation_required" for e in collected_events)
                        action_status = "awaiting_confirm" if has_confirm else "done"

                        # Vamos salvar os logs desta execução e o status no data da mensagem do assistente pai.
                        msg_data = dict(parent_msg.data or {})
                        runs = msg_data.get("suggested_actions_runs", {})
                        runs[str(action_index)] = {
                            "status": action_status,
                            "logs": collected_events,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        msg_data["suggested_actions_runs"] = runs
                        parent_msg.data = msg_data
                        
                        # Também precisamos atualizar o log/evento "suggested_actions" original em parent_msg.logs para refletir que ela foi executada
                        parent_logs = list(parent_msg.logs or [])
                        for event in parent_logs:
                            if event.get("type") == "suggested_actions" and "actions" in event:
                                # Adiciona o status/logs na ação correspondente
                                if 0 <= action_index < len(event["actions"]):
                                    action_item = event["actions"][action_index]
                                    action_item["status"] = action_status
                                    action_item["logs"] = collected_events
                        parent_msg.logs = parent_logs
                        
                        db.add(parent_msg)
                        await db.commit()
                        log.info("agent.suggested_action.saved_to_parent", parent_message_id=parent_message_id, action_index=action_index)
                else:
                    # Comportamento padrão de salvar como mensagens separadas se não for uma ação sugerida atrelada ao pai
                    from api.v1.routers.conversations import save_message as _save_message
                    if not is_regeneration:
                        await _save_message(db, thread_id, "user", message)
                    
                    # Salva a resposta do assistente se houve resposta final OU se houve eventos (investigação iniciada/parada em confirmação)
                    if final_response or collected_events:
                        await _save_message(
                            db, 
                            thread_id, 
                            "assistant", 
                            final_response or "", 
                            logs=collected_events
                        )
                    log.info("agent.messages.saved", thread_id=thread_id, is_regeneration=is_regeneration, has_final=bool(final_response))
        except Exception as e:
            log.warning("agent.messages.save_failed", thread_id=thread_id, error=str(e))


def _extract_first_activity_id(messages_snapshot: list) -> str | None:
    """Extrai o ID da primeira atividade de pipedrive_get_activities no snapshot."""
    import re as _re

    # Passo 1: encontra tool_use_ids para pipedrive_get_activities
    activity_tool_ids: set[str] = set()
    for m in messages_snapshot:
        content = m.get("content", "")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use" and block.get("name") == "pipedrive_get_activities":
                tid = block.get("id", "")
                if tid:
                    activity_tool_ids.add(tid)

    if not activity_tool_ids:
        return None

    # Passo 2: encontra os tool_results correspondentes e extrai o primeiro ID
    for m in messages_snapshot:
        content = m.get("content", "")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") != "tool_result":
                continue
            if block.get("tool_use_id") not in activity_tool_ids:
                continue
            tc = block.get("content", "")
            if isinstance(tc, list):
                tc = " ".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in tc)
            ids = _re.findall(r'"id"\s*:\s*(\d+)', str(tc))
            if ids:
                return ids[0]

    return None


_FOLLOWUP_ACTION_KEYWORDS = [
    "marque", "marcar", "concluir", "concluído", "concluida", "atualiz",
    "próximas ações", "proximas acoes", "sugerir", "sugira",
    "feito", "pronto", "faz isso", "faltou", "não chamou",
    "falta chamar", "também faz", "agora faz", "agora marqu",
    "agora atuali", "agora conclui", "agora suger", "agora cri",
    # Pedidos de criação de tarefas / próximos passos com base no contexto
    "com base no contexto", "com base nisso", "com base no que",
    "sugira tarefas", "crie tarefas", "criar tarefas", "novas tarefas",
    "próximos passos", "proximos passos", "marcar uma reunião", "agendar reunião",
    "o que fazer", "o que devo fazer", "qual o próximo passo",
]

_INVESTIGATION_DONE_MARKERS = [
    "pipedrive_get_activities", "pipedrive_get_org", "pipedrive_get_persons",
    "whatsapp_get_messages", "generate_sales_message",
    "atividades pendentes", "mensagens com", "contatos em", "deal(s) em",
]


def _detect_context_followup(message: str, history: list) -> str | None:
    """
    Detecta micro-ação sobre investigação já concluída no histórico.
    Retorna diretiva [MODO CONTEXTO] para injetar no prompt, ou None.
    """
    import re as _re

    msg_lower = message.lower().strip()
    is_micro_action = (
        len(message.strip()) < 250
        and any(kw in msg_lower for kw in _FOLLOWUP_ACTION_KEYWORDS)
    )
    if not is_micro_action:
        return None

    history_text = " ".join(str(m.get("content", "")) for m in history[-15:])
    markers_found = sum(1 for mk in _INVESTIGATION_DONE_MARKERS if mk in history_text)
    if markers_found < 2:
        return None

    # Extrai IDs de atividade do histórico para incluir na diretiva
    id_patterns = [
        r'activity_id["\s:]+(\d{4,8})',
        r'atividade\s*#?(\d{4,8})',
        r'ATIVIDADE\s*#?(\d{4,8})',
    ]
    ids: set[str] = set()
    for pat in id_patterns:
        ids.update(_re.findall(pat, history_text, _re.IGNORECASE))

    directive = (
        "\n\n[MODO CONTEXTO — LEIA ANTES DE AGIR]: A investigação desta empresa já foi "
        "concluída nesta conversa. NÃO reinicie a investigação. É PROIBIDO chamar "
        "pipedrive_get_org, pipedrive_get_persons, pipedrive_get_deals, "
        "pipedrive_get_activities, whatsapp_get_messages ou email_get_contact_history — "
        "todos esses dados já estão no histórico acima. Use o contexto coletado e execute "
        "APENAS o que o usuário está pedindo agora. "
        "Se precisar escrever uma nota em pipedrive_update_task, redija com base no "
        "contexto de WhatsApp/Email que já aparece no histórico desta conversa — "
        "não chame ferramentas de busca para isso."
    )
    if ids:
        directive += f" IDs de atividade disponíveis no histórico: {', '.join(list(ids)[:3])}."

    return directive


async def resume_after_confirmation(
    action_id: str,
    approved: bool,
    thread_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Retoma o agente após confirmação de uma ação de escrita."""
    pending = _PENDING.pop(action_id, None)
    if not pending:
        yield _emit({"type": "error", "content": "Ação não encontrada ou expirada"})
        return

    tool_name = pending["tool"]
    tool_args = pending["args"]
    tool_use_id = pending["tool_use_id"]
    call_id = pending["call_id"]
    label = pending.get("label", tool_name)
    parent_message_id = pending.get("parent_message_id")
    action_index = pending.get("action_index")

    # Emite o tool call que estava pendente
    yield _emit({"type": "tool_call", "call_id": call_id, "tool": tool_name, "args": tool_args, "label": label})

    pending_org_id = pending.get("org_id")
    pending_process_id = pending.get("process_id", f"proc_res_{uuid.uuid4().hex[:8]}")

    if approved:
        try:
            _raw_log(pending_process_id, "tool_execute_write_start", {"tool": tool_name, "args": tool_args})
            result = await execute_write_tool(tool_name, tool_args, org_id=pending_org_id)
            _raw_log(pending_process_id, "tool_execute_write_result", {"tool": tool_name, "result_raw": result})
        except Exception as e:
            result = {"ok": False, "error": str(e)}
    else:
        result = {"ok": False, "error": "Ação cancelada pelo usuário"}

    ok = result.get("ok", False)
    summary = result.get("result") or result.get("error") or ("OK" if ok else "Erro")

    yield _emit({"type": "tool_result", "call_id": call_id, "tool": tool_name, "summary": summary, "ok": ok})

    # Monta a lista completa de tool results (reads anteriores + write confirmado)
    write_result = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "tool_name": tool_name,
        "content": json.dumps(result, ensure_ascii=False),
    }
    all_results = pending["prior_results"] + [write_result]

    # Restaura conversa e adiciona os resultados
    messages = pending["messages_snapshot"]  # Já inclui a mensagem do assistente com tool_use blocks
    
    # Se aprovado, adicionamos um nudge para o agente continuar o fluxo
    system_nudge = ""
    if approved:
        if tool_name in ("whatsapp_send_message", "email_send", "email_reply"):
            sent_msg_preview = pending.get("args", {}).get(
                "message" if tool_name == "whatsapp_send_message" else "body", ""
            )
            channel_label = "WhatsApp" if tool_name == "whatsapp_send_message" else "Email"

            # Extrai o ID real da atividade do snapshot para não deixar o agente adivinhar
            activity_id_val = _extract_first_activity_id(pending.get("messages_snapshot", []))
            activity_id_str = (
                str(activity_id_val)
                if activity_id_val
                else "use o ID encontrado em pipedrive_get_activities no histórico acima"
            )

            msg_short = sent_msg_preview[:120].replace('"', "'")

            system_nudge = (
                f"\n\n[SISTEMA]: {channel_label} enviado com sucesso.\n"
                f"MENSAGEM ENVIADA: \"{msg_short}...\"\n\n"
                f"OBRIGATÓRIO — execute estas 2 ferramentas AGORA, nesta ordem:\n\n"
                f"1. pipedrive_update_task\n"
                f"   activity_id: {activity_id_str}\n"
                f"   done: true\n"
                f"   note: redija uma nota curta (1-2 linhas) resumindo o contexto da conversa "
                f"encontrado no histórico acima (último contato, pendências discutidas, o que foi enviado). "
                f"Use o histórico de WhatsApp/Email já visível nesta conversa — NÃO chame ferramentas.\n\n"
                f"2. suggest_next_actions — somente após o update acima.\n\n"
                f"É PROIBIDO encerrar a tarefa sem executar ambas as ferramentas."
            )

        elif tool_name == "pipedrive_update_task":
            system_nudge = (
                "\n\n[SISTEMA]: Atividade do Pipedrive atualizada com sucesso.\n\n"
                "ÚLTIMA ETAPA OBRIGATÓRIA: chame agora 'suggest_next_actions' para "
                "apresentar ao usuário os próximos passos estratégicos com base em tudo "
                "que foi encontrado nesta investigação. NÃO encerre sem exibir as sugestões."
            )

    messages.append({
        "role": "user", 
        "content": all_results + ([{"type": "text", "text": system_nudge}] if system_nudge else [])
    })

    tools = get_tools_anthropic_schema()
    start_iter = pending.get("iteration", 1)

    final_response = ""
    collected_events = []
    
    async for chunk in _agent_loop(messages, tools, start_iteration=start_iter, org_id=pending_org_id, process_id=pending_process_id, parent_message_id=parent_message_id, action_index=action_index):
        try:
            data = _json.loads(chunk)
            collected_events.append(data)
            if data.get("type") == "final":
                final_response = data.get("response", "")
        except Exception:
            pass
        yield chunk

    if thread_id:
        try:
            from core.infra.database import async_session as _async_session
            async with _async_session() as db:
                if parent_message_id and action_index is not None:
                    # Carrega a mensagem do assistente pai e atualiza os eventos dela
                    from sqlalchemy import select
                    from models.conversation import ConversationMessage
                    result = await db.execute(
                        select(ConversationMessage).where(ConversationMessage.id == parent_message_id)
                    )
                    parent_msg = result.scalar_one_or_none()
                    if parent_msg:
                        msg_data = dict(parent_msg.data or {})
                        runs = msg_data.get("suggested_actions_runs", {})
                        
                        # Recupera logs anteriores de SuggestedActionTask (que geraram a confirmação)
                        prev_run = runs.get(str(action_index), {})
                        prev_logs = prev_run.get("logs", [])
                        
                        # Combina os logs anteriores com os novos logs desta retomada
                        combined_logs = prev_logs + collected_events
                        
                        has_confirm = any(e.get("type") == "confirmation_required" for e in collected_events)
                        action_status = "awaiting_confirm" if has_confirm else "done"
                        
                        runs[str(action_index)] = {
                            "status": action_status,
                            "logs": combined_logs,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        msg_data["suggested_actions_runs"] = runs
                        parent_msg.data = msg_data
                        
                        # Também atualiza o log/evento "suggested_actions" original em parent_msg.logs
                        parent_logs = list(parent_msg.logs or [])
                        for event in parent_logs:
                            if event.get("type") == "suggested_actions" and "actions" in event:
                                if 0 <= action_index < len(event["actions"]):
                                    action_item = event["actions"][action_index]
                                    action_item["status"] = action_status
                                    action_item["logs"] = combined_logs
                        parent_msg.logs = parent_logs
                        
                        db.add(parent_msg)
                        await db.commit()
                        log.info("agent.suggested_action.confirm.saved_to_parent", parent_message_id=parent_message_id, action_index=action_index)
                else:
                    from api.v1.routers.conversations import save_message as _save_message
                    if final_response or collected_events:
                        await _save_message(db, thread_id, "assistant", final_response or "", logs=collected_events)
            log.info("agent.messages.resumed_saved", thread_id=thread_id)
        except Exception as e:
            log.warning("agent.messages.resumed_save_failed", thread_id=thread_id, error=str(e))