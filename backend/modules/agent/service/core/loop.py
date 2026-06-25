"""
modules.agent.service.core.loop
=================================
Loop principal do agente autônomo (async generator de eventos NDJSON).

Funções neste arquivo:
    _agent_loop                  — loop central de tool-calling (entry point)
"""
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List

from modules.agent.service.helpers import (
    _emit, _raw_log, _get_thinking_fallback, _get_label,
    _get_tools_called,
)
from modules.agent.service.sanitizers import _sanitize_result
from modules.agent.service.tools import TOOLS, execute_write_tool, get_tools_anthropic_schema
from modules.agent.service.prompts import (
    SYSTEM_PROMPT_POWERFUL, SYSTEM_PROMPT_BASIC, SYSTEM_PROMPT_DIRECT,
    SYSTEM_PROMPT_TASK_DIRECTIVE,
)
from modules.agent.service.llm.caller import _call_with_tools
from modules.agent.service.core.phase_tracker import _build_phase_status
from modules.agent.service.core._activity_prompts import (
    _dispatch_activity_etapas,
    _build_task_action_prompt,
)
from core.observability.logging_config import get_logger

# Submódulos extraídos
from modules.agent.service.core.loop_utils import (
    _suggest_actions_done,
    _extract_json_objects,
    _prune_messages,
)
from modules.agent.service.core.loop_interceptors import (
    intercept_pre_execution,
    intercept_post_llm_turn,
)
from modules.agent.service.core.loop_executor import (
    execute_read_tools_batch,
    handle_write_tool_pending,
)
from modules.agent.service.core.thread_memory import dedup_key_for

log = get_logger(__name__)

MAX_ITERATIONS = 45

# Compartilhado com runner.py — ações de escrita pendentes aguardando confirmação
_PENDING: Dict[str, Dict[str, Any]] = {}


async def _agent_loop(
    messages: list,
    tools: list,
    start_iteration: int = 0,
    org_id: int | None = None,
    preferred: str | None = None,
    strict_mode: bool = False,
    process_id: str | None = None,
    direct_action: bool = False,
    parent_message_id: str | None = None,
    action_index: int | None = None,
    query_type: str = "agent_workflow",
    active_skill: Any = None,
    thread_tool_memory: Dict[str, dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Loop central do agente. Yields eventos NDJSON."""
    import re as _re
    process_id = process_id or f"proc_{uuid.uuid4().hex[:8]}"

    # Sinais de detecção persistentes
    _has_local_decision_maker = False
    _persons_with_wa: list[tuple] = []
    _persons_with_email: list[tuple] = []

    # Acumula resultados de ferramentas para degradação graciosa
    _collected_tool_summaries: list[str] = []
    # Garante que o evento final seja emitido apenas uma vez (dossiê)
    _final_emitted = False
    
    _first_msg_content = ""
    for _m in messages:
        if _m.get("role") == "user":
            _mc = _m.get("content", "")
            if isinstance(_mc, str):
                _first_msg_content = _mc
                break
            elif isinstance(_mc, list):
                if _mc and isinstance(_mc[0], dict) and (_mc[0].get("type") == "tool_result" or "tool_name" in _mc[0] or "tool_use_id" in _mc[0]):
                    continue
                text_content = " ".join(_b.get("text", "") for _b in _mc if isinstance(_b, dict) and _b.get("type") == "text")
                if text_content.strip():
                    _first_msg_content = text_content
                    break

    # Compila apenas as instruções textuais reais do usuário
    _user_msgs = []
    for _m in messages:
        if _m.get("role") == "user":
            _mc = _m.get("content", "")
            if isinstance(_mc, list):
                if _mc and isinstance(_mc[0], dict) and (_mc[0].get("type") == "tool_result" or "tool_name" in _mc[0] or "tool_use_id" in _mc[0]):
                    continue
                _user_msgs.append(" ".join(_b.get("text", "") for _b in _mc if isinstance(_b, dict) and _b.get("type") == "text"))
            elif isinstance(_mc, str):
                _user_msgs.append(_mc)

    # Limpa alertas de sistema e metadados envoltos em colchetes [ ... ]
    _user_instructions_clean = []
    for _text in _user_msgs:
        if isinstance(_text, str):
            _user_instructions_clean.append(_re.sub(r'\[.*?\]', '', _text, flags=_re.DOTALL))
    _user_instructions_text = " ".join(_user_instructions_clean).lower()

    _first_msg_content_clean = ""
    if isinstance(_first_msg_content, str):
        _clean_text = _first_msg_content.split("[INSTRUÇÕES DA PIPELINE]")[0]
        _first_msg_content_clean = _re.sub(r'\[.*?\]', '', _clean_text, flags=_re.DOTALL)

    # Sinais que identificam um prompt de execução de tarefa CRM
    _TASK_SIGNALS = [
        "ATIVIDADE #",
        "Execute agora, começando pelo raciocínio",
        "EXECUTE ESTAS ETAPAS EM ORDEM",
        "ETAPA 1 — Pipedrive",
        "ETAPA 1 — ",
        "Investigue a empresa",
        "Execute a seguinte atividade do CRM",
    ]
    _has_task_signal = any(s in _first_msg_content for s in _TASK_SIGNALS)

    if _has_task_signal and not direct_action:
        direct_action = True

    _is_task_action = direct_action and _has_task_signal
    _is_find_decisor_task = any(kw in _first_msg_content_clean.lower() for kw in [
        "encontrar contato", "encontrar decisor", "open_hierarchy_drawer",
        "encontrar o contato", "identificar contato", "localizar contato",
    ])

    yield _emit({"type": "agent_start", "process_id": process_id, "message": _first_msg_content[:100]})

    _max_iters = (35 if _is_task_action else 12) if direct_action else MAX_ITERATIONS
    _is_direct_directive = not _has_task_signal

    _PINNED_TOOLS = {
        "deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals",
        "pipedrive_get_activities", "whatsapp_get_messages", "email_get_contact_history",
    }

    # Guard de deduplicação de tool calls — pré-semeado com (1) tool_use já presentes nas
    # `messages` desta execução e (2) a memória persistida da thread inteira (chamadas
    # feitas em mensagens anteriores do usuário, possivelmente em execuções passadas do
    # loop — ver thread_memory.py). Sem (2), o agente esquece tudo que buscou assim que
    # a mensagem sai da janela recente enviada pelo frontend.
    _tool_call_history: set = set(thread_tool_memory.keys()) if thread_tool_memory else set()
    for _m in messages:
        _mc = _m.get("content", "")
        if isinstance(_mc, list):
            for _b in _mc:
                if isinstance(_b, dict) and _b.get("type") == "tool_use":
                    _key = dedup_key_for(_b.get("name", ""), _b.get("input") or {})
                    if _key:
                        _tool_call_history.add(_key)
                        
    _session_task_person: str | None = None
    for _m in messages:
        if _m.get("role") == "user":
            _content = str(_m.get("content", ""))
            _match = _re.search(r'\bcom\s+([A-Z][a-zA-ZÀ-ÿ]+(?:\s+(?:de|da|do|dos|e|[A-Z][a-zA-ZÀ-ÿ]+))*)', _content)
            if _match:
                _raw_name = _match.group(1).strip()
                _words = _raw_name.split()
                _clean_words = []
                for _w in _words:
                    if _w.lower() in ("para", "empresa", "a", "o", "com", "na", "no", "em", "um", "uma"):
                        break
                    else:
                        _clean_words.append(_w)
                while _clean_words and _clean_words[-1].lower() in ("de", "da", "do", "dos", "e"):
                    _clean_words.pop()
                if _clean_words:
                    _session_task_person = " ".join(_clean_words)
                    log.info("agent.session_task_person.extracted_from_prompt", person=_session_task_person)
                    break

    _cached_final_response: str | None = None
    
    for iteration in range(start_iteration, _max_iters):
        if _suggest_actions_done(messages):
            _final_text = _cached_final_response or "Ações sugeridas criadas com sucesso."
            yield _emit({"type": "final", "response": _final_text})
            return

        # Poda de memória inteligente
        messages = _prune_messages(messages, _PINNED_TOOLS, max_len=40)

        # Encontra a última vez que pipedrive_get_persons foi chamado na tarefa atual
        _has_local_decision_maker = False
        _persons_with_wa = []
        _persons_with_email = []
        
        _last_persons_msg = None
        for _m in messages:
            _mc = _m.get("content", "")
            if not isinstance(_mc, list): continue
            for _b in _mc:
                if isinstance(_b, dict) and _b.get("type") == "tool_result" and _b.get("tool_name") == "pipedrive_get_persons":
                    _last_persons_msg = _b

        if _last_persons_msg:
            _raw_c = _last_persons_msg.get("content", "")
            try:
                _text = json.loads(_raw_c) if isinstance(_raw_c, str) else _raw_c
            except Exception:
                _text = _raw_c
            
            if isinstance(_text, str) and "[ALERTA: DECISOR LOCAL ENCONTRADO]" in _text:
                _has_local_decision_maker = True

            if isinstance(_text, dict):
                for _p in (_text.get("persons") or []):
                    _pn = _p.get("name", "")
                    if _pn:
                        if _p.get("phone"): _persons_with_wa.append((_pn, _p.get("phone")))
                        if _p.get("email"): _persons_with_email.append((_pn, _p.get("email")))
            elif isinstance(_text, str):
                for _line in _text.split('\n'):
                    _m2 = _re.search(r'\[ID:[^\]]+\]\s*([^(\n]+?)\s*\(([^)]+)\)', _line)
                    if _m2:
                        _pn = _m2.group(1).strip()
                        _pc = _m2.group(2).strip()
                        if _pn and _pc and _pc != "sem contato":
                            if "@" in _pc: _persons_with_email.append((_pn, _pc))
                            else: _persons_with_wa.append((_pn, _pc))

        # System prompt por fase
        from modules.ai.service.context.business_context_service import BusinessContextService
        from modules.agent.service.prompts import render_prompt
        
        ctx = await BusinessContextService.get_tenant_context()
        seller_name = ctx.get("seller_name", "o Vendedor")
        company_name = ctx.get("company_name", "a Empresa")

        if active_skill:
            _last_content = messages[-1].get('content', '') if messages else ''
            if isinstance(_last_content, list):
                _last_content = ' '.join(
                    b.get('text', '') if isinstance(b, dict) else str(b)
                    for b in _last_content
                )
            _act_id_match = _re.search(r'ID da tarefa no Pipedrive:\s*(\d+)', _last_content)
            _skill_ctx = {"org_id": org_id, "process_id": process_id}
            if _act_id_match:
                _skill_ctx["activity_id"] = int(_act_id_match.group(1))

            if _is_direct_directive:
                system = render_prompt(SYSTEM_PROMPT_TASK_DIRECTIVE, ctx)
                skill_inst = render_prompt(active_skill.get_instructions(_skill_ctx), ctx)
                system += f"\n\n[CONTEXTO DE BACKGROUND DA TAREFA ATUAL]:\nO usuário pediu uma ação pontual (diretiva livre) dentro desta tarefa. As regras da diretiva livre (Fim da burocracia) são SOBERANAS e você DEVE cumpri-las e pular quaisquer investigações ou Fases obrigatórias ditadas no texto abaixo. Eis o background apenas para que você tenha contexto das regras de negócio gerais:\n\n{skill_inst}"
            else:
                system = render_prompt(active_skill.get_instructions(_skill_ctx), ctx)
                if hasattr(active_skill, "get_advance_prompt"):
                    adv_prompt = render_prompt(active_skill.get_advance_prompt(), ctx)
                    if adv_prompt:
                        system += f"\n\n{adv_prompt}"
        elif _is_direct_directive:
            system = render_prompt(SYSTEM_PROMPT_TASK_DIRECTIVE, ctx)
        elif direct_action:
            system = render_prompt(SYSTEM_PROMPT_DIRECT, ctx)
        else:
            try:
                system = _build_phase_status(messages, query_type=query_type, org_id=org_id, ctx=ctx)
            except Exception:
                system = render_prompt(SYSTEM_PROMPT_POWERFUL, ctx)

        system += "\n\n[REGRA GLOBAL DE IDIOMA]: Você deve OBRIGATORIAMENTE se comunicar com o usuário em PORTUGUÊS (PT-BR) em todas as suas respostas, resumos e sugestões. Nunca responda em inglês."

        # Filtragem de ferramentas permitidas pelo skill
        _current_tools = tools
        if active_skill and not _is_direct_directive:
            _current_tools = [t for t in tools if t.get("name") in active_skill.allowed_tools]
            
            # Safeguard para injetar a ferramenta exigida pelo phase tracker se faltar
            _re_tools = _re.compile(r'PRÓXIMA FERRAMENTA:\s*([^\s]+)')
            m_required = _re_tools.search(system)
            if m_required:
                req_tool = m_required.group(1).strip()
                if not any(t.get("name") == req_tool for t in _current_tools):
                    for t_full in tools:
                        if t_full.get("name") == req_tool:
                            _current_tools.append(t_full)
                            break

        _raw_log(process_id, "llm_request", {"system": system, "messages": messages, "iteration": iteration})
        _pending_events: list = []
        _force = False
        _allowed_core: list | None = None
        
        if _is_direct_directive:
            pass
        elif active_skill:
            _CORE = set(active_skill.core_tools)
            _CORE_ORDER = list(active_skill.core_tools)
            
            if _session_task_person:
                _CORE.discard("evaluate_prospects")
                if "evaluate_prospects" in _CORE_ORDER:
                    _CORE_ORDER.remove("evaluate_prospects")
                    
            _done = _get_tools_called(messages, target_tools=_CORE)
            _missing_core = _CORE - _done
            if _missing_core:
                _force = True
                _next_core = next((t for t in _CORE_ORDER if t not in _done), None)
                if _next_core:
                    _allowed_core = [_next_core]
        elif _is_task_action:
            if _is_find_decisor_task:
                _CORE = {"pipedrive_get_org", "pipedrive_get_persons"}
                _CORE_ORDER = ["pipedrive_get_org", "pipedrive_get_persons"]
            else:
                _CORE = {"pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"}
                _CORE_ORDER = ["pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"]
            
            _done = _get_tools_called(messages, target_tools=_CORE)
            _missing_core = _CORE - _done
            if _missing_core:
                _force = True
                _next_core = next((t for t in _CORE_ORDER if t not in _done), None)
                if _next_core:
                    _allowed_core = [_next_core]
            else:
                _comm_tools = {"whatsapp_get_messages", "email_get_contact_history", "batch_communication_search"}
                _comm_done = _get_tools_called(messages, target_tools=_comm_tools)
                if not _comm_done:
                    _force = True
                    _allowed_core = ["batch_communication_search"]

        # Detector de loop de histórico de buscas
        if _is_task_action and not _force:
            _comm_counts: dict[str, int] = {}
            for _m in messages:
                _mc = _m.get("content","")
                if isinstance(_mc, list):
                    for _b in _mc:
                        if isinstance(_b, dict) and _b.get("type") == "tool_use":
                            _tn = _b.get("name","")
                            if _tn in ("whatsapp_get_messages","email_get_contact_history","pipedrive_get_persons"):
                                _comm_counts[_tn] = _comm_counts.get(_tn, 0) + 1
            _loop_detected = any(v >= 3 for v in _comm_counts.values())
            if _loop_detected and iteration < _max_iters - 2:
                _contacts_summary = ""
                for _m in messages:
                    _mc = _m.get("content","")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict) and _b.get("type") == "tool_result" and _b.get("tool_name") == "pipedrive_get_persons":
                                _contacts_summary = str(_b.get("content",""))[:400]
                messages.append({
                    "role": "user",
                    "content": (
                        "Você está em loop buscando histórico de comunicação. "
                        "Já investigou todos os canais disponíveis e não encontrou histórico. "
                        "PARE de buscar. Contatos da empresa: " + (_contacts_summary or "ver histórico anterior") + "\n"
                        "Próxima ação obrigatória: com base no que foi coletado, decida a ação "
                        "de comunicação adequada (email de reativação, WhatsApp, etc.) e execute. "
                        "Não busque mais histórico — não existe."
                    ),
                })

        # Executa a chamada do LLM em background para reportar pacing ao front
        _llm_task = asyncio.create_task(_call_with_tools(
            system, messages, _current_tools,
            preferred=preferred, strict_mode=strict_mode,
            pending_events=_pending_events,
            force_tool_call=_force,
            allowed_tool_names=_allowed_core,
        ))
        while not _llm_task.done():
            while _pending_events:
                yield _emit(_pending_events.pop(0))
            await asyncio.sleep(0.05)
        response = await _llm_task

        if response and not strict_mode:
            succ_model = response.get("_successful_model")
            if succ_model:
                preferred = succ_model

        for _ev in _pending_events:
            yield _emit(_ev)
        _pending_events.clear()
        _raw_log(process_id, "llm_response", {"response": response})

        content = response.get("content", [])
        stop_reason = response.get("stop_reason", "end_turn")
        text_blocks = [b for b in content if b.get("type") == "text"]
        tool_use_blocks = [b for b in content if b.get("type") == "tool_use"]

        # Conversão de JSON embutido no texto em tool_use real
        if text_blocks:
            _combined_text = " ".join(b.get("text", "") for b in text_blocks)
            for _jc in _extract_json_objects(_combined_text):
                try:
                    _obj = json.loads(_jc)
                    _tool_name = _obj.get("name") or _obj.get("function")
                    _tool_args = _obj.get("arguments") or _obj.get("input") or _obj.get("parameters") or {}
                    if isinstance(_tool_args, str):
                        try:
                            _tool_args = json.loads(_tool_args)
                        except Exception:
                            _tool_args = {}
                    if _tool_name and _tool_name in TOOLS and isinstance(_tool_args, dict):
                        if not tool_use_blocks:
                            tool_use_blocks.append({
                                "type": "tool_use",
                                "id": f"tc_fallback_{uuid.uuid4().hex[:8]}",
                                "name": _tool_name,
                                "input": _tool_args,
                            })
                            stop_reason = "tool_use"
                        text_blocks = [
                            {**b, "text": b.get("text", "").replace(_jc, "").strip()}
                            for b in text_blocks
                        ]
                        text_blocks = [b for b in text_blocks if b.get("text")]
                        content = text_blocks + tool_use_blocks
                        break
                except Exception:
                    pass

        # Emite sinal de thinking se houver chamadas de ferramentas sem narração prévia
        if tool_use_blocks:
            first_tool = tool_use_blocks[0]
            native_text = " ".join(b.get("text", "").strip() for b in text_blocks).strip()
            native_is_complete = bool(native_text and native_text[-1] in ".!?")

            if native_is_complete and len(native_text) > 40:
                yield _emit({"type": "thinking", "content": native_text})
            else:
                _tn = first_tool.get("name", "")
                _ta = first_tool.get("input") or {}
                if _tn != "suggest_next_actions":
                    yield _emit({"type": "thinking", "content": _get_thinking_fallback(_tn, _ta)})

        # Resposta final de texto puro
        if stop_reason in ("end_turn", "stop") or not tool_use_blocks:
            if not content:
                fallback_msg = {"type": "text", "text": "*(Turno silencioso - aguardando instruções do sistema)*"}
                content.append(fallback_msg)
                text_blocks.append(fallback_msg)

            response_text = " ".join(b.get("text", "") for b in text_blocks).strip()
            if "parada antecipada" in response_text.lower():
                yield _emit({"type": "final", "response": response_text})
                return

        # 🚀 Execução de Interceptores pós-LLM
        should_continue, final_resp, updated_final_emitted, cached_final_resp = await intercept_post_llm_turn(
            messages=messages,
            content=content,
            response_text=" ".join(b.get("text", "") for b in text_blocks).strip(),
            query_type=query_type,
            org_id=org_id,
            direct_action=direct_action,
            is_task_action=_is_task_action,
            is_find_decisor_task=_is_find_decisor_task,
            first_msg_content_clean=_first_msg_content_clean,
            first_msg_content=_first_msg_content,
            session_task_person=_session_task_person,
            persons_with_wa=_persons_with_wa,
            persons_with_email=_persons_with_email,
            has_local_decision_maker=_has_local_decision_maker,
            iteration=iteration,
            max_iters=_max_iters,
            process_id=process_id,
            stop_reason=stop_reason,
            tool_use_blocks=tool_use_blocks,
            collected_tool_summaries=_collected_tool_summaries,
            active_skill=active_skill,
            ctx=ctx,
            final_emitted=_final_emitted,
        )
        
        _final_emitted = updated_final_emitted
        if cached_final_resp is not None:
            _cached_final_response = cached_final_resp

        if should_continue:
            continue
        if final_resp is not None:
            yield _emit({"type": "final", "response": final_resp})
            return

        # Execução das ferramentas solicitadas pelo LLM
        tool_results: list = []
        read_blocks: list = []
        write_tool_pending: dict | None = None

        for block in tool_use_blocks:
            tool_name = block.get("name", "")
            tool_args = block.get("input") or {}
            tool_id = block.get("id", "")

            # 🚀 Interceptores Pré-Execução
            block_res = await intercept_pre_execution(
                tool_name=tool_name,
                tool_args=tool_args,
                tool_id=tool_id,
                messages=messages,
                org_id=org_id,
                has_local_decision_maker=_has_local_decision_maker,
                session_task_person=_session_task_person,
                is_task_action=_is_task_action,
                is_find_decisor_task=_is_find_decisor_task,
                query_type=query_type,
                direct_action=direct_action,
                active_skill=active_skill,
                ctx=ctx,
                tool_use_blocks=tool_use_blocks,
                seller_name=seller_name,
                company_name=company_name,
                tool_call_history=_tool_call_history,
            )
            if block_res is not None:
                tool_results.append(block_res)
                continue

            if tool_name not in TOOLS:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": f"Ferramenta '{tool_name}' não encontrada",
                    "is_error": True,
                })
                continue

            # Deduplicação de tool calls — agora também olha a memória persistida da
            # thread inteira (thread_tool_memory), não só o que já rodou nesta execução.
            _dedup_key = dedup_key_for(tool_name, tool_args)
            if _dedup_key:
                if _dedup_key in _tool_call_history:
                    log.warning("agent.tool_call.dedup_blocked", tool=tool_name, tool_args=str(tool_args)[:80])
                    _cached = (thread_tool_memory or {}).get(_dedup_key)
                    if _cached and _cached.get("content"):
                        # Reaproveita o resultado real já coletado (nesta execução ou em
                        # mensagem anterior da mesma thread) em vez de só bloquear sem dados.
                        _dedup_content = (
                            f"[JÁ CONSULTADO NESTA CONVERSA — reaproveitando resultado anterior, "
                            f"NÃO repita esta chamada]\n{_cached['content']}"
                        )
                    else:
                        _dedup_content = f"[DEDUP] {_dedup_key} já foi executada nesta sessão. Avance para o próximo contato ou ação."
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": _dedup_content,
                        "is_error": False,
                        "summary": "[já coletado]",
                    })
                    continue
                else:
                    _tool_call_history.add(_dedup_key)

            tool_meta = TOOLS[tool_name]
            if tool_meta["type"] == "write":
                if write_tool_pending is None:
                    call_id = f"tc_{iteration}_{uuid.uuid4().hex[:6]}"
                    write_tool_pending = {
                        "block": block,
                        "call_id": call_id,
                        "label": _get_label(tool_name, tool_args),
                        "prior_results": [],
                        "org_id": org_id,
                    }
                continue

            executor = tool_meta.get("executor")
            if not executor:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": "Executor não definido",
                    "is_error": True,
                })
                continue

            call_id = f"tc_{iteration}_{uuid.uuid4().hex[:6]}"
            read_blocks.append((block, call_id, executor))

        # Executa as ferramentas de leitura em lote
        if read_blocks:
            loop_state = {
                "org_id": org_id,
                "session_task_person": _session_task_person,
                "final_emitted": _final_emitted,
                "iteration": iteration,
                "should_return": False,
            }
            async for event in execute_read_tools_batch(
                read_blocks=read_blocks,
                messages=messages,
                org_id=org_id,
                process_id=process_id,
                query_type=query_type,
                ctx=ctx,
                tool_results=tool_results,
                collected_tool_summaries=_collected_tool_summaries,
                loop_state=loop_state,
                _PENDING=_PENDING,
            ):
                yield event

            org_id = loop_state["org_id"]
            _session_task_person = loop_state["session_task_person"]
            _final_emitted = loop_state["final_emitted"]

            if loop_state.get("should_return"):
                return

        # Trata ferramenta de escrita pendente (com confirmação) se houver
        if write_tool_pending:
            # Salva o turno na memória ANTES de retornar, para evitar amnésia de ações paralelas
            messages.append({"role": "assistant", "content": content, "tool_use_id": [b["id"] for b in tool_use_blocks] if tool_use_blocks else None})
            messages.append({"role": "user", "content": tool_results})
            async for event in handle_write_tool_pending(
                write_tool_pending=write_tool_pending,
                messages=messages,
                content=content,
                tool_results=tool_results,
                iteration=iteration,
                org_id=org_id,
                process_id=process_id,
                parent_message_id=parent_message_id,
                action_index=action_index,
                direct_action=direct_action,
                preferred=preferred,
                strict_mode=strict_mode,
                query_type=query_type,
                TOOLS=TOOLS,
                _PENDING=_PENDING,
            ):
                yield event
            return

        # Salva o turno atual e continua para a próxima iteração
        messages.append({"role": "assistant", "content": content, "tool_use_id": [b["id"] for b in tool_use_blocks] if tool_use_blocks else None})
        messages.append({"role": "user", "content": tool_results})
        
        if _suggest_actions_done(messages):
            _final_text = _cached_final_response or "Ações sugeridas criadas com sucesso."
            yield _emit({"type": "final", "response": _final_text})
            return
        
        if loop_state.get("should_break") if "loop_state" in locals() else False:
            break

    # Fim das iterações
    yield _emit({
        "type": "final",
        "response": "Não consegui concluir a tarefa dentro do número máximo de passos. Tente reformular o pedido.",
    })
