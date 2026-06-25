"""
modules.agent.service.core.loop_executor
=========================================
Executor de ferramentas de leitura/escrita e controle de confirmações do loop do agente.
"""
from __future__ import annotations
import uuid
import json
import inspect
import asyncio
from typing import Any, AsyncGenerator, Dict, List
from modules.agent.service.helpers import _emit, _raw_log, _get_label
from modules.agent.service.sanitizers import _sanitize_result
from modules.agent.service.core.thread_memory import DEDUP_TOOLS
from core.observability.logging_config import get_logger

log = get_logger(__name__)

async def execute_read_tools_batch(
    read_blocks: List[tuple],
    messages: List[Dict],
    org_id: int | None,
    process_id: str,
    query_type: str,
    ctx: Dict,
    tool_results: List[Dict],
    collected_tool_summaries: List[str],
    loop_state: Dict[str, Any],
    _PENDING: Dict[str, Any],
) -> AsyncGenerator[Dict, None]:
    """
    Executa em lote as ferramentas de leitura do turno.
    Yields eventos NdJSON para o streaming.
    Modifica in-place lists/dicts passados (tool_results, loop_state, etc.).
    """
    from modules.agent.service.core._activity_prompts import _build_task_action_prompt

    for first_block, first_call_id, first_executor in read_blocks:
        tool_args = first_block.get("input") or {}
        tool_id = first_block.get("id", "")
        tool_name = first_block.get("name", "")

        yield _emit({
            "type": "tool_call",
            "call_id": first_call_id,
            "tool": tool_name,
            "args": tool_args,
            "label": _get_label(tool_name, tool_args)
        })

        _raw_log(process_id, "tool_execute_start", {"tool": tool_name, "args": tool_args, "call_id": first_call_id})

        try:
            exec_kwargs = {}
            try:
                sig = inspect.signature(first_executor)
                params = sig.parameters
                if "org_id" in params:
                    exec_kwargs["org_id"] = org_id
                if "messages" in params:
                    exec_kwargs["messages"] = messages
                if "process_id" in params:
                    exec_kwargs["process_id"] = process_id
            except Exception:
                pass

            tool_result = await first_executor(tool_args, **exec_kwargs)
            _raw_log(process_id, "tool_execute_result", {"tool": tool_name, "result_raw": tool_result, "call_id": first_call_id})
        except Exception as e:
            tool_result = {"ok": False, "error": str(e)}

        # Retry logic para erros inesperados de conexão/Timeout
        if not tool_result.get("ok"):
            _err = str(tool_result.get("error", "")).lower()
            _expected = any(x in _err for x in [
                "não encontrad", "not found", "nenhum", "0 contatos", "0 deal",
                "0 mensagens", "0 e-mail", "sem histórico",
            ])
            if not _expected:
                try:
                    await asyncio.sleep(1)
                    tool_result = await first_executor(tool_args, **exec_kwargs)
                except Exception as e:
                    tool_result = {"ok": False, "error": str(e)}

        ok = tool_result.get("ok", False)
        if ok and isinstance(tool_result, dict):
            org_val = tool_result.get("org")
            org_id_from_org = org_val.get("id") if isinstance(org_val, dict) else None
            res_org_id = tool_result.get("org_id") or org_id_from_org
            if res_org_id:
                try:
                    org_id = int(res_org_id)
                    loop_state["org_id"] = org_id
                    log.info("agent.session_org_id.updated", org_id=org_id, tool_name=tool_name)
                except (ValueError, TypeError):
                    pass

        # Identifica o contato principal a partir das atividades pendentes
        if ok and tool_name == "pipedrive_get_activities" and not loop_state.get("session_task_person"):
            _pending_acts = (tool_result.get("pending") or []) if isinstance(tool_result, dict) else []
            for _a in _pending_acts:
                if isinstance(_a, dict) and _a.get("person_name"):
                    loop_state["session_task_person"] = _a["person_name"]
                    log.info("agent.session_task_person.set", person=loop_state["session_task_person"])
                    break

        summary = tool_result.get("summary") or tool_result.get("error") or ("OK" if ok else "Erro")

        sanitized = _sanitize_result(tool_name, tool_result)
        raw_content = json.dumps(sanitized, ensure_ascii=False) if isinstance(sanitized, (dict, list)) else str(sanitized)
        _max_content = 4000 if tool_name in ("pipedrive_get_all_activities", "email_get_inbox", "email_get_contact_history", "evaluate_prospects") else 2000
        if len(raw_content) > _max_content:
            raw_content = raw_content[:_max_content] + "... [TRUNCADO]"

        emitted_result = {"type": "tool_result", "call_id": first_call_id, "tool": tool_name, "summary": summary, "ok": ok, "args": tool_args}
        emitted_data = {}
        if "quota" in tool_result:
            emitted_data["quota"] = tool_result.get("quota")
        if "plan" in tool_result:
            emitted_data["plan"] = tool_result.get("plan")
        if "org_name" in tool_result:
            emitted_data["org_name"] = tool_result.get("org_name")
        if ok and tool_name in DEDUP_TOOLS:
            # Persiste o conteúdo sanitizado (não só o summary curto) para que uma nova
            # mensagem do usuário nesta mesma thread, mais tarde, possa reaproveitar o
            # resultado real desta busca em vez de chamar a tool de novo — ver thread_memory.py.
            emitted_data["cached_content"] = raw_content

        if emitted_data:
            emitted_result["data"] = emitted_data

        yield _emit(emitted_result)
        yield _emit({"type": "context_saved"})

        if ok and summary:
            collected_tool_summaries.append(f"[{tool_name}] {summary}")

        # Confirmação dinâmica
        if ok and tool_result.get("status") == "confirmation_required":
            action_id = f"act_{uuid.uuid4().hex[:6]}"
            _PENDING[action_id] = {
                "call_id": first_call_id,
                "tool_use_id": first_call_id,
                "tool": tool_name,
                "args": tool_args,
                "label": _get_label(tool_name, tool_args),
                "org_id": org_id,
                "process_id": process_id,
                "messages_snapshot": list(messages),
                "prior_results": list(tool_results), 
                "iteration": loop_state.get("iteration", 0) + 1,
                "query_type": query_type,
                "options": tool_result.get("options"),
            }

            yield _emit({
                "type": "confirmation_required",
                "action_id": action_id,
                "tool": tool_name,
                "label": tool_result.get("summary", "Confirmação necessária"),
                "preview": tool_result.get("message", ""),
                "org_id": org_id,
                "org_name": tool_result.get("org_name"),
                "options": tool_result.get("options")
            })
            if not loop_state.get("final_emitted"):
                loop_state["final_emitted"] = True
                yield _emit({"type": "final", "response": tool_result.get("message", "Aguardando sua decisão para prosseguir.")})
            loop_state["should_return"] = True
            return

        if ok and tool_name == "suggest_next_actions":
            actions = tool_result.get("actions", [])
            if actions:
                yield _emit({"type": "suggested_actions", "actions": actions})
            loop_state["should_break"] = True

        # Hierarchy Mapper
        if ok and tool_name == "open_hierarchy_drawer":
            yield _emit({
                "type": "hierarchy_mapping_required",
                "org_name": tool_result.get("org_name"),
                "org_id": tool_result.get("org_id"),
                "deal_id": tool_result.get("deal_id"),
                "activity_id": tool_result.get("activity_id"),
                "pre_task_id": tool_result.get("pre_task_id"),
            })
            if not loop_state.get("final_emitted"):
                loop_state["final_emitted"] = True
                _org = tool_result.get("org_name", "a empresa")
                yield _emit({"type": "final", "response": f"Empresa **{_org}** aberta no mapeador. Insira o CNPJ e inicie o mapeamento — assim que terminar, continuarei automaticamente."})
            loop_state["should_return"] = True
            return

        # Pipedrive tasks list
        if ok and tool_name == "pipedrive_get_all_activities" and query_type == "pipedrive_tasks":
            _pd_actions = []
            for _act in tool_result.get("overdue", []):
                _subj = _act.get("subject") or ""
                _org = _act.get("org") or ""
                _act_id = _act.get("id")
                if not _act_id:
                    continue
                _pd_actions.append({
                    "label": f"⚠️ ATRASADA → {_subj}" + (f"  ·  {_org}" if _org else ""),
                    "prompt": _build_task_action_prompt(
                        _act_id, _subj, _org,
                        _act.get("org_id"), _act.get("deal_id"),
                        _act.get("type", ""), _act.get("note", ""),
                        ctx=ctx
                    ),
                })
            for _act in tool_result.get("today", []):
                _subj = _act.get("subject") or ""
                _org = _act.get("org") or ""
                _act_id = _act.get("id")
                if not _act_id:
                    continue
                _pd_actions.append({
                    "label": f"{_subj}" + (f"  →  {_org}" if _org else ""),
                    "prompt": _build_task_action_prompt(
                        _act_id, _subj, _org,
                        _act.get("org_id"), _act.get("deal_id"),
                        _act.get("type", ""), _act.get("note", ""),
                        ctx=ctx
                    ),
                })
            if _pd_actions:
                yield _emit({"type": "suggested_actions", "actions": _pd_actions})

        tool_results.append({
            "type": "tool_result",
            "tool_use_id": tool_id,
            "tool_name": tool_name,
            "content": raw_content,
        })


async def handle_write_tool_pending(
    write_tool_pending: Dict,
    messages: List[Dict],
    content: List[Dict],
    tool_results: List[Dict],
    iteration: int,
    org_id: int | None,
    process_id: str,
    parent_message_id: str | None,
    action_index: int | None,
    direct_action: bool,
    preferred: str | None,
    strict_mode: bool,
    query_type: str,
    TOOLS: Dict[str, Any],
    _PENDING: Dict[str, Any],
) -> AsyncGenerator[Dict, None]:
    """
    Registra e emite confirmação para ferramentas de escrita pendentes.
    Yields eventos confirmation_required e final.
    """
    action_id = str(uuid.uuid4())
    block = write_tool_pending["block"]
    tool_name = block["name"]
    tool_args = block["input"] or {}
    
    if tool_name == "open_ligacao_view" and not tool_args.get("flight_plan"):
        try:
            from services.realtime_call import assistant_manager
            _ap = assistant_manager.get_active_coaching_plan() or {}
            if _ap:
                tool_args["flight_plan"] = _ap
        except Exception:
            pass

    messages_with_assistant = messages + [{"role": "assistant", "content": content}]

    _PENDING[action_id] = {
        "tool_use_id": block["id"],
        "tool": tool_name,
        "args": tool_args,
        "call_id": write_tool_pending["call_id"],
        "label": write_tool_pending["label"],
        "messages_snapshot": messages_with_assistant,
        "prior_results": tool_results,
        "iteration": iteration + 1,
        "org_id": write_tool_pending.get("org_id"),
        "process_id": process_id,
        "parent_message_id": parent_message_id,
        "action_index": action_index,
        "direct_action": direct_action,
        "preferred": preferred,
        "strict_mode": strict_mode,
        "query_type": query_type,
    }

    label_fn = TOOLS[tool_name].get("confirm_label")
    confirm_label = label_fn(tool_args) if callable(label_fn) else write_tool_pending["label"]
    
    if tool_name == "open_ligacao_view":
        _steps_count = len(tool_args.get("flight_plan", {}).get("steps", []))
        preview = f"Plano de voo incluído ({_steps_count} passos). Prontos para ligar!"
    else:
        preview = tool_args.get("message") or tool_args.get("body") or json.dumps(tool_args, ensure_ascii=False)[:120]

    if tool_name in ("email_send", "email_reply") and isinstance(preview, str):
        try:
            from modules.ai.service.context.business_context_service import BusinessContextService
            ctx = await BusinessContextService.get_tenant_context()
            sig_path = ctx.get("signature_path")
            if sig_path:
                sig_html = f'<br><br><img src="http://localhost:8000/api/v1/settings/v2/profile/signature/image" style="max-width: 400px; height: auto; border-radius: 8px;" />'
                if "img src" not in preview:
                    preview = preview + "\n\n" + sig_html
        except Exception as e:
            log.warning(f"Erro no preview email signature: {e}")

    yield _emit({
        "type": "confirmation_required",
        "action_id": action_id,
        "call_id": write_tool_pending["call_id"],
        "tool": tool_name,
        "label": confirm_label,
        "preview": str(preview),
        "args": tool_args,
    })
    
    yield _emit({"type": "final", "response": preview if tool_name == "open_ligacao_view" else "Aguardando confirmação para executar a ação comercial."})
