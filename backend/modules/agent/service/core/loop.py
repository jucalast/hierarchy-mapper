"""
modules.agent.service.core.loop
=================================
Loop principal do agente autônomo (async generator de eventos NDJSON).

Funções neste arquivo:
    _suggest_actions_done        — verifica se suggest_next_actions já foi emitido
    _agent_loop                  — loop central de tool-calling (entry point)

Funções extraídas para sub-módulos:
    phase_tracker.py             → _build_phase_status (system prompt por fase)
    _activity_prompts.py         → _dispatch_activity_etapas, _build_task_action_prompt
"""
from __future__ import annotations
import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List

from modules.agent.service.helpers import (
    _emit, _raw_log, _fix_corrupted_name, _get_thinking_fallback, _get_label,
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

log = get_logger(__name__)

MAX_ITERATIONS = 45

# Compartilhado com runner.py — ações de escrita pendentes aguardando confirmação
_PENDING: Dict[str, Dict[str, Any]] = {}



def _suggest_actions_done(messages: list) -> bool:
    """Retorna True se suggest_next_actions foi efetivamente executada com sucesso."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "tool_result" and block.get("tool_name") == "suggest_next_actions":
                    res_content = str(block.get("content", ""))
                    if "SKIPPED" not in res_content and "Erro" not in res_content:
                        return True
    return False



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
    # Detecta se é uma tarefa multi-etapa (card de atividade do Pipedrive)
    # vs. aprovação de ação única — marcador injetado por _build_task_action_prompt
    _first_msg_content = messages[0].get("content", "") if messages else ""

    # Sinais que identificam um prompt de execução de tarefa CRM — gerado por
    # _build_task_action_prompt OU enviado manualmente via chat com o prefixo padrão.
    _TASK_SIGNALS = [
        "ATIVIDADE #",
        "Execute agora, começando pelo raciocínio",
        "EXECUTE ESTAS ETAPAS EM ORDEM",
        "ETAPA 1 — Pipedrive",
        "ETAPA 1 — ",
        "Investigue a empresa",
        "Execute a seguinte atividade do CRM",  # prefixo manual do frontend
    ]
    _has_task_signal = any(s in _first_msg_content for s in _TASK_SIGNALS)

    # Se o prompt parece uma tarefa CRM mas direct_action não foi sinalizado pelo
    # frontend (ex: enviado via chat normal), força o modo de tarefa automaticamente.
    if _has_task_signal and not direct_action:
        direct_action = True

    _is_task_action = direct_action and _has_task_signal
    _is_find_decisor_task = any(kw in _first_msg_content.lower() for kw in [
        "encontrar contato", "encontrar decisor", "open_hierarchy_drawer",
        "encontrar o contato", "identificar contato", "localizar contato",
    ])

    # ...
    # Yielding start event
    yield _emit({"type": "agent_start", "process_id": process_id, "message": _first_msg_content[:100]})

    _max_iters = (35 if _is_task_action else 12) if direct_action else MAX_ITERATIONS

    # ── DETECÇÃO DE DIRETIVA DIRETA ──
    # Conforme solicitado, todas as interações manuais (que não vierem do botão
    # "fazer com o agente" com o sinalizador de tarefa) são tratadas como diretivas.
    # Isso permite execução rápida sem a obrigação da longa contextualização (Bloco 1 e 2).
    _is_direct_directive = not _has_task_signal
    if _is_direct_directive:
        log.info("agent.intent.direct_directive_detected", content=_first_msg_content[:50])
        # active_skill é mantido para que as regras de negócio de funil não sejam perdidas


    # ── DETECÇÃO DE REUSO DE CONTEXTO ──
    # Se o histórico já contém as informações necessárias para a tarefa, 
    # injetamos uma instrução para pular a fase de investigação.
    _history_text = str(messages).lower()
    _has_org_info = "consultando" in _history_text and "pipedrive" in _history_text
    _has_comm_info = ("buscando e-mails" in _history_text) or ("buscando mensagens" in _history_text)
    _should_skip_investigation = _has_org_info and _has_comm_info
    
    # ── FILTRO DE REPETIÇÃO DE SUGESTÃO ──
    # Evita sugerir ações que o usuário acabou de aprovar ou que o agente acabou de executar.
    _executed_tools = []
    for _m in messages:
        _mc = _m.get("content", "")
        if isinstance(_mc, list):
            for _b in _mc:
                if isinstance(_b, dict):
                    _tn = _b.get("tool_name") or _b.get("name")
                    if _tn: _executed_tools.append(_tn)
    _just_updated_task = "pipedrive_update_task" in _executed_tools

    # sem eles o modelo perde a lista de contatos e começa a repetir ou pular buscas.
    _CTX_TOOLS = {
        "deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals",
        "pipedrive_get_activities", "whatsapp_get_messages", "email_get_contact_history",
    }
    _PINNED_TOOLS = _CTX_TOOLS

    def _is_pinned(msg: dict) -> bool:
        content = msg.get("content", "")
        if isinstance(content, str):
            content_trimmed = content.strip()
            if content_trimmed.startswith("[") or content_trimmed.startswith("{"):
                try:
                    import json as _json
                    content = _json.loads(content_trimmed)
                except Exception:
                    try:
                        import ast as _ast
                        content = _ast.literal_eval(content_trimmed)
                    except Exception:
                        pass
        if not isinstance(content, list):
            return False
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use" and item.get("name") in _PINNED_TOOLS:
                return True
            if item.get("tool_name") in _PINNED_TOOLS:
                return True
        return False

    # Guard de deduplicação de tool calls — evita loop infinito quando modelo ignora anti-repetição
    _tool_call_history: set = set()
    # Prepopula do histórico (messages) para manter estado entre as chamadas do frontend
    for _m in messages:
        _mc = _m.get("content", "")
        if isinstance(_mc, list):
            for _b in _mc:
                if isinstance(_b, dict) and _b.get("type") == "tool_use":
                    _tn = _b.get("name", "")
                    _ta = _b.get("input") or {}
                    if _tn in {"pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"}:
                        _tool_call_history.add(_tn)
                    elif _tn in {"whatsapp_get_messages", "email_get_contact_history"}:
                        _cid = (_ta.get("contact") or _ta.get("contact_name") or _ta.get("org_name") or "").lower().strip()
                        _tool_call_history.add(f"{_tn}:{_cid}")
                        
    # Nome do contato dono da tarefa (person_name da atividade pendente do Pipedrive).
    _session_task_person: str | None = None
    _cached_final_response: str | None = None
    
    for iteration in range(start_iteration, _max_iters):
        # Sai assim que suggest_next_actions foi chamado
        if _suggest_actions_done(messages):
            if _cached_final_response:
                yield _emit({"type": "final", "response": _cached_final_response})
            return

        # ... (pacing logic) ...
        # Corte de memória inteligente...
        if len(messages) > 40:
            pinned = [m for m in messages[1:-20] if _is_pinned(m)]
            recent = messages[-20:]
            pinned_set = set(id(m) for m in pinned)
            messages = [messages[0]] + pinned + [m for m in recent if id(m) not in pinned_set]

        # Atualiza sinais de detecção a partir do histórico mais recente
        _has_local_decision_maker = False
        _persons_with_wa = []
        _persons_with_email = []
        
        # Usa apenas o resultado MAIS RECENTE de pipedrive_get_persons
        _last_persons_msg = None
        for _m in messages:
            _mc = _m.get("content", "")
            if not isinstance(_mc, list): continue
            for _b in _mc:
                if isinstance(_b, dict) and _b.get("type") == "tool_result" and _b.get("tool_name") == "pipedrive_get_persons":
                    _last_persons_msg = _b

        if _last_persons_msg:
            import json as _json_loop
            import re as _re_loop
            _raw_c = _last_persons_msg.get("content", "")
            try:
                _text = _json_loop.loads(_raw_c) if isinstance(_raw_c, str) else _raw_c
            except Exception:
                _text = _raw_c
            
            # Detecção de Decisor Local (Sinalizador Estratégico)
            if isinstance(_text, str) and "[ALERTA: DECISOR LOCAL ENCONTRADO]" in _text:
                _has_local_decision_maker = True

            # Extração de contatos com canal
            if isinstance(_text, dict):
                for _p in (_text.get("persons") or []):
                    _pn = _p.get("name", "")
                    if _pn:
                        if _p.get("phone"): _persons_with_wa.append((_pn, _p.get("phone")))
                        if _p.get("email"): _persons_with_email.append((_pn, _p.get("email")))
            elif isinstance(_text, str):
                # Formato: "• [ID:NNN] Nome (telefone_ou_email) - Cargo: ... [Origem]"
                for _line in _text.split('\n'):
                    _m2 = _re_loop.search(r'•\s*\[ID:[^\]]+\]\s*([^(\n]+?)\s*\(([^)]+)\)', _line)
                    if _m2:
                        _pn = _m2.group(1).strip()
                        _pc = _m2.group(2).strip()
                        if _pn and _pc and _pc != "sem contato":
                            if "@" in _pc: _persons_with_email.append((_pn, _pc))
                            else: _persons_with_wa.append((_pn, _pc))

        # System prompt por fase...
        from modules.ai.service.context.business_context_service import BusinessContextService
        from modules.agent.service.prompts import render_prompt
        
        ctx = await BusinessContextService.get_tenant_context()

        if active_skill:
            if _is_direct_directive:
                system = render_prompt(SYSTEM_PROMPT_TASK_DIRECTIVE, ctx)
                skill_inst = render_prompt(active_skill.get_instructions({'org_id': org_id, 'process_id': process_id}), ctx)
                system += f"\n\n[CONTEXTO DE BACKGROUND DA TAREFA ATUAL]:\nO usuário pediu uma ação pontual (diretiva livre) dentro desta tarefa. As regras da diretiva livre (Fim da burocracia) são SOBERANAS e você DEVE cumpri-las e pular quaisquer investigações ou Fases obrigatórias ditadas no texto abaixo. Eis o background apenas para que você tenha contexto das regras de negócio gerais:\n\n{skill_inst}"
            else:
                system = render_prompt(active_skill.get_instructions({"org_id": org_id, "process_id": process_id}), ctx)
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

        # Regra global: sempre responder em português
        system += "\n\n[REGRA GLOBAL DE IDIOMA]: Você deve OBRIGATORIAMENTE se comunicar com o usuário em PORTUGUÊS (PT-BR) em todas as suas respostas, resumos e sugestões. Nunca responda em inglês."

        # ── Tool calling ──────────────────────────────────────────────────────
        try:
            import asyncio as _asyncio

            # Se houver skill ativo, filtramos as ferramentas
            # para as permitidas pelo skill.
            _current_tools = tools
            if active_skill and not _is_direct_directive:
                _current_tools = [t for t in tools if t.get("name") in active_skill.allowed_tools]
                log.info("agent.intent.active_skill.tools_filtered", count=len(_current_tools))

            _raw_log(process_id, "llm_request", {"system": system, "messages": messages, "iteration": iteration})
            _pending_events: list = []
            # Roda _call_with_tools como task em background para poder emitir
            # eventos (rate_wait, model_active) em tempo real enquanto ele aguarda.
            # Para tarefas CRM: força chamada de ferramenta enquanto Pipedrive core incompleto,
            # restringindo ao próximo tool core pendente para garantir a ordem correta.
            _force = False
            _allowed_core: list | None = None
            if _is_direct_directive:
                pass # Não força ferramentas core em diretivas diretas, obedece o usuário imediatamente
            elif active_skill:
                _CORE = set(active_skill.core_tools)
                _CORE_ORDER = list(active_skill.core_tools)
                _done = _get_tools_called(messages, target_tools=_CORE)
                
                _missing_core = _CORE - _done
                if _missing_core:
                    _force = True
                    _next_core = next((t for t in _CORE_ORDER if t not in _done), None)
                    if _next_core:
                        _allowed_core = [_next_core]
            elif _is_task_action:
                if _is_find_decisor_task:
                    _CORE = {"deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects"}
                    _CORE_ORDER = ["deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects"]
                else:
                    _CORE = {"deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals", "pipedrive_get_activities"}
                    _CORE_ORDER = ["deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals", "pipedrive_get_activities"]
                
                _done = _get_tools_called(messages, target_tools=_CORE)
                
                _missing_core = _CORE - _done
                if _missing_core:
                    _force = True
                    # Restringe ao próximo tool core em ordem
                    _next_core = next((t for t in _CORE_ORDER if t not in _done), None)
                    if _next_core:
                        _allowed_core = [_next_core]
                else:
                    # Fase 1 concluída. Se ainda não buscou histórico, permite usar o BATCH SEARCH
                    _comm_tools = {"whatsapp_get_messages", "email_get_contact_history", "batch_communication_search"}
                    _comm_done = _get_tools_called(messages, target_tools=_comm_tools)
                    if not _comm_done:
                        _force = True
                        _allowed_core = ["batch_communication_search"]

            # Detector de loop: se whatsapp_get_messages ou email_get_contact_history
            # foram chamados 3+ vezes, injeta instrução para o modelo avançar para ação.
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

            _llm_task = _asyncio.create_task(_call_with_tools(
                system, messages, _current_tools,
                preferred=preferred, strict_mode=strict_mode,
                pending_events=_pending_events,
                force_tool_call=_force,
                allowed_tool_names=_allowed_core,
            ))
            while not _llm_task.done():
                while _pending_events:
                    yield _emit(_pending_events.pop(0))
                await _asyncio.sleep(0.05)
            response = await _llm_task  # propaga exceção se houver

            # Se deu certo, atualiza o preferred de forma "sticky" para manter o modelo que funcionou!
            if response and not strict_mode:
                succ_model = response.get("_successful_model")
                if succ_model:
                    preferred = succ_model
                    log.info("agent.llm.preferred.updated", preferred_model=preferred, iteration=iteration)

            # Esvazia quaisquer eventos restantes após conclusão
            for _ev in _pending_events:
                yield _emit(_ev)
            _pending_events.clear()
            _raw_log(process_id, "llm_response", {"response": response})
        except Exception as e:
            if _collected_tool_summaries:
                partial = "\n".join(f"• {s}" for s in _collected_tool_summaries)
                yield _emit({
                    "type": "final",
                    "response": (
                        f"⚠️ Os serviços de IA estão temporariamente sobrecarregados. "
                        f"Aqui estão os dados coletados até agora:\n\n{partial}\n\n"
                        f"Tente novamente em alguns minutos para a análise completa."
                    ),
                })
            else:
                _raw_log(process_id, "agent_error", {"content": f"Erro ao chamar LLM: {e}"})
                yield _emit({"type": "error", "content": f"Erro ao chamar LLM: {e}"})
            return

        content = response.get("content", [])
        stop_reason = response.get("stop_reason", "end_turn")

        text_blocks = [b for b in content if b.get("type") == "text"]
        tool_use_blocks = [b for b in content if b.get("type") == "tool_use"]

        # ── Fallback: alguns modelos menores (Cerebras/Groq 8B) retornam tool calls
        # como texto JSON — seja como resposta exclusiva (sem tool_use_blocks) ou
        # embutido no texto junto com um tool call estruturado real (resposta dupla).
        # Em ambos os casos: detecta, converte e limpa o JSON do texto da UI.
        if text_blocks:
            def _extract_json_objects(text: str) -> list[str]:
                """Extrai objetos JSON balanceados (suporta aninhamento)."""
                results, depth, start = [], 0, -1
                for i, ch in enumerate(text):
                    if ch == '{':
                        if depth == 0:
                            start = i
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0 and start >= 0:
                            results.append(text[start:i + 1])
                            start = -1
                return results

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
                        # Sem tool_use estruturado: converte o JSON em tool_use real
                        if not tool_use_blocks:
                            tool_use_blocks.append({
                                "type": "tool_use",
                                "id": f"tc_fallback_{uuid.uuid4().hex[:8]}",
                                "name": _tool_name,
                                "input": _tool_args,
                            })
                            stop_reason = "tool_use"
                        # Com ou sem tool_use: remove o JSON do texto para não poluir a UI
                        text_blocks = [
                            {**b, "text": b.get("text", "").replace(_jc, "").strip()}
                            for b in text_blocks
                        ]
                        text_blocks = [b for b in text_blocks if b.get("text")]
                        # Reconstrói content para que o histórico reflita o tool_use real.
                        # Sem isso, _build_phase_status não rastreia whatsapp_searched/email_searched
                        # a partir dos args do assistente — a fase fica em loop infinito.
                        content = text_blocks + tool_use_blocks
                        break
                except Exception:
                    pass

        # ── Thinking: gerado DEPOIS de saber qual ferramenta será chamada ────
        # Prioridade: texto nativo completo > auxiliar completo > nada (sem fallback seco).
        # O label da ferramenta já é mostrado pelo tool_call event — não duplicar.
        if tool_use_blocks:
            first_tool = tool_use_blocks[0]
            native_text = " ".join(b.get("text", "").strip() for b in text_blocks).strip()
            native_is_complete = bool(native_text and native_text[-1] in ".!?")

            if native_is_complete and len(native_text) > 40:
                # Modelo principal (Claude/Gemini) gerou raciocínio genuíno
                yield _emit({"type": "thinking", "content": native_text})
            else:
                # Modelo não narrou (Groq) — tenta auxiliar de qualidade
                # skip_groq=True evita dobrar quota quando main também é Groq,
                # mas agora sem injection o risco de comportamento errado é zero,
                # então só skipamos quando há alternativa disponível.
                from core.config import settings as _s
                _groq_models = set(_s.ai_groq_models_list or [])
                _cerebras_models = set(_s.ai_cerebras_models_list or [])
                
                _main_is_groq = (
                    not preferred
                    or (preferred or "").lower() == "groq"
                    or preferred in _groq_models
                )
                _main_is_cerebras = (
                    (preferred or "").lower() == "cerebras"
                    or preferred in _cerebras_models
                )
                
                # Só pula Groq se Gemini ou Cerebras estiverem disponíveis
                _has_alt_for_groq = bool(
                    (_s.GEMINI_API_KEY and _s.ai_gemini_models_list)
                    or (_s.CEREBRAS_API_KEY and _s.ai_cerebras_models_list)
                )
                # Só pula Cerebras se Gemini ou Groq estiverem disponíveis
                _has_alt_for_cerebras = bool(
                    (_s.GEMINI_API_KEY and _s.ai_gemini_models_list)
                    or (_s.GROQ_API_KEY and _s.ai_groq_models_list)
                )
                
                _tn = first_tool.get("name", "")
                _ta = first_tool.get("input") or {}

                # Template para todas as ferramentas — evita chamada LLM extra (5-15s por tool).
                # O modelo principal já gera texto quando tem contexto real; aqui só cobrimos
                # o caso em que ele chamou a ferramenta sem texto (ex: Gemini com mode=ANY).
                if _tn != "suggest_next_actions":
                    yield _emit({"type": "thinking", "content": _get_thinking_fallback(_tn, _ta)})

        # Resposta final (sem tool calls)
        if stop_reason in ("end_turn", "stop") or not tool_use_blocks:
            response_text = " ".join(b.get("text", "") for b in text_blocks).strip()

            if "parada antecipada" in response_text.lower():
                # O agente detectou uma quebra de fluxo via Pipeline (ex: falta de telefone)
                # Encerra o loop instantaneamente e retorna a mensagem.
                yield _emit({"type": "final", "response": response_text})
                return

            # Modo execução direta: verificar se a Fase 1 foi concluída antes de encerrar
            elif direct_action and _is_task_action:
                _CTX_TOOLS = {
                    "deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals",
                    "pipedrive_get_activities", "whatsapp_get_messages", "email_get_contact_history",
                }
                # Detecta quais ferramentas de contexto já foram chamadas no histórico
                _called_ctx: set[str] = set()
                for _m in messages + [{"role": "assistant", "content": content}]:
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict):
                                if _b.get("type") == "tool_use" and _b.get("name") in _CTX_TOOLS:
                                    _called_ctx.add(_b["name"])
                                elif _b.get("type") == "tool_result" and _b.get("tool_name") in _CTX_TOOLS:
                                    _called_ctx.add(_b["tool_name"])

                if active_skill and hasattr(active_skill, "core_tools"):
                    _CORE_CTX = set(active_skill.core_tools)
                    _CTX_ORDER = list(active_skill.core_tools)
                    for t in ["whatsapp_get_messages", "email_get_contact_history"]:
                        if t not in _CORE_CTX:
                            _CTX_ORDER.append(t)
                else:
                    _CORE_CTX = {"deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals", "pipedrive_get_activities"}
                    _CTX_ORDER = [
                        "deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals",
                        "pipedrive_get_activities", "whatsapp_get_messages", "email_get_contact_history",
                    ]
                _missing_core = _CORE_CTX - _called_ctx
                _next_tool = next((t for t in _CTX_ORDER if t not in _called_ctx), None)

                if _missing_core and _next_tool and iteration < _max_iters - 2:
                    # Fase 1 incompleta — injeta continuação com a ferramenta EXATA a chamar
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"A investigação não foi concluída. "
                            f"CHAME AGORA: {_next_tool}\n"
                            f"Ferramentas ainda pendentes: {', '.join(t for t in _CTX_ORDER if t not in _called_ctx)}\n"
                            f"Execute {_next_tool} imediatamente. Não gere texto — apenas chame a ferramenta."
                        ),
                    })
                    continue

                _ai_response_text = " ".join(b.get("text", "") for b in text_blocks).lower()

                # Detecta se já gerou rascunho de mensagem
                _has_draft = False
                for _m in messages + [{"role": "assistant", "content": content}]:
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict) and (_b.get("tool_name") == "generate_sales_message" or (_b.get("type") == "tool_use" and _b.get("name") == "generate_sales_message")):
                                _has_draft = True
                                break
                    if _has_draft: break

                # ── Interceptor: contatos com canal ainda não investigados ─────────────
                # Para tarefas de follow-up/comunicação, garante que TODOS os contatos
                # ── Interceptor: Email obrigatório para contato-tarefa ──────────────────────
                # Para tarefas com contato específico (_session_task_person), sempre busca
                # TAMBÉM o email após WhatsApp — independente do resultado do WhatsApp.
                if _session_task_person and _is_task_action and not _has_draft and iteration < _max_iters - 2:
                    _tpn_first = _session_task_person.split()[0].lower()
                    _task_wa_done = False
                    _task_email_done = False
                    for _hm in messages + [{"role": "assistant", "content": content}]:
                        _hc = _hm.get("content", "")
                        if not isinstance(_hc, list): continue
                        for _hb in _hc:
                            if not isinstance(_hb, dict) or _hb.get("type") != "tool_use": continue
                            _inp = _hb.get("input") or {}
                            if _hb.get("name") == "whatsapp_get_messages":
                                if _tpn_first in (_inp.get("contact") or "").lower():
                                    _task_wa_done = True
                            elif _hb.get("name") == "email_get_contact_history":
                                if (_tpn_first in (_inp.get("contact_name") or "").lower()
                                        or _tpn_first in (_inp.get("org_name") or "").lower()):
                                    _task_email_done = True
                    if _task_wa_done and not _task_email_done:
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"Você já verificou o WhatsApp de {_session_task_person}. "
                                f"OBRIGATÓRIO: verifique também o e-mail antes de finalizar — "
                                f"chame email_get_contact_history com contact_name='{_session_task_person}' "
                                f"para ter o histórico completo de comunicações."
                            ),
                        })
                        continue

                # com canal registrado (WhatsApp ou telefone/email) sejam buscados antes
                # de o agente finalizar. Impede que o modelo conclua "sem histórico" depois
                # de buscar apenas o contato principal.
                # Se já gerou rascunho, PULA estas investigações forçadas para economizar turnos.
                if not _has_draft and iteration < _max_iters - 2:
                    # PRIORIDADE E FAST-TRACK: Se é uma tarefa para uma pessoa específica e já temos o contato dela, 
                    # não forçamos a busca de outros contatos para economizar turnos.
                    _skip_others = False
                    if _session_task_person and _is_task_action:
                        _tpn_f = _session_task_person.lower().split()[0]
                        
                        # Verifica se já buscamos o histórico da pessoa alvo
                        _target_searched = False
                        for _m in messages + [{"role": "assistant", "content": content}]:
                            _mc = _m.get("content", "")
                            if not isinstance(_mc, list): continue
                            for _b in _mc:
                                if isinstance(_b, dict) and _b.get("type") == "tool_use":
                                    _tn_s = _b.get("name", "")
                                    _ta_s = _b.get("input") or {}
                                    if _tn_s == "whatsapp_get_messages" and _tpn_f in str(_ta_s.get("contact", "")).lower():
                                        _target_searched = True
                                    if _tn_s == "email_get_contact_history" and (_tpn_f in str(_ta_s.get("contact_name", "")).lower() or _tpn_f in str(_ta_s.get("org_name", "")).lower()):
                                        _target_searched = True
                                    if _tn_s == "batch_communication_search":
                                        _c_str = str(_ta_s.get("contacts", ""))
                                        _o_str = str(_ta_s.get("org_name", ""))
                                        if _tpn_f in _c_str.lower() or _tpn_f in _o_str.lower():
                                            _target_searched = True
                        
                        if _target_searched:
                            _skip_others = True # Já investigou o alvo, não precisa investigar o resto da empresa agora
                    
                    if not _skip_others:
                        # Prioriza o contato dono da tarefa — usa _session_task_person capturado
                        # durante a execução de pipedrive_get_activities (dado raw, antes da sanitização).
                        _tpn_lower = ""
                        if _session_task_person:
                            _tpn_lower = _session_task_person.lower()
                        # WA
                        _task_entry_wa = None
                        for p in _persons_with_wa:
                            if _tpn_lower and (_tpn_lower in p[0].lower() or p[0].lower().split()[0] in _tpn_lower):
                                _task_entry_wa = p
                                break
                        if _task_entry_wa and _persons_with_wa.index(_task_entry_wa) != 0:
                            _persons_with_wa.remove(_task_entry_wa)
                            _persons_with_wa.insert(0, _task_entry_wa)
                        
                        # Email
                        _task_entry_email = None
                        for p in _persons_with_email:
                            if _tpn_lower and (_tpn_lower in p[0].lower() or p[0].lower().split()[0] in _tpn_lower):
                                _task_entry_email = p
                                break
                        if _task_entry_email and _persons_with_email.index(_task_entry_email) != 0:
                            _persons_with_email.remove(_task_entry_email)
                            _persons_with_email.insert(0, _task_entry_email)

                    # Descobre quais contatos já foram buscados via whatsapp ou email
                    _already_searched: set[str] = set()
                    for _m in messages + [{"role": "assistant", "content": content}]:
                        _mc = _m.get("content", "")
                        if not isinstance(_mc, list): continue
                        for _b in _mc:
                            if not isinstance(_b, dict): continue
                            if _b.get("type") != "tool_use": continue
                            _tn2 = _b.get("name", "")
                            _ta2 = _b.get("input") or {}
                            if _tn2 == "whatsapp_get_messages":
                                _already_searched.add((_ta2.get("contact") or "").lower())
                            elif _tn2 == "email_get_contact_history":
                                _cn = (_ta2.get("contact_name") or _ta2.get("org_name") or "").lower()
                                if _cn: _already_searched.add(_cn)
                            elif _tn2 == "batch_communication_search":
                                _contacts = _ta2.get("contacts") or []
                                for _c in _contacts:
                                    if _c.get("name"): _already_searched.add(_c["name"].lower())
                                _on = (_ta2.get("org_name") or "").lower()
                                if _on: _already_searched.add(_on)

                    # Nome da organização para busca por empresa
                    _org_name_for_search = ""
                    for _m in messages:
                        _mc = _m.get("content", "")
                        if not isinstance(_mc, list): continue
                        for _b in _mc:
                            if not isinstance(_b, dict): continue
                            if _b.get("type") == "tool_result" and _b.get("tool_name") == "pipedrive_get_org":
                                try:
                                    _od = json.loads(_b.get("content", "{}"))
                                    _org_name_for_search = (_od.get("org") or {}).get("name") or _od.get("name") or ""
                                except Exception:
                                    pass

                    # Encontra o próximo contato WA e Email ainda não buscados
                    _next_unsearched_wa = None
                    for _pname, _pphone in _persons_with_wa:
                        if _pname.lower() not in _already_searched and _pname.split()[0].lower() not in _already_searched:
                            _next_unsearched_wa = (_pname, _pphone)
                            break
                    
                    _next_unsearched_email = None
                    for _pname, _pemail in _persons_with_email:
                        if _pname.lower() not in _already_searched and _pname.split()[0].lower() not in _already_searched:
                            _next_unsearched_email = (_pname, _pemail)
                            break

                    _ai_response_text = " ".join(b.get("text", "") for b in text_blocks).lower()
                    
                    # Detecta se já gerou rascunho de mensagem ou plano de voo
                    _has_draft = False
                    _has_flight_plan = False
                    for _m in messages + [{"role": "assistant", "content": content}]:
                        _mc = _m.get("content", "")
                        if isinstance(_mc, list):
                            for _b in _mc:
                                if isinstance(_b, dict):
                                    if _b.get("tool_name") == "generate_sales_message" or (_b.get("type") == "tool_use" and _b.get("name") == "generate_sales_message"):
                                        _has_draft = True
                                    if _b.get("tool_name") == "prepare_live_coaching_session" or (_b.get("type") == "tool_use" and _b.get("name") == "prepare_live_coaching_session"):
                                        _has_flight_plan = True
                        if _has_draft and _has_flight_plan: break

                    _found_decision_maker = _has_draft or _has_flight_plan or ("decisor" in _ai_response_text and any(word in _ai_response_text for word in ["encontrado", "confirmado", "identificado"]))

                    # Se já achou decisor ou gerou rascunho, ignora esgotamento forçado.
                    _has_useful_history = any(
                        True
                        for _hm in messages + [{"role": "assistant", "content": content}]
                        for _hb in (_hm.get("content") if isinstance(_hm.get("content"), list) else [])
                        if isinstance(_hb, dict)
                        and _hb.get("type") == "tool_result"
                        and _hb.get("tool_name") in ("whatsapp_get_messages", "email_get_contact_history")
                        and "desconectado" not in str(_hb.get("content", "")).lower()
                        and "inacess" not in str(_hb.get("content", "")).lower()
                        and "não encontrado" not in str(_hb.get("content", "")).lower()
                    )

                    if not _found_decision_maker and not _has_draft and not _has_flight_plan:
                        if (_is_task_action or _is_call_task) and _already_searched and _has_useful_history:
                            # Já encontrou histórico útil — não força busca adicional
                            pass
                        elif _next_unsearched_wa:
                            _first_name = _next_unsearched_wa[0].split()[0]
                            _phone_val = _next_unsearched_wa[1]
                            _phone_param = f", phone='{_phone_val}'" if "@" not in _phone_val else ""

                            # Se WhatsApp estiver desconectado ou com falha, força email em vez de outra tentativa
                            _wa_disconnected_now = any(
                                "desconectado" in str(_hb.get("content", "")).lower() or
                                "inacess" in str(_hb.get("content", "")).lower() or
                                "http 5" in str(_hb.get("content", "")).lower() or
                                "sem lid" in str(_hb.get("content", "")).lower() or
                                "sem conversa ativa" in str(_hb.get("content", "")).lower()
                                for _hm in messages + [{"role": "assistant", "content": content}]
                                for _hb in (_hm.get("content") if isinstance(_hm.get("content"), list) else [])
                                if isinstance(_hb, dict) and _hb.get("type") == "tool_result"
                                and _hb.get("tool_name") == "whatsapp_get_messages"
                            )
                            if _wa_disconnected_now:
                                # Tenta buscar o e-mail deste contato ou do próximo
                                _next_for_email = _next_unsearched_wa[0]
                                _org_label = _org_name_for_search or "a empresa"
                                messages.append({"role": "assistant", "content": content})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        f"WhatsApp está desconectado. OBRIGATÓRIO: busque o histórico de e-mail como alternativa.\n"
                                        f"Chame email_get_contact_history com contact_name='{_next_for_email}', org_name='{_org_label}' agora.\n"
                                        f"Só conclua 'sem histórico' após verificar e-mail também."
                                    ),
                                })
                            else:
                                messages.append({"role": "assistant", "content": content})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        f"ATENÇÃO: Você não esgotou todos os contatos com WhatsApp antes de finalizar.\n"
                                        f"OBRIGATÓRIO: busque agora whatsapp_get_messages com contact='{_first_name}'{_phone_param} "
                                        f"antes de redigir qualquer mensagem. "
                                        f"Só conclua 'sem histórico' após verificar TODOS os contatos com canal."
                                    ),
                                })
                            continue
                        elif _next_unsearched_email:
                            _next_for_email = _next_unsearched_email[0]
                            _org_label = _org_name_for_search or "a empresa"
                            messages.append({"role": "assistant", "content": content})
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"OBRIGATÓRIO: busque o histórico de e-mail para ter o histórico completo.\n"
                                    f"Chame email_get_contact_history com contact_name='{_next_for_email}', org_name='{_org_label}' agora.\n"
                                    f"Só conclua 'sem histórico' após verificar e-mail também."
                                ),
                            })
                            continue

                    # ── Interceptor: sem canal → forçar open_hierarchy_drawer (anti-alucinação) ──
                    # O LLM tende a escrever "abri o mapeador" em texto em vez de chamar a tool.
                    # Condição: investigação concluída + zero contatos com canal + tarefa é encontrar decisor.
                    # _is_find_decisor_task já foi definido no início do loop
                    _hierarchy_already_called = any(
                        isinstance(_b, dict) and (
                            (_b.get("type") == "tool_use" and _b.get("name") == "open_hierarchy_drawer") or
                            (_b.get("type") == "tool_result" and _b.get("tool_name") == "open_hierarchy_drawer")
                        )
                        for _m in messages + [{"role": "assistant", "content": content}]
                        for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
                    )
                    if (
                        _is_find_decisor_task
                        and not _persons_with_wa
                        and not _persons_with_email
                        and not _missing_core
                        and not _hierarchy_already_called
                        and not _has_local_decision_maker
                    ):
                        _org_hint = _org_name_for_search or ""
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"AÇÃO OBRIGATÓRIA: Investigação concluída — nenhum contato com canal válido encontrado.\n"
                                f"NÃO descreva esta ação em texto — CHAME A FERRAMENTA DIRETAMENTE AGORA.\n"
                                f"Chame: open_hierarchy_drawer"
                                + (f" com org_name='{_org_hint}'" if _org_hint else "")
                                + f"\nProibido escrever 'abri o mapeador' sem chamar a tool."
                            ),
                        })
                        continue

                    # ── Interceptor: Decisores locais exigem evaluation ──
                    if _has_local_decision_maker:
                        _evaluation_called = any(
                            isinstance(_b, dict) and (
                                (_b.get("type") == "tool_use" and _b.get("name") == "evaluate_prospects") or
                                (_b.get("type") == "tool_result" and _b.get("tool_name") == "evaluate_prospects")
                            )
                            for _m in messages + [{"role": "assistant", "content": content}]
                            for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
                        )
                        
                        if not _evaluation_called:
                            messages.append({"role": "assistant", "content": content})
                            messages.append({
                                "role": "user",
                                "content": "AÇÃO OBRIGATÓRIA: Decisores ICP encontrados. CHAME AGORA `evaluate_prospects` para realizar o ranking inteligente."
                            })
                            continue

                # ── Interceptor: Rascunho gerado mas NÃO enviado (REGRA DE OURO) ─────────────
                if _is_task_action and iteration < _max_iters - 2:
                    _has_draft_now = False
                    _has_sent_now = False
                    _SEND_TOOLS = {"whatsapp_send_message", "email_send", "email_reply", "pipedrive_update_task", "pipedrive_create_task"}
                    
                    for _m in messages + [{"role": "assistant", "content": content}]:
                        _mc = _m.get("content", "")
                        if isinstance(_mc, list):
                            for _b in _mc:
                                if not isinstance(_b, dict): continue
                                _tn_check = _b.get("tool_name") or _b.get("name")
                                if _tn_check == "generate_sales_message":
                                    _has_draft_now = True
                                elif _tn_check in _SEND_TOOLS:
                                    _has_sent_now = True
                    
                    if _has_draft_now and not _has_sent_now:
                        # Recupera attachment_name do rascunho se disponível
                        _att_name = ""
                        for _m in messages + [{"role": "assistant", "content": content}]:
                            _mc = _m.get("content", "")
                            if isinstance(_mc, list):
                                for _b in _mc:
                                    if isinstance(_b, dict) and _b.get("tool_name") == "generate_sales_message":
                                        try:
                                            _rd = json.loads(_b.get("content", "{}"))
                                            _att_name = _rd.get("attachment_name") or ""
                                        except: pass

                        # Força o envio do rascunho
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                "REGRA DE OURO: Você gerou um rascunho de mensagem mas não chamou a ferramenta de envio para aprovação.\n"
                                "O 'Sucesso' da sua tarefa é fazer o card de aprovação aparecer para o João Luccas.\n"
                                f"CHAME AGORA: whatsapp_send_message (ou email_send/email_reply) com o texto do rascunho"
                                + (f" e attachment_name='{_att_name}'" if _att_name else "") + ".\n"
                                "É PROIBIDO terminar o turno apenas com texto quando há um rascunho pronto."
                            ),
                        })
                        continue

                    # ── Interceptor: Investigação concluída mas rascunho NÃO gerado ──────────
                    _COMM_KEYWORDS = ["enviar", "email", "whatsapp", "mensagem", "mandar", "falar", "apresentação", "proposta", "follow"]
                    _is_comm_task = any(k in _first_msg_content.lower() for k in _COMM_KEYWORDS)
                    _is_call_task = any(k in _first_msg_content.lower() for k in ["ligação", "ligar", "telefonar", "telefone"])

                    # ── Interceptor: LIGAÇÃO - contato sem telefone → forçar find_company_contact ──
                    if _is_call_task and not _missing_core and iteration < _max_iters - 2:
                        _persons_called = any(
                            isinstance(_b, dict) and (
                                (_b.get("type") == "tool_use" and _b.get("name") == "pipedrive_get_persons") or
                                (_b.get("type") == "tool_result" and _b.get("tool_name") == "pipedrive_get_persons")
                            )
                            for _m in messages + [{"role": "assistant", "content": content}]
                            for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
                        )
                        _find_contact_called = any(
                            isinstance(_b, dict) and (
                                (_b.get("type") == "tool_use" and _b.get("name") == "find_company_contact") or
                                (_b.get("type") == "tool_result" and _b.get("tool_name") == "find_company_contact")
                            )
                            for _m in messages + [{"role": "assistant", "content": content}]
                            for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
                        )
                        _coaching_called = any(
                            isinstance(_b, dict) and (
                                (_b.get("type") == "tool_use" and _b.get("name") == "prepare_live_coaching_session") or
                                (_b.get("type") == "tool_result" and _b.get("tool_name") == "prepare_live_coaching_session")
                            )
                            for _m in messages + [{"role": "assistant", "content": content}]
                            for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
                        )

                        # 🚀 FAST-TRACK: Se já temos o telefone, FORÇAMOS o coaching imediatamente
                        _has_phone = len(_persons_with_wa) > 0 or _find_contact_called

                        # 🌉 GOLDEN BRIDGE: Se já temos o flight_plan, FORÇAMOS a abertura da LigacaoView
                        # Isso evita que o modelo entre em loop infinito tentando achar telefone após o plano pronto.
                        if _has_phone and _coaching_called:
                            # Extrai o flight_plan do histórico recente
                            _fp_to_pass = {}
                            for _m in reversed(messages + [{"role": "assistant", "content": content}]):
                                _mc = _m.get("content", "")
                                if not isinstance(_mc, list): continue
                                for _b in _mc:
                                    if isinstance(_b, dict) and _b.get("type") == "tool_result" and _b.get("tool_name") == "prepare_live_coaching_session":
                                        _res_data = _b.get("content", {})
                                        try:
                                            if isinstance(_res_data, str): _res_data = json.loads(_res_data)
                                            _fp_to_pass = _res_data.get("flight_plan") or _res_data
                                        except: pass
                                        break
                                if _fp_to_pass: break

                            _extracted_phone = ""
                            for _m in messages + [{"role": "assistant", "content": content}]:
                                _mc = _m.get("content", "")
                                if isinstance(_mc, list):
                                    for _b in _mc:
                                        if isinstance(_b, dict) and _b.get("type") == "tool_result" and _b.get("tool_name") == "find_company_contact":
                                            try:
                                                _res_str = str(_b.get("content", ""))
                                                if _res_str.strip().startswith(("{", "[")):
                                                    _res_data = json.loads(_res_str)
                                                    _phones = _res_data.get("phones") or []
                                                    if _phones and isinstance(_phones, list) and _phones[0].get("value"):
                                                        _extracted_phone = str(_phones[0]["value"])
                                                if not _extracted_phone:
                                                    import re
                                                    _m_phone = re.search(r'Telefones\s*\(Receita\s+Federal\):\s*(\d+)', _res_str)
                                                    if _m_phone:
                                                        _extracted_phone = _m_phone.group(1)
                                            except: pass

                            if _fp_to_pass:
                                _p_name = _session_task_person or (_persons_with_wa[0][0] if _persons_with_wa else "o contato")
                                _p_phone = _persons_with_wa[0][1] if _persons_with_wa else (_extracted_phone or "3537311491")

                                messages.append({"role": "assistant", "content": content})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        f"SINAL DE EXECUÇÃO: O Plano de Voo para '{_p_name}' já está pronto. "
                                        f"OBRIGATÓRIO: Chame AGORA a ferramenta `open_ligacao_view` com:\n"
                                        f"- contact_name: '{_p_name}'\n"
                                        f"- phone: '{_p_phone}'\n"
                                        f"- flight_plan: [REPÀSSE O JSON DO PLANO AQUI]\n"
                                        "NÃO faça mais nenhuma pesquisa ou dossiê."
                                    ),
                                })
                                continue

                        if _has_phone and not _coaching_called:
                            _p_name = _persons_with_wa[0][0] if _persons_with_wa else (_session_task_person or "o contato")
                            _p_phone = _persons_with_wa[0][1] if _persons_with_wa else (_extracted_phone or "3537311491")

                            messages.append({"role": "assistant", "content": content})
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"SINAL DE EXECUÇÃO: O telefone de '{_p_name}' já foi identificado ({_p_phone}). "
                                    "PARE qualquer investigação adicional (E-mail, OSINT, Dossiê). "
                                    "OBRIGATÓRIO: Chame `prepare_live_coaching_session` AGORA para gerar o roteiro e abrir a ligação."
                                ),
                            })
                            continue

                        # Se buscou contatos e não encontrou telefone E ainda não tentou find_company_contact
                        _contact_has_no_phone = _persons_called and not _persons_with_wa
                        if _contact_has_no_phone and not _find_contact_called:
                            _org_hint = _org_name_for_search or ""
                            messages.append({"role": "assistant", "content": content})
                            messages.append({
                                "role": "user",
                                "content": (
                                    f"O contato não possui telefone registrado no CRM. "
                                    f"OBRIGATÓRIO: Chame AGORA `find_company_contact` com org_name='{_org_hint}' para buscar o telefone na Receita Federal e na Web. "
                                    f"NÃO encerre a tarefa antes de tentar essa busca."
                                ),
                            })
                            continue

                    if _is_comm_task and not _is_call_task and not _missing_core and not _has_draft_now and not _has_sent_now:
                         messages.append({"role": "assistant", "content": content})
                         messages.append({
                             "role": "user",
                             "content": (
                                 "Você concluiu a fase de investigação de dados e histórico. "
                                 "OBRIGATÓRIO: Use `generate_sales_message` agora para criar o rascunho da comunicação "
                                 "baseado em tudo que você descobriu. Não encerre apenas com o resumo ou prometendo enviar depois."
                             ),
                         })
                         continue


                    # ── Interceptor: Histórico encontrado mas rascunho NÃO gerado (OBRIGATÓRIO PARA FOLLOW-UP) ──
                    if not _has_draft_now and not _has_sent_now:
                        _is_followup = any(kw in _first_msg_content.lower() for kw in ["follow-up", "cobrar retorno", "acompanhar", "orçamento"])
                        if _is_followup:
                            _found_history = False
                            # Verifica tanto o histórico quanto os resultados do turno atual
                            for _hm in messages + [{"role": "assistant", "content": content}]:
                                _mc = _m.get("content", "")
                                if not isinstance(_mc, list): continue
                                for _b in _mc:
                                    if not isinstance(_b, dict): continue
                                    if _b.get("type") == "tool_result" and _b.get("tool_name") in ("whatsapp_get_messages", "email_get_contact_history"):
                                        _found_history = True
                            
                            if _found_history:
                                messages.append({"role": "assistant", "content": content})
                                messages.append({
                                    "role": "user",
                                    "content": "Você já encontrou o histórico de comunicações. OBRIGATÓRIO: Use `generate_sales_message` agora para propor a próxima mensagem."
                                })
                                continue

                # ── Interceptor: Anti-questionamento de nome de empresa (Anti-Bottleneck) ──────────────
                _ai_text_full = " ".join(b.get("text", "") for b in text_blocks).lower()
                if "confirmar o nome da empresa" in _ai_text_full or "qual o nome da empresa" in _ai_text_full:
                    # Tenta recuperar o nome da org_name_for_search
                    _org_name_final = ""
                    for _m in messages:
                        _mc = _m.get("content", "")
                        if not isinstance(_mc, list): continue
                        for _b in _mc:
                            if not isinstance(_b, dict): continue
                            if _b.get("type") == "tool_result" and _b.get("tool_name") == "pipedrive_get_org":
                                try:
                                    _od = json.loads(_b.get("content", "{}"))
                                    _org_name_final = (_od.get("org") or {}).get("name") or _od.get("name") or ""
                                except Exception: pass
                    
                    if _org_name_final:
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": f"O nome da empresa é '{_org_name_final}'. Você já tem essa informação no histórico do Pipedrive. NÃO peça confirmação novamente. Prossiga com a tarefa imediatamente usando as ferramentas adequadas."
                        })
                        continue

            # Proteção contra parada prematura em pipelines de ligação
            if "PARADA ANTECIPADA" in response_text and iteration < _max_iters - 2:
                # Verifica se houve tentativa real de busca e se realmente não veio telefone
                _search_attempted = any(
                    isinstance(_b, dict) and (_b.get("name") == "find_company_contact" or _b.get("tool_name") == "find_company_contact")
                    for _m in messages + [{"role": "assistant", "content": content}]
                    for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
                )
                _phone_found_now = False
                for _m in messages + [{"role": "assistant", "content": content}]:
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict) and _b.get("type") == "tool_result" and _b.get("tool_name") == "find_company_contact":
                                _res = str(_b.get("content", ""))
                                if any(char.isdigit() for char in _res): _phone_found_now = True
                
                if _phone_found_now:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": "ERRO: Você disse 'PARADA ANTECIPADA', mas um telefone FOI ENCONTRADO na busca externa. PROSSIGA IMEDIATAMENTE para a etapa 2 (prepare_live_coaching_session) e etapa 3 (open_ligacao_view) conforme as instruções da pipeline."
                    })
                    continue

            # Emite resultado final
            if direct_action and not _is_task_action:
                if not _final_emitted:
                    _raw_log(process_id, "agent_final_response", {"response": response_text})
                    yield _emit({"type": "final", "response": response_text})
                return

            # Interceptor anti-permissão...
            _PERMISSION_PHRASES = [
                "você gostaria", "gostaria de verificar", "gostaria de buscar",
                "deseja continuar", "deseja verificar", "posso verificar",
                "posso buscar", "posso investigar", "quer que eu",
                "para prosseguir", "preciso de mais informações",
                "você prefere", "prefere que eu",
            ]
            _resp_lower = response_text.lower()
            _is_asking_permission = any(p in _resp_lower for p in _PERMISSION_PHRASES)

            if _is_asking_permission and iteration < MAX_ITERATIONS - 2:
                messages.append({"role": "assistant", "content": content})
                
                try:
                    _status = _build_phase_status(messages, query_type=query_type, org_id=org_id)
                    m_action = _re.search(r'(PRÓXIMA FERRAMENTA:[^\n]+)', _status)
                    action_str = m_action.group(1) if m_action else "Consulte o plano de fases para decidir o próximo passo."
                except Exception:
                    _status = "Status desconhecido"
                    action_str = "Continue investigando ou chame a ferramenta final."

                messages.append({
                    "role": "user",
                    "content": (
                        "PROIBIDO pedir permissão. "
                        "Não faça perguntas de confirmação ao usuário durante a investigação.\n\n"
                        f"OBRIGATÓRIO AGORA: {action_str}\n\n"
                        f"Contexto atual:\n{_status}"
                    ),
                })
                continue

            # Extrai dados reais do histórico para sugestões e prompts
            found_org = ""
            found_deal_id = None
            found_activities = []
            found_contacts = []
            for _m in messages:
                _m_content = _m.get("content", "")
                if isinstance(_m_content, list):
                    for _item in _m_content:
                        if isinstance(_item, dict) and _item.get("type") == "tool_result":
                            _t_name = _item.get("tool_name", "")
                            _t_content = str(_item.get("content", ""))
                            try:
                                _t_data = json.loads(_t_content) if _t_content.strip().startswith(("{", "[")) else {}
                            except Exception:
                                _t_data = {}
                            if _t_name in ("pipedrive_get_org", "pipedrive_get_persons"):
                                if _t_name == "pipedrive_get_org":
                                    found_org = _t_data.get("org", {}).get("name") or _t_data.get("name") or found_org
                                _p_list = _t_data.get("persons") or []
                                for _p in _p_list:
                                    _p_name = _p.get("name")
                                    if _p_name:
                                        _p_name_clean = _p_name.strip().lower()
                                        if _p_name_clean not in [c.get("name", "").strip().lower() for c in found_contacts]:
                                            found_contacts.append(_p)
                            elif _t_name == "pipedrive_get_deals":
                                _d_list = _t_data.get("deals") or []
                                for _d in _d_list:
                                    if _d.get("status") == "open":
                                        found_deal_id = _d.get("id") or found_deal_id
                            elif _t_name == "pipedrive_get_activities":
                                _p_list = _t_data.get("pending") or []
                                for _a in _p_list:
                                    _act_id = _a.get("id")
                                    if _act_id and _act_id not in [act.get("id") for act in found_activities]:
                                        found_activities.append({
                                            "id": _act_id,
                                            "subject": _a.get("subject", "Sem assunto"),
                                            "due_date": _a.get("due_date", "sem data")
                                        })

            # Interceptor anti-finalização prematura e injeção de suggest_next_actions
            if iteration < MAX_ITERATIONS - 2:
                try:
                    _msgs_with_current = messages + [{"role": "assistant", "content": content}]
                    _status = _build_phase_status(_msgs_with_current, query_type=query_type, org_id=org_id)
                    # Para queries não-investigativas, o modo universal já controla a completude.
                    # Para investigações, detectamos pela fase no _status.
                    # Detecta se o MODO CONTEXTO está ativo no histórico de mensagens
                    context_mode_active = False
                    for msg in messages:
                        if msg.get("role") == "user" and "[MODO CONTEXTO" in str(msg.get("content", "")):
                            context_mode_active = True
                            break

                    # Determina se a consulta exige investigação de negócio (chat dedicado de empresa org_id > 0)
                    _is_investigation = query_type in ("deal_status", "agent_workflow") or (
                        org_id is not None
                        and org_id > 0
                        and query_type != "pipedrive_tasks"
                        and not context_mode_active
                    )
                    _is_non_investigation = not _is_investigation
                    _is_complete = (
                        _is_non_investigation
                        or "Fase final" in _status
                        or "resposta final" in _status.lower()
                        or "responda à pergunta" in _status.lower()
                        or "apresente os" in _status.lower()
                        or "escreva a resposta final" in _status.lower()
                        or "não chame mais ferramentas" in _status.lower()
                        or "regra de ouro" in str(content).lower()
                        or "parada antecipada" in str(content).lower()
                    )

                    # Se for uma tarefa CRM (_is_task_action), ela só está completa se:
                    # 1. Já gerou um rascunho de mensagem (se for tarefa de comunicação)
                    # 2. Já chamou suggest_next_actions (final absoluto)
                    if _is_task_action:
                        _SEND_TOOLS = {"whatsapp_send_message", "email_send", "email_reply"}
                        _has_sent_global = False
                        _has_draft_global = False
                        
                        # Verifica no histórico de resultados de ferramentas
                        for _m in messages:
                             _mc = _m.get("content", "")
                             if isinstance(_mc, list):
                                 for _b in _mc:
                                     if not isinstance(_b, dict): continue
                                     _tn_check = _b.get("tool_name") or _b.get("name")
                                     if _tn_check == "generate_sales_message":
                                         _has_draft_global = True
                                     if _tn_check in _SEND_TOOLS:
                                         try:
                                             _res = json.loads(_b.get("content", "{}"))
                                             if _res.get("ok"): _has_sent_global = True
                                         except: pass
                        
                        # Verifica se está no turno atual (assistant content)
                        if not _has_sent_global or not _has_draft_global:
                            for _b in content if isinstance(content, list) else []:
                                if isinstance(_b, dict) and _b.get("type") == "tool_use":
                                    _tn_curr = _b.get("name")
                                    if _tn_curr in _SEND_TOOLS: _has_sent_global = True
                                    if _tn_curr == "generate_sales_message": _has_draft_global = True

                        _COMM_KEYWORDS = ["enviar", "email", "whatsapp", "mensagem", "mandar", "falar", "apresentação", "proposta", "follow"]
                        _is_comm_task = any(k in _first_msg_content.lower() for k in _COMM_KEYWORDS)
                        
                        # A tarefa de comunicação está "completa para o loop" se já tem o rascunho.
                        # Isso permite que o assistente pare para mostrar o texto ao usuário.
                        if _is_comm_task and (_has_sent_global or _has_draft_global):
                            _is_complete = True
                        elif _is_comm_task:
                            _is_complete = False # Força a passar pelos interceptores de rascunho/envio

                    if not _is_complete and stop_reason in ("end_turn", "stop") and not tool_use_blocks:
                        # Investigação incompleta — força continuar (só para respostas de texto puro)
                        m_action = _re.search(r'(PRÓXIMA FERRAMENTA:[^\n]+)', _status)
                        action_str = m_action.group(1) if m_action else "Consulte o plano de fases."
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"ERRO: INVESTIGAÇÃO INCOMPLETA. Você tentou finalizar a resposta sem usar a ferramenta obrigatória.\n"
                                f"Para a investigação estar completa, você DEVE executar a próxima etapa.\n\n"
                                f"OBRIGATÓRIO AGORA:\n{action_str}\n\n"
                                f"Contexto:\n{_status}"
                            ),
                        })
                        continue

                    # Investigação completa — verifica se suggest_next_actions já foi chamado.
                    if not _final_emitted and not _suggest_actions_done(_msgs_with_current) and stop_reason in ("end_turn", "stop") and not tool_use_blocks:
                        # Emite o dossiê agora e força turno dedicado para suggest_next_actions
                        _final_response = response_text
                        if not _final_response.strip():
                            # Verifica se houve algum write de sucesso real no histórico
                            _real_write_success = False
                            _WRITE_TOOLS_CHECK = {"pipedrive_update_task", "pipedrive_create_note", "pipedrive_create_task", "pipedrive_create_person", "whatsapp_send_message", "email_send", "email_reply"}
                            for _m in messages:
                                _mc = _m.get("content", "")
                                if isinstance(_mc, list):
                                    for _b in _mc:
                                        if isinstance(_b, dict) and _b.get("type") == "tool_result" and _b.get("tool_name") in _WRITE_TOOLS_CHECK:
                                            try:
                                                _rd = json.loads(_b.get("content", "{}"))
                                                if _rd.get("ok"): _real_write_success = True
                                            except: pass
                            
                            if _real_write_success:
                                _final_response = "Ação realizada com sucesso! Aqui estão as sugestões de próximos passos:"
                            else:
                                _final_response = "Investigação concluída! Aqui estão as sugestões de próximos passos:"

                        _raw_log(process_id, "agent_final_response", {"response": _final_response})
                        _cached_final_response = _final_response
                        yield _emit({"type": "thinking", "content": "Analisando histórico para sugerir ações..."})
                        _final_emitted = True

                        # Se for tarefa de ação (_is_task_action), injeta um aviso extra no prompt de sugestão
                        _task_action_hint = ""
                        if _is_task_action:
                            _task_action_hint = (
                                f"\nTAREFA CRM CONCLUÍDA: A atividade #{_first_msg_content[:20]}... foi processada.\n"
                                "Agora gere sugestões focadas no PÓS-CONTATO ou em novas frentes de prospecção."
                            )

                        real_data_summary = []
                        if found_org:
                            real_data_summary.append(f"  - Organização/Empresa: '{found_org}'")
                        if found_deal_id:
                            real_data_summary.append(f"  - ID do Negócio Comercial (deal_id): {found_deal_id}")
                        if found_activities:
                            real_data_summary.append("  - Atividades Pendentes no Pipedrive (IDs REAIS):")
                            for _a in found_activities:
                                real_data_summary.append(f"    • ID: {_a['id']} | Assunto: '{_a['subject']}' | Vencimento: {_a['due_date']}")
                        if found_contacts:
                            real_data_summary.append("  - Contatos Atuais no Pipedrive:")
                            for _c in found_contacts:
                                real_data_summary.append(f"    • {_c.get('name')} (E-mail: {_c.get('email') or 'N/A'}, Tel: {_c.get('phone') or 'N/A'})")
                        else:
                            real_data_summary.append("  - Contatos Atuais no Pipedrive: Nenhum contato cadastrado ainda!")

                        real_data_str = "\n".join(real_data_summary) if real_data_summary else "  (Nenhum ID específico encontrado)"

                        messages.append({"role": "assistant", "content": content})
                        context_lines = [s for s in _collected_tool_summaries[-10:] if s]
                        context_str = "\n".join(f"  • {s}" for s in context_lines) if context_lines else "  (sem dados específicos)"
                        messages.append({
                            "role": "user",
                            "content": (
                                f"Dossiê entregue. DADOS REAIS EXTRAÍDOS DO HISTÓRICO (USE APENAS ESTES IDS):\n{real_data_str}\n\n"
                                f"RESUMO DAS FONTES:\n{context_str}\n\n"
                                f"{_task_action_hint}\n"
                                "Você é um Consultor de Vendas B2B sênior e altamente estratégico. "
                                "Chame OBRIGATORIAMENTE 'suggest_next_actions' com ações específicas, contextualizadas e comercialmente brilhantes.\n"
                                "ATENÇÃO: Se a busca retornou uma LISTA de entidades (ex: 12 negócios sem tarefas, múltiplos prospects), "
                                "VOCÊ DEVE GERAR UMA AÇÃO INDIVIDUAL PARA CADA UM DELES. NÃO agrupe ações e NÃO resuma. "
                                "Você pode e deve gerar até 20 ações se houver 20 empresas na lista.\n"
                                "Avalie inteligentemente o status de cada entidade na lista. Por exemplo: se um negócio sem tarefa possuir o aviso 'SEM CONTATO', a tarefa que você deve criar para ele deverá se focar ativamente em 'Procurar contato/Encontrar decisor' ao invés de follow-ups genéricos.\n"
                                "MUITO IMPORTANTE: Não forneça uma introdução gigante em texto Markdown antes de chamar as actions. "
                                "Deixe que os botões (actions) gerados mostrem o que precisa ser feito.\n"
                                "Cada ação DEVE ter:\n"
                                "• 'label': texto curto, persuasivo e atraente para o botão (comercialmente focado)\n"
                                "• 'prompt': instrução autossuficiente com IDs e parâmetros REAIS obtidos nas buscas.\n\n"
                                f"{active_skill.get_suggestion_rules() if active_skill else ''}\n"
                                "NÃO invente IDs. Se não tiver ID real, não use o prompt correspondente.\n"
                                "NÃO escreva nenhum outro texto no seu retorno. Apenas chame suggest_next_actions."
                            ),
                        })
                        continue
                except Exception:
                    pass

            if _final_emitted and not _suggest_actions_done(messages):
                # O dossiê já foi emitido, mas o LLM falhou em gerar o suggest_next_actions.
                # Chamada arquitetural: aciona o serviço de estratégia para gerar os cards de aprovação dinâmicos.
                from modules.sales.service.strategy import sales_strategy_service
                strategy_res = await sales_strategy_service.analyze_and_suggest_actions(messages, org_id)
                if strategy_res and strategy_res.get("ok"):
                    fallback_actions = strategy_res.get("actions", [])
                    if fallback_actions:
                        _raw_log(process_id, "agent_fallback_suggested_actions", {"actions": fallback_actions})
                        yield _emit({
                            "type": "suggested_actions",
                            "actions": fallback_actions
                        })

            if not _final_emitted:
                yield _emit({"type": "final", "response": response_text})
            elif _cached_final_response:
                yield _emit({"type": "final", "response": _cached_final_response})
            return

        # Separa ferramentas de leitura e escrita
        tool_results = []
        write_tool_pending = None
        read_blocks = []

        for block in tool_use_blocks:
            tool_name = block.get("name", "")
            tool_args = block.get("input") or {}
            tool_id = block.get("id", "")

            # 🚀 INTERCEPTOR: Bloqueio Hard de WhatsApp para contatos Somente-Email
            if tool_name == "whatsapp_get_messages":
                _contact_name = (tool_args.get("contact") or "").lower()
                # Se o contato está na lista de e-mails mas NÃO está na lista de WA
                _is_only_email = any(_p[0].lower() in _contact_name for _p in _persons_with_email) and not any(_p[0].lower() in _contact_name for _p in _persons_with_wa)
                
                if _is_only_email:
                    log.info("agent.interceptor.whatsapp_blocked_only_email", contact=_contact_name)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": (
                            f"AÇÃO BLOQUEADA PELO SISTEMA: O contato '{tool_args.get('contact')}' não possui WhatsApp "
                            "registrado (canal identificado: apenas Email). É PROIBIDO tentar buscar mensagens de WhatsApp "
                            "para este contato. PROSSIGA imediatamente para 'email_get_contact_history' ou para a ação final."
                        ),
                        "is_error": False,
                    })
                    continue

            # 🚀 INTERCEPTOR: Bloqueio Hard de Mapeamento Redundante
            # Se um decisor local foi encontrado, é terminantemente proibido abrir o mapeador.
            if tool_name == "open_hierarchy_drawer" and _has_local_decision_maker:
                log.info("agent.interceptor.hierarchy_drawer_blocked", org_name=tool_args.get("org_name"))
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": (
                        "AÇÃO BLOQUEADA PELO SISTEMA: Um decisor estratégico (Compras/Logística) já foi identificado "
                        "no Banco Local para esta empresa. O mapeamento de hierarquia é desnecessário e redundante. "
                        "PROSSIGA agora para a associação do contato ao negócio ou verificação dos canais de comunicação "
                        "já encontrados (WhatsApp/E-mail)."
                    ),
                    "is_error": False,
                })
                continue

            # 🚀 INTERCEPTOR: Validação de E-mail Obrigatória
            if tool_name in ("email_send", "email_reply"):
                _target_email = tool_args.get("to") or ""
                _contact_name = tool_args.get("contact_name") or ""

                # 🚀 AUTO-ENRICH: Adiciona assinatura e apresentação automaticamente para exibição no front-end
                try:
                    import os as _os
                    from modules.ai.service.context.business_context_service import BusinessContextService
                    
                    # 1. Força a Apresentação se não estiver definida
                    if tool_name == "email_send" and not tool_args.get("attachment_name"):
                        tool_args["attachment_name"] = "apresentacao_linkb2b"

                    # 2. Embutir assinatura no corpo do email para visualização imediata no frontend
                    _body = tool_args.get("body") or ""
                    if "<!-- SIGNATURE_START -->" not in _body and "J.Ferres" not in _body:
                        ctx = await BusinessContextService.get_tenant_context()
                        sig_path = ctx.get("signature_path")
                        if sig_path and _os.path.exists(sig_path):
                            try:
                                import base64 as _base64
                                from pathlib import Path as _Path
                                ext = _Path(sig_path).suffix.lower().replace(".", "")
                                if ext in ("png", "jpg", "jpeg", "gif"):
                                    with open(sig_path, "rb") as f:
                                        b64_data = _base64.b64encode(f.read()).decode()
                                    mime = f"image/{ext}" if ext != "jpg" else "image/jpeg"
                                    sig_html = f'<br><br><!-- SIGNATURE_START --><img src="data:{mime};base64,{b64_data}" style="max-width: 400px; height: auto;" /><!-- SIGNATURE_END -->'
                                    if sig_html not in _body:
                                        tool_args["body"] = _body + sig_html
                            except Exception as sig_err:
                                log.warning(f"Erro ao embutir assinatura em loop.py: {sig_err}")
                        else:
                            # Assinatura em texto se não houver imagem
                            sig_text = f"<br><br>--<br><b>{seller_name}</b><br>Equipe Comercial {company_name}"
                            if sig_text not in _body:
                                tool_args["body"] = _body + sig_text
                except Exception as enrich_err:
                    log.warning(f"Erro ao enriquecer email com assinatura/apresentação: {enrich_err}")
                
                # Só intercepta se ainda não validou NESTA sessão
                _already_validated = False
                for _m in messages:
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict) and _b.get("tool_name") == "discover_and_validate_email":
                                try:
                                    _res = json.loads(_b.get("content", "{}"))
                                    if _res.get("recommended") == _target_email or _target_email in str(_res.get("valid_emails")):
                                        _already_validated = True
                                        break
                                except Exception:
                                    pass

                # Força a validação de e-mails em tempo real sem assumir que dados crus do Pipedrive sejam válidos de antemão.
                # Só pulamos a validação se ela já foi explicitamente executada nesta sessão (via discover_and_validate_email).

                # Se ainda não detectado, faz uma busca no banco local pelo endereço de e-mail (para pegar validações do UI/históricas)
                if not _already_validated and _target_email:
                    try:
                        from core.infra.database import async_session
                        from models.people.employee import Employee
                        from sqlalchemy import select
                        
                        async with async_session() as session:
                            stmt = select(Employee).where(Employee.email == _target_email)
                            res = await session.execute(stmt)
                            db_emp = res.scalar_one_or_none()
                            if db_emp:
                                log.info("agent.interceptor.email_validated_via_local_db", email=_target_email)
                                _already_validated = True
                    except Exception as db_err:
                        log.warning(f"Erro ao verificar email no banco local: {db_err}")
                
                # Se não validou e o e-mail parece um padrão gerado (contém pontos/under ou é curto)
                # ou se o usuário explicitamente pediu para validar (via Alerta de Contexto)
                _looks_like_pattern = _target_email and ("." in _target_email.split("@")[0] or "_" in _target_email.split("@")[0])
                
                if not _already_validated and (_looks_like_pattern or not _target_email):
                    log.info("agent.interceptor.email_validation_forced", email=_target_email)
                    
                    # 🚀 NOVA LÓGICA: Auto-validação inline
                    _auto_validated = False
                    _auto_validated_email = None
                    try:
                        from modules.agent.service.tools.intelligence import exec_discover_and_validate_email
                        
                        # Tenta obter domínio para a busca
                        _domain = ""
                        if org_id:
                            from modules.crm.service.pipedrive_service import pipedrive_service
                            org_details = await pipedrive_service.get_organization_details(org_id)
                            if isinstance(org_details, dict):
                                _domain = org_details.get("domain") or org_details.get("website") or ""
                        
                        if not _domain:
                            from core.infra.database import async_session
                            from models.organization import Organization
                            from sqlalchemy import select
                            async with async_session() as session:
                                stmt = select(Organization).where((Organization.id == org_id) | (Organization.pipedrive_id == org_id))
                                res = await session.execute(stmt)
                                o_db = res.scalar_one_or_none()
                                if o_db:
                                    _domain = o_db.domain or ""
                        
                        validation_args = {
                            "contact_name": _contact_name,
                            "org_name": tool_args.get("org_name", ""),
                            "domain": _domain
                        }
                        
                        log.info("agent.interceptor.auto_validating_inline", args=validation_args)
                        val_res = await exec_discover_and_validate_email(validation_args)
                        if val_res.get("ok") and val_res.get("recommended"):
                            _auto_validated_email = val_res.get("recommended")
                            _smtp_result = val_res.get("smtp_result")
                            if _smtp_result == "valid":
                                log.info("agent.interceptor.auto_validation_success_smtp", email=_auto_validated_email)
                            else:
                                log.warning(f"E-mail {_auto_validated_email} estimado por heuristica (SMTP result: {_smtp_result}). Recomenda-se configurar a VRFYMAIL_API_KEY no arquivo .env para validacao completa.")
                            tool_args["to"] = _auto_validated_email
                            _auto_validated = True
                            _already_validated = True
                    except Exception as val_err:
                        log.warning(f"Falha na validação inline automática: {val_err}")
                    
                    # Se não conseguiu auto-validar, fazemos um retorno suave de instrução para a IA em vez de crashar
                    if not _auto_validated:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "tool_name": tool_name,
                            "content": (
                                f"AVISO DE SEGURANÇA: O e-mail '{_target_email}' para o contato '{_contact_name}' "
                                "precisa ser validado antes do envio real para evitar que caia em SPAM ou retorne erro.\n\n"
                                "Por favor, chame a ferramenta `discover_and_validate_email` no próximo passo para confirmar o e-mail.\n"
                                f"Chame: discover_and_validate_email(contact_name='{_contact_name}', org_name='{tool_args.get('org_name', '')}')"
                            ),
                            "is_error": False,
                        })
                        continue


            # 🚀 INTERCEPTOR: Trava de Execução de Tarefa de Valor
            # Impede fechar tarefas complexas (Otimização, Proposta, Follow-up) sem antes realizar a ação.
            if tool_name == "pipedrive_update_task":
                _done_val = tool_args.get("done")
                _is_marking_done = _done_val is True or str(_done_val).lower() in ("true", "1", "yes", "y")
                
                if _is_marking_done:
                    # Verifica intenção de comunicação em TODO o histórico (não apenas na primeira mensagem)
                    _full_history_text = " ".join(str(m.get("content", "")).lower() for m in messages)
                    _is_comm_task = any(kw in _full_history_text for kw in ["enviar", "email", "whatsapp", "mensagem", "mandar", "falar", "apresentação", "proposta", "follow", "otimização", "ligar"])
                    
                    if _is_comm_task:
                        _comm_proposed = False
                        _COMM_TOOLS = {"whatsapp_send_message", "email_send", "email_reply", "generate_sales_message"}
                        
                        # Verifica se houve rascunho ou envio no histórico
                        for _m in messages:
                            _mc = _m.get("content", "")
                            if isinstance(_mc, list):
                                for _b in _mc:
                                    if not isinstance(_b, dict): continue
                                    _tn_hist = _b.get("tool_name") or _b.get("name")
                                    if _tn_hist in _COMM_TOOLS:
                                        _comm_proposed = True
                                        break
                        
                        # Verifica se está propondo AGORA no mesmo bloco
                        if not _comm_proposed:
                            for _b in tool_use_blocks:
                                if _b.get("name") in _COMM_TOOLS:
                                    _comm_proposed = True
                        
                        if not _comm_proposed:
                            log.info("agent.interceptor.value_task_close_blocked", tool=tool_name, reason="no_comm_found")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "tool_name": tool_name,
                                "content": (
                                    "ERRO DE FLUXO: Você está tentando concluir uma Tarefa de Comunicação no Pipedrive, "
                                    "mas ainda NÃO gerou o rascunho da mensagem nem propôs o envio real.\n\n"
                                    "É PROIBIDO fechar a tarefa sem antes realizar o trabalho comercial.\n"
                                    "OBRIGATÓRIO AGORA: \n"
                                    "1. Use `generate_sales_message` para criar o e-mail/WhatsApp.\n"
                                    "2. Use `email_send` ou `whatsapp_send_message` para propor o envio ao João.\n"
                                    "3. Somente após essas etapas você poderá marcar a tarefa como concluída."
                                ),
                                "is_error": False,
                            })
                            continue

            # 🚀 INTERCEPTOR: Trava de Alvo Definido (Target Locking)
            # Se a tarefa já tem um nome de pessoa (ex: "Ligar para Pedro"),
            # é PROIBIDO rodar evaluate_prospects ou buscar outros contatos.
            if _session_task_person and _is_task_action:
                _tpn_lower = _session_task_person.lower()
                
                # Bloqueia mapeamento de novos perfis se o alvo já é conhecido
                if tool_name == "evaluate_prospects":
                    log.info("agent.interceptor.target_locked.eval_blocked", person=_session_task_person)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": (
                            f"AÇÃO BLOQUEADA: A tarefa atual é para um contato específico: '{_session_task_person}'. "
                            "Não é necessário avaliar outros perfis. PROSSIGA imediatamente para a preparação da ligação "
                            f"com '{_session_task_person}'."
                        ),
                        "is_error": False,
                    })
                    continue
                
                # Bloqueia busca de e-mails/WA de outras pessoas
                if tool_name in ("whatsapp_get_messages", "email_get_contact_history"):
                    _target_args = (tool_args.get("contact") or tool_args.get("contact_name") or "").lower()
                    # Se o nome que a IA quer buscar NÃO contém o nome do alvo da tarefa
                    _is_different_person = _tpn_lower.split()[0] not in _target_args
                    
                    if _is_different_person:
                        log.info("agent.interceptor.target_locked.search_blocked", target=_session_task_person, requested=_target_args)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "tool_name": tool_name,
                            "content": (
                                f"AÇÃO BLOQUEADA: Foco no Alvo. A tarefa é para '{_session_task_person}'. "
                                f"É proibido investigar '{_target_args}' enquanto a tarefa principal não for concluída. "
                                f"Busque apenas o histórico de '{_session_task_person}'."
                            ),
                            "is_error": False,
                        })
                        continue

            # 🚀 INTERCEPTOR: Trava de Sugestão Prematura
            if tool_name == "suggest_next_actions" and _is_task_action:
                 # Se for uma tarefa de comunicação, não pode sugerir próximos passos 
                 # sem antes ter proposto o envio da mensagem desta tarefa.
                 _full_history_text = " ".join(str(m.get("content", "")).lower() for m in messages)
                 _is_comm_task = any(kw in _full_history_text for kw in ["enviar", "email", "whatsapp", "mensagem", "mandar", "falar", "apresentação", "proposta", "follow", "otimização", "ligar"])
                 
                 if _is_comm_task:
                     _has_sent_global = False
                     _SEND_TOOLS = {"whatsapp_send_message", "email_send", "email_reply"}
                     
                     for _m in messages:
                         _mc = _m.get("content", "")
                         if isinstance(_mc, list):
                             for _b in _mc:
                                 if not isinstance(_b, dict): continue
                                 _tn_check = _b.get("tool_name") or _b.get("name")
                                 if _tn_check in _SEND_TOOLS:
                                     _has_sent_global = True
                                     break
                     
                     if not _has_sent_global:
                         log.info("agent.interceptor.suggestion_blocked_comm_pending", tool=tool_name)
                         tool_results.append({
                             "type": "tool_result",
                             "tool_use_id": tool_id,
                             "tool_name": tool_name,
                             "content": (
                                 "BLOQUEIO: Você está tentando sugerir próximos passos (suggest_next_actions), "
                                 "mas ainda não realizou a ação principal desta tarefa (enviar e-mail/WhatsApp). "
                                 "OBRIGATÓRIO: Use `generate_sales_message` e depois a ferramenta de envio correspondente "
                                 "ANTES de chamar suggest_next_actions. A tarefa só acaba quando a comunicação é proposta."
                             ),
                             "is_error": False,
                             "summary": "SKIPPED: Ação pendente"
                         })
                         # Adiciona um marcador no histórico para o LLM saber que deve focar na comunicação
                         messages.append({"role": "assistant", "content": content})
                         messages.append({
                             "role": "user",
                             "content": "Atenção: A chamada de `suggest_next_actions` foi ignorada pelo sistema porque você ainda não enviou a mensagem desta tarefa. Foque em gerar o rascunho e propor o envio agora."
                         })
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

            # Deduplicação de tool calls — ferramentas de leitura idempotentes não devem
            # ser chamadas mais de uma vez para o MESMO alvo por sessão.
            # Pipedrive (org/persons/deals/activities): chave = tool_name (uma empresa por sessão).
            # Comunicação (whatsapp/email): chave = (tool_name, contato) — permite múltiplos
            # contatos diferentes na mesma sessão (ex: Edvaldo + Lucas + Semorin).
            _DEDUP_PIPEDRIVE = {
                "pipedrive_get_org", "pipedrive_get_persons",
                "pipedrive_get_deals", "pipedrive_get_activities",
            }
            _DEDUP_COMM = {"whatsapp_get_messages", "email_get_contact_history"}
            _DEDUP_READ_TOOLS = _DEDUP_PIPEDRIVE | _DEDUP_COMM

            if tool_name in _DEDUP_READ_TOOLS:
                # Pipedrive: dedup por nome de ferramenta (mesma empresa → mesmo resultado)
                # Comunicação: dedup por (ferramenta, contato) — contatos diferentes = chamadas diferentes
                if tool_name in _DEDUP_PIPEDRIVE:
                    _dedup_key = tool_name
                else:
                    _contact_id = (
                        tool_args.get("contact") or
                        tool_args.get("contact_name") or
                        tool_args.get("org_name") or ""
                    ).lower().strip()
                    _dedup_key = f"{tool_name}:{_contact_id}"

                if _dedup_key in _tool_call_history:
                    log.warning("agent.tool_call.dedup_blocked", tool=tool_name, tool_args=str(tool_args)[:80])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": f"[DEDUP] {_dedup_key} já foi executada nesta sessão. Avance para o próximo contato ou ação.",
                        "is_error": False,
                        "summary": f"[já coletado]",
                    })
                    continue
                else:
                    # Registra MENTIRAMENTE agora para já bloquear o próximo `block` no mesmo turno
                    _tool_call_history.add(_dedup_key)

            tool_meta = TOOLS[tool_name]

            _INVESTIGATION_REQUIRED = {"whatsapp_send_message", "email_send", "email_reply", "pipedrive_create_task", "pipedrive_create_person", "suggest_next_actions", "prepare_live_coaching_session"}
            if tool_name in _INVESTIGATION_REQUIRED:
                try:
                    _phase = _build_phase_status(messages, query_type=query_type, org_id=org_id)
                    
                    context_mode_active = False
                    command_mode_active = False
                    for msg in messages:
                        if msg.get("role") == "user":
                            _content = str(msg.get("content", "")).lower()
                            if "[MODO CONTEXTO" in _content:
                                context_mode_active = True
                            import re as _re
                            if _re.search(r'\b(execute|realizar|realize|marque|crie|adicione|atualize|altere|mande|envie|agende|ligue)\b', _content):
                                command_mode_active = True

                    _is_investigation = query_type in ("deal_status", "agent_workflow") or (
                        org_id is not None
                        and org_id > 0
                        and query_type != "pipedrive_tasks"
                        and not context_mode_active
                        and not command_mode_active
                    )

                    _write_allowed = (
                        direct_action 
                        or _is_task_action 
                        or "Fase final" in _phase 
                        or "Todas as fontes foram investigadas" in _phase
                        or not _is_investigation
                    )
                    
                    if tool_name == "prepare_live_coaching_session":
                        _local_called_ctx = set()
                        for _m2 in messages:
                            _mc2 = _m2.get("content", "")
                            if isinstance(_mc2, list):
                                for _b2 in _mc2:
                                    if isinstance(_b2, dict) and _b2.get("type") == "tool_use":
                                        _local_called_ctx.add(_b2.get("name"))
                        
                        if active_skill and hasattr(active_skill, "core_tools"):
                            _local_missing = set(active_skill.core_tools) - _local_called_ctx
                        else:
                            _local_missing = {"deep_company_investigation", "evaluate_prospects"} - _local_called_ctx
                        if _local_missing:
                            _write_allowed = False
                        
                        _passed_phone = str(tool_args.get("phone", "")).strip()
                        if not _passed_phone or _passed_phone.lower() == "nenhum":
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "tool_name": tool_name,
                                "content": f"AÇÃO BLOQUEADA: Contato sem telefone válido. CHAME A FERRAMENTA 'find_company_contact' para buscar o número antes de preparar a ligação.",
                                "is_error": True,
                            })
                            continue
                except Exception:
                    _write_allowed = True

                if not _write_allowed:
                    # suggest_next_actions NUNCA deve ser bloqueado
                    if tool_name == "suggest_next_actions":
                        pass  # permite continuar normalmente
                    elif tool_name == "prepare_live_coaching_session":
                        _missing_names = ", ".join(f"'{t}'" for t in _local_missing)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "tool_name": tool_name,
                            "content": f"AÇÃO BLOQUEADA: Você deve executar as ferramentas fundamentais ({_missing_names}) antes de gerar o plano de voo da ligação.",
                            "is_error": True,
                        })
                        continue
                    else:
                        _block_reason = (
                            "criar tarefas embasadas" if tool_name == "pipedrive_create_task"
                            else "criar novos contatos" if tool_name == "pipedrive_create_person"
                            else "enviar mensagens ou emails"
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "tool_name": tool_name,
                            "content": (
                                f"BLOQUEADO: complete a investigação de comunicação (whatsapp_get_messages e email_get_contact_history) antes de {_block_reason}. "
                                + _phase
                            ),
                            "is_error": False,
                        })
                        continue

            # Ferramenta de ESCRITA — sempre exige confirmação do usuário, inclusive em direct_action.
            # O direct_action já foi aprovado pelo usuário (ação sugerida), mas qualquer
            # side-effect externo (enviar email, atualizar CRM, enviar WhatsApp) requer
            # uma segunda confirmação explícita para evitar ações não intencionais.
            if tool_meta["type"] == "write":
                if tool_name == "open_ligacao_view":
                    _passed_phone = str(tool_args.get("phone", "")).strip()
                    if not _passed_phone or _passed_phone.lower() == "nenhum":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "tool_name": tool_name,
                            "content": f"AÇÃO BLOQUEADA: Contato sem telefone válido. CHAME A FERRAMENTA 'find_company_contact' para buscar o número na Receita Federal antes de invocar a ligação.",
                            "is_error": True,
                        })
                        continue

                if write_tool_pending is None:
                    call_id = f"tc_{iteration}_{uuid.uuid4().hex[:6]}"
                    write_tool_pending = {
                        "block": block,
                        "call_id": call_id,
                        "label": _get_label(tool_name, tool_args),
                        "prior_results": [],
                        "org_id": org_id,
                    }
                continue  # leituras primeiro

            # Guard: generate_dossier só pode ser chamado quando todas as
            # comunicações foram investigadas (fase 3b ou posterior).
            if tool_name == "generate_dossier":
                try:
                    _gd_phase = _build_phase_status(messages, query_type=query_type, org_id=org_id)
                    _gd_allowed = (
                        _is_task_action
                        or "Todas as fontes foram investigadas" in _gd_phase
                        or "Fase final" in _gd_phase
                        or query_type not in ("agent_workflow", "deal_status")
                    )
                except Exception:
                    _gd_allowed = True
                if not _gd_allowed:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": (
                            "BLOQUEADO: complete todas as buscas de comunicação antes de consolidar. "
                            + _gd_phase
                        ),
                        "is_error": False,
                    })
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

        # Executa TODAS as ferramentas de leitura SEQUENCIALMENTE no mesmo turno.
        # Isso garante que a API receba tool_result para todos os
        # tool_use do turno (obrigatoriedade da spec), sem quebrar o fluxo narrativo
        # e sem confundir o LLM com mensagens de erro falsas.
        if read_blocks:
            for first_block, first_call_id, first_executor in read_blocks:
                tool_args = first_block.get("input") or {}
                tool_id = first_block.get("id", "")
                tool_name = first_block.get("name", "")

                yield _emit({"type": "tool_call", "call_id": first_call_id, "tool": tool_name,
                             "args": tool_args, "label": _get_label(tool_name, tool_args)})

                _raw_log(process_id, "tool_execute_start", {"tool": tool_name, "args": tool_args, "call_id": first_call_id})

                try:
                    import inspect
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

                if not tool_result.get("ok"):
                    _err = str(tool_result.get("error", "")).lower()
                    _expected = any(x in _err for x in [
                        "não encontrad", "not found", "nenhum", "0 contatos", "0 deal",
                        "0 mensagens", "0 e-mail", "sem histórico",
                    ])
                    if not _expected:
                        try:
                            import asyncio as _asyncio
                            await _asyncio.sleep(1)
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
                            log.info("agent.session_org_id.updated", org_id=org_id, tool_name=tool_name)
                        except (ValueError, TypeError):
                            pass

                if ok and tool_name == "pipedrive_get_activities" and not _session_task_person:
                    _pending_acts = (tool_result.get("pending") or []) if isinstance(tool_result, dict) else []
                    for _a in _pending_acts:
                        if isinstance(_a, dict) and _a.get("person_name"):
                            _session_task_person = _a["person_name"]
                            log.info("agent.session_task_person.set", person=_session_task_person)
                            break

                summary = tool_result.get("summary") or tool_result.get("error") or ("OK" if ok else "Erro")
                emitted_result = {"type": "tool_result", "call_id": first_call_id, "tool": tool_name, "summary": summary, "ok": ok, "args": tool_args}
                if "quota" in tool_result:
                    emitted_result["data"] = {"quota": tool_result.get("quota")}
                yield _emit(emitted_result)
                yield _emit({"type": "context_saved"})

                if ok and summary:
                    _collected_tool_summaries.append(f"[{tool_name}] {summary}")

                if ok and tool_name == "suggest_next_actions":
                    actions = tool_result.get("actions", [])
                    if actions:
                        yield _emit({"type": "suggested_actions", "actions": actions})

                if ok and tool_name == "open_hierarchy_drawer":
                    yield _emit({
                        "type": "hierarchy_mapping_required",
                        "org_name": tool_result.get("org_name"),
                        "org_id": tool_result.get("org_id"),
                        "deal_id": tool_result.get("deal_id"),
                        "activity_id": tool_result.get("activity_id"),
                        "pre_task_id": tool_result.get("pre_task_id"),
                    })
                    if not _final_emitted:
                        _final_emitted = True
                        _org = tool_result.get("org_name", "a empresa")
                        yield _emit({"type": "final", "response": f"Empresa **{_org}** aberta no mapeador. Insira o CNPJ e inicie o mapeamento — assim que terminar, continuarei automaticamente."})
                    return

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

                sanitized = _sanitize_result(tool_name, tool_result)
                raw_content = json.dumps(sanitized, ensure_ascii=False) if isinstance(sanitized, (dict, list)) else str(sanitized)
                _max_content = 4000 if tool_name in ("pipedrive_get_all_activities", "email_get_inbox", "email_get_contact_history", "evaluate_prospects") else 2000
                if len(raw_content) > _max_content:
                    raw_content = raw_content[:_max_content] + "... [TRUNCADO]"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": raw_content,
                })

        # Pausa para ferramenta de escrita (leituras já foram executadas)
        if write_tool_pending:
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
                "prior_results": tool_results,  # inclui resultados das leituras paralelas
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

            yield _emit({
                "type": "confirmation_required",
                "action_id": action_id,
                "call_id": write_tool_pending["call_id"],
                "tool": tool_name,
                "label": confirm_label,
                "preview": str(preview),
                "args": tool_args,
            })
            
            # Se for abertura de ligação, pausamos a execução do loop do agente aqui.
            # O agente só deve retomar após o usuário encerrar a ligação manualmente.
            if tool_name == "open_ligacao_view":
                return

            return

        # Todos os tool calls processados — adiciona ao histórico e continua
        # Adiciona a resposta do assistente (chamada de ferramenta)
        messages.append({"role": "assistant", "content": content, "tool_use_id": [b["id"] for b in tool_use_blocks] if tool_use_blocks else None})
        
        # Adiciona os resultados usando o formato de lista de objetos que o _messages_to_openai entende
        messages.append({"role": "user", "content": tool_results})

    # Esgotou iterações
    yield _emit({
        "type": "final",
        "response": "Não consegui concluir a tarefa dentro do número máximo de passos. Tente reformular o pedido.",
    })
