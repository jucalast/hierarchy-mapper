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

from modules.agent.service.helpers import _emit, _raw_log, _fix_corrupted_name, _get_thinking_fallback, _get_label
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

MAX_ITERATIONS = 20

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
    _max_iters = (16 if _is_task_action else 6) if direct_action else MAX_ITERATIONS

    # ── DETECÇÃO DE DIRETIVA DIRETA ──
    # Se o usuário deu uma ordem direta de escrita (Ex: "atualize a nota", "marque como feita"),
    # ativamos o modo "Direct Directive". Nesse modo, o agente é proibido de sugerir
    # ações proativas (como rascunhar e-mail) antes de cumprir o comando original.
    _DIRECTIVE_KEYWORDS = ["atualize", "marque", "crie", "delete", "remova", "altere", "nota", "escreva", "execute"]
    _is_direct_directive = direct_action and any(kw in _first_msg_content.lower() for kw in _DIRECTIVE_KEYWORDS)
    if _is_direct_directive:
        log.info("agent.intent.direct_directive_detected", content=_first_msg_content[:50])
        active_skill = None  # Desativa Skills para ordens diretas/action cards

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
    _tool_call_history: set[tuple] = set()
    # Nome do contato dono da tarefa (person_name da atividade pendente do Pipedrive).
    _session_task_person: str | None = None
    
    for iteration in range(start_iteration, _max_iters):
        # Sai assim que suggest_next_actions foi chamado
        if _suggest_actions_done(messages):
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
        if active_skill:
            system = active_skill.get_instructions({"org_id": org_id, "process_id": process_id})
        elif _is_direct_directive:
            system = SYSTEM_PROMPT_TASK_DIRECTIVE
        elif direct_action:
            system = SYSTEM_PROMPT_DIRECT
        else:
            try:
                system = _build_phase_status(messages, query_type=query_type, org_id=org_id)
            except Exception:
                system = SYSTEM_PROMPT_POWERFUL

        # ── Tool calling ──────────────────────────────────────────────────────
        try:
            import asyncio as _asyncio

            # Se houver skill ativo, filtramos as ferramentas
            # para as permitidas pelo skill.
            _current_tools = tools
            if active_skill:
                _current_tools = [t for t in tools if t.get("name") in active_skill.allowed_tools]
                log.info("agent.intent.active_skill.tools_filtered", count=len(_current_tools))
            elif _is_direct_directive:
                _PIPEDRIVE_WRITE_TOOLS = {
                    "pipedrive_update_task", "pipedrive_create_note", "pipedrive_create_person",
                    "pipedrive_create_task", "pipedrive_create_deal", "pipedrive_get_activities",
                    "pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals"
                }
                _current_tools = [t for t in tools if t.get("name") in _PIPEDRIVE_WRITE_TOOLS]
                log.info("agent.intent.direct_directive.tools_filtered", count=len(_current_tools))

            _raw_log(process_id, "llm_request", {"system": system, "messages": messages, "iteration": iteration})
            _pending_events: list = []
            # Roda _call_with_tools como task em background para poder emitir
            # eventos (rate_wait, model_active) em tempo real enquanto ele aguarda.
            # Para tarefas CRM: força chamada de ferramenta enquanto Pipedrive core incompleto,
            # restringindo ao próximo tool core pendente para garantir a ordem correta.
            _force = False
            _allowed_core: list | None = None
            if active_skill:
                _CORE = set(active_skill.core_tools)
                _CORE_ORDER = list(active_skill.core_tools)
                _done: set[str] = set()
                for _m in messages:
                    _mc = _m.get("content","")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict):
                                _tn = _b.get("tool_name") or _b.get("name","")
                                if _b.get("type") in ("tool_result","tool_use") and _tn in _CORE:
                                    _done.add(_tn)
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
                _done: set[str] = set()
                for _m in messages:
                    _mc = _m.get("content","")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict):
                                _tn = _b.get("tool_name") or _b.get("name","")
                                if _b.get("type") in ("tool_result","tool_use") and _tn in _CORE:
                                    _done.add(_tn)
                _missing_core = _CORE - _done
                if _missing_core:
                    _force = True
                    # Restringe ao próximo tool core em ordem — impede Gemini de pular para
                    # whatsapp/email antes de terminar o Bloco 1 (Pipedrive).
                    _next_core = next((t for t in _CORE_ORDER if t not in _done), None)
                    if _next_core:
                        _allowed_core = [_next_core]

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
        if stop_reason == "end_turn" or not tool_use_blocks:
            response_text = " ".join(b.get("text", "") for b in text_blocks).strip()

            # Modo execução direta: verificar se a Fase 1 foi concluída antes de encerrar
            if direct_action and _is_task_action:
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

                _missing_ctx = _CTX_TOOLS - _called_ctx
                # Só bloqueia se faltam ferramentas core (org, persons, deals, activities)
                # — as de comunicação podem ser omitidas pelo padrão "Encontrar Decisor"
                _CORE_CTX = {"deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals", "pipedrive_get_activities"}
                _missing_core = _CORE_CTX - _called_ctx

                # Ordem preferida de execução da fase 1
                _CTX_ORDER = [
                    "deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals",
                    "pipedrive_get_activities", "whatsapp_get_messages", "email_get_contact_history",
                ]
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

                # ── Interceptor: contatos com canal ainda não investigados ─────────────
                # Para tarefas de follow-up/comunicação, garante que TODOS os contatos
                # ── Interceptor: Email obrigatório para contato-tarefa ──────────────────────
                # Para tarefas com contato específico (_session_task_person), sempre busca
                # TAMBÉM o email após WhatsApp — independente do resultado do WhatsApp.
                if _session_task_person and _is_task_action and iteration < _max_iters - 2:
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
                if iteration < _max_iters - 2:
                    # Prioriza o contato dono da tarefa — usa _session_task_person capturado
                    # durante a execução de pipedrive_get_activities (dado raw, antes da sanitização).
                    if _session_task_person:
                        _tpn_lower = _session_task_person.lower()
                        # WA
                        _task_entry_wa = next((p for p in _persons_with_wa if _tpn_lower in p[0].lower() or p[0].lower().split()[0] in _tpn_lower), None)
                        if _task_entry_wa and _persons_with_wa.index(_task_entry_wa) != 0:
                            _persons_with_wa.remove(_task_entry_wa)
                            _persons_with_wa.insert(0, _task_entry_wa)
                        # Email
                        _task_entry_email = next((p for p in _persons_with_email if _tpn_lower in p[0].lower() or p[0].lower().split()[0] in _tpn_lower), None)
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

                    _found_decision_maker = _has_draft or ("decisor" in _ai_response_text and any(word in _ai_response_text for word in ["encontrado", "confirmado", "identificado"]))

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

                    if not _found_decision_maker and not _has_draft:
                        if _is_task_action and _already_searched and _has_useful_history:
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
                        # Força o envio do rascunho
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                "REGRA DE OURO: Você gerou um rascunho de mensagem mas não chamou a ferramenta de envio para aprovação.\n"
                                "O 'Sucesso' da sua tarefa é fazer o card de aprovação aparecer para o João Luccas.\n"
                                "CHAME AGORA: whatsapp_send_message (ou email_send) com o texto do rascunho.\n"
                                "É PROIBIDO terminar o turno apenas com texto quando há um rascunho pronto."
                            ),
                        })
                        continue

                    # ── Interceptor: Histórico encontrado mas rascunho NÃO gerado (OBRIGATÓRIO PARA FOLLOW-UP) ──
                    if not _has_draft_now and not _has_sent_now:
                        _is_followup = any(kw in _first_msg_content.lower() for kw in ["follow-up", "cobrar retorno", "acompanhar", "orçamento"])
                        if _is_followup:
                            _found_history = False
                            # Verifica tanto o histórico quanto os resultados do turno atual
                            all_recent_results = []
                            for _m in messages:
                                _mc = _m.get("content", "")
                                if isinstance(_mc, list):
                                    all_recent_results.extend([_b for _b in _mc if isinstance(_b, dict)])
                            all_recent_results.extend([_b for _b in tool_results if isinstance(_b, dict)])

                            for _b in all_recent_results:
                                if _b.get("type") == "tool_result" and _b.get("tool_name") in ("whatsapp_get_messages", "email_get_contact_history"):
                                    _res_content = str(_b.get("content", "")).lower()
                                    if ("nenhuma mensagem" not in _res_content and 
                                        "0 mensagens" not in _res_content and 
                                        "nenhum e-mail" not in _res_content and
                                        "0 e-mails" not in _res_content):
                                        _found_history = True
                                        break
                            
                            if _found_history:
                                messages.append({"role": "assistant", "content": content})
                                messages.append({
                                    "role": "user",
                                    "content": (
                                        "ATENÇÃO: Você encontrou histórico de comunicação relevante mas NÃO gerou o rascunho de follow-up.\n"
                                        "Para tarefas de follow-up/cobrar retorno, sua missão OBRIGATORIAMENTE deve terminar com um rascunho pronto para envio.\n"
                                        "CHAME AGORA: generate_sales_message para criar a mensagem agressiva/técnica baseada no histórico encontrado.\n"
                                        "É PROIBIDO finalizar a tarefa apenas relatando que encontrou as mensagens."
                                    ),
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
                        or _is_task_action
                        or "Fase final" in _status
                        or "resposta final" in _status.lower()
                        or "responda à pergunta" in _status.lower()
                        or "apresente os" in _status.lower()
                        or "escreva a resposta final" in _status.lower()
                        or "não chame mais ferramentas" in _status.lower()
                        or "regra de ouro" in content.lower()
                        or "parada antecipada" in content.lower()
                    )

                    if not _is_complete and stop_reason == "end_turn" and not tool_use_blocks:
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
                    if not _final_emitted and not _suggest_actions_done(_msgs_with_current) and stop_reason == "end_turn" and not tool_use_blocks:
                        # Emite o dossiê agora e força turno dedicado para suggest_next_actions
                        _final_response = response_text
                        if not _final_response.strip():
                            _has_update_task = any("pipedrive_update_task" in str(m) for m in messages)
                            if _has_update_task:
                                _final_response = "Ação realizada com sucesso! Aqui estão as sugestões de próximos passos:"
                            else:
                                _final_response = "Investigação concluída! Aqui estão as sugestões de próximos passos:"

                        _raw_log(process_id, "agent_final_response", {"response": _final_response})
                        yield _emit({"type": "final", "response": _final_response})
                        _final_emitted = True

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
                # Injetamos ações a partir dos dados reais coletados durante a investigação.
                from datetime import datetime, timedelta
                fallback_actions = []
                today = datetime.now()

                for act in found_activities:
                    fallback_actions.append({
                        "label": f"Concluir atividade pendente · {act['subject']}",
                        "prompt": f"Execute pipedrive_update_task com activity_id={act['id']} e done=true"
                    })

                if found_org:
                    # Detect price objections in messages to customize fallback follow-ups
                    has_price_objection = False
                    objection_keywords = ["caro", "alto", "preço", "preco", "orcamento", "orçamento", "desconto", "concorrencia", "concorrência", "valor"]
                    for _m in messages:
                        _m_content = str(_m.get("content", "")).lower()
                        if any(kw in _m_content for kw in objection_keywords):
                            has_price_objection = True
                            break

                    def _d(delta): return (today + timedelta(days=delta)).strftime("%Y-%m-%d")

                    if has_price_objection:
                        seq_prompt = (
                            f"Execute pipedrive_create_task 5 vezes em sequência para criar o plano de negociação e contorno de objeção de preço with {found_org}"
                            + (f" (deal_id={found_deal_id})" if found_deal_id else "") + ":\n"
                            f"Tarefa 1: subject=\"Estudo interno de margem e engenharia de custos\", task_type=\"task\", due_date=\"{_d(1)}\", org_name=\"{found_org}\", note=\"Analisar viabilidade de concessão de descontos adicionais ou alteração de especificações para caber no orçamento.\"\n"
                            f"Tarefa 2: subject=\"Aviso de revisão de proposta comercial\", task_type=\"task\", due_date=\"{_d(1)}\", org_name=\"{found_org}\", note=\"Enviar mensagem ao contato informando que estamos revisando internamente os valores para apresentar uma alternativa competitiva.\"\n"
                            f"Tarefa 3: subject=\"Enviar proposta comercial revisada\", task_type=\"task\", due_date=\"{_d(3)}\", org_name=\"{found_org}\", note=\"Elaborar e enviar por e-mail ou WhatsApp a proposta com novos preços ou especificações.\"\n"
                            f"Tarefa 4: subject=\"Ligação de acompanhamento consultivo\", task_type=\"call\", due_date=\"{_d(6)}\", org_name=\"{found_org}\", note=\"Ligar para entender o comparativo com a concorrência e o feedback sobre a proposta ajustada.\"\n"
                            f"Tarefa 5: subject=\"Fechamento comercial / alinhamento final\", task_type=\"meeting\", due_date=\"{_d(10)}\", org_name=\"{found_org}\", note=\"Reunião rápida ou ligação para fechar o pedido ou ajustar termos finais de pagamento.\""
                        )
                        lbl = "Criar plano de 5 tarefas de negociação de preço"
                    else:
                        seq_prompt = (
                            f"Execute pipedrive_create_task 5 vezes em sequência para criar o plano de follow-up para agendar reunião with {found_org}"
                            + (f" (deal_id={found_deal_id})" if found_deal_id else "") + ":\n"
                            f"Tarefa 1: subject=\"Follow-up 1: Ligar para {found_org}\", task_type=\"call\", due_date=\"{_d(1)}\", org_name=\"{found_org}\", note=\"Primeira tentativa de contato. Apresentar J.Ferres e propor reunião rápida de 20 min.\"\n"
                            f"Tarefa 2: subject=\"Follow-up 2: Email de apresentação\", task_type=\"task\", due_date=\"{_d(3)}\", org_name=\"{found_org}\", note=\"Enviar e-mail de apresentação propondo reunião. Referenciar último assunto discutido.\"\n"
                            f"Tarefa 3: subject=\"Follow-up 3: Segunda ligação\", task_type=\"call\", due_date=\"{_d(7)}\", org_name=\"{found_org}\", note=\"Segunda tentativa. Perguntar se recebeu o e-mail e verificar disponibilidade.\"\n"
                            f"Tarefa 4: subject=\"Follow-up 4: Canal alternativo (LinkedIn)\", task_type=\"task\", due_date=\"{_d(10)}\", org_name=\"{found_org}\", note=\"Tentar contato via LinkedIn ou outro canal para propor reunião.\"\n"
                            f"Tarefa 5: subject=\"Follow-up 5: Tentativa final\", task_type=\"call\", due_date=\"{_d(14)}\", org_name=\"{found_org}\", note=\"Última tentativa antes de arquivar. Propor horário específico para reunião de 30 min.\""
                        )
                        lbl = "Criar sequência de 5 follow-ups para reunião"

                    fallback_actions.append({
                        "label": lbl,
                        "prompt": seq_prompt,
                    })

                if fallback_actions:
                    _raw_log(process_id, "agent_fallback_suggested_actions", {"actions": fallback_actions})
                    yield _emit({
                        "type": "suggested_actions",
                        "actions": fallback_actions
                    })

            if not _final_emitted:
                _raw_log(process_id, "agent_final_response", {"response": response_text})
                yield _emit({"type": "final", "response": response_text})
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

            tool_meta = TOOLS[tool_name]

            _INVESTIGATION_REQUIRED = {"whatsapp_send_message", "email_send", "email_reply", "pipedrive_create_task", "pipedrive_create_person", "suggest_next_actions"}
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
                except Exception:
                    _write_allowed = True

                if not _write_allowed:
                    _block_reason = (
                        "criar tarefas embasadas" if tool_name == "pipedrive_create_task"
                        else "criar novos contatos" if tool_name == "pipedrive_create_person"
                        else "sugerir próximos passos comerciais" if tool_name == "suggest_next_actions"
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

                if tool_name in _DEDUP_READ_TOOLS:
                    if tool_name in _DEDUP_PIPEDRIVE:
                        _tool_call_history.add(tool_name)
                    else:
                        _exec_contact_id = (
                            tool_args.get("contact") or
                            tool_args.get("contact_name") or
                            tool_args.get("org_name") or ""
                        ).lower().strip()
                        _tool_call_history.add(f"{tool_name}:{_exec_contact_id}")

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
                yield _emit({"type": "tool_result", "call_id": first_call_id, "tool": tool_name, "summary": summary, "ok": ok})
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
                                _act.get("type", ""), _act.get("note", "")
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
                                _act.get("type", ""), _act.get("note", "")
                            ),
                        })
                    if _pd_actions:
                        yield _emit({"type": "suggested_actions", "actions": _pd_actions})

                sanitized = _sanitize_result(tool_name, tool_result)
                raw_content = json.dumps(sanitized, ensure_ascii=False)
                _max_content = 4000 if tool_name in ("pipedrive_get_all_activities", "email_get_inbox", "email_get_contact_history") else 2000
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
            tool_args = block["input"]

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
            preview = tool_args.get("message") or tool_args.get("body") or json.dumps(tool_args, ensure_ascii=False)[:120]

            yield _emit({
                "type": "confirmation_required",
                "action_id": action_id,
                "tool": tool_name,
                "label": confirm_label,
                "preview": str(preview),
                "args": tool_args,
            })
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
