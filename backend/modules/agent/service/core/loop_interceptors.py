"""
modules.agent.service.core.loop_interceptors
============================================
Interceptores de fluxo comerciais, validações e travas do agente.
"""
from __future__ import annotations
import os
import re
import json
from pathlib import Path
from core.observability.logging_config import get_logger

log = get_logger(__name__)

async def intercept_pre_execution(
    tool_name: str,
    tool_args: dict,
    tool_id: str,
    messages: list,
    org_id: int | None,
    has_local_decision_maker: bool,
    session_task_person: str | None,
    is_task_action: bool,
    is_find_decisor_task: bool,
    query_type: str,
    direct_action: bool,
    active_skill: Any,
    ctx: dict,
    tool_use_blocks: list,
    seller_name: str,
    company_name: str,
    tool_call_history: set[str],
) -> dict | None:
    """
    Executa os interceptores antes de chamar uma ferramenta.
    Retorna um dict (tool_result estruturado) se a ação for bloqueada ou redirecionada.
    Retorna None se a ação puder prosseguir.
    """

    # 1. open_hierarchy_drawer redundancy check
    if tool_name == "open_hierarchy_drawer" and has_local_decision_maker:
        log.info("agent.interceptor.hierarchy_drawer_blocked", org_name=tool_args.get("org_name"))
        return {
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
        }
    # 1.5 suggest_next_actions block when draft is pending
    if tool_name == "suggest_next_actions":
        _last_generate_idx = -1
        _last_send_idx = -1
        _idx = 0
        _last_tool_result_content = ""
        for _m in messages:
            _mc = _m.get("content", "")
            if isinstance(_mc, list):
                for _b in _mc:
                    if isinstance(_b, dict):
                        _name = _b.get("tool_name") or _b.get("name")
                        if _name == "generate_sales_message":
                            _last_generate_idx = _idx
                        elif _name in ("email_send", "whatsapp_send_message"):
                            _last_send_idx = _idx
                        if _b.get("type") == "tool_result":
                            _last_tool_result_content = str(_b.get("content", ""))
            _idx += 1
            
        if _last_generate_idx > _last_send_idx:
            log.info("agent.interceptor.suggest_next_actions_blocked", reason="draft_pending")
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "tool_name": tool_name,
                "content": (
                    "AÇÃO BLOQUEADA: Você gerou um rascunho de mensagem mas não o enviou para aprovação do usuário.\n"
                    "É PROIBIDO chamar `suggest_next_actions` enquanto o rascunho estiver pendente.\n"
                    "CHAME AGORA a ferramenta de envio (email_send ou whatsapp_send_message) correspondente ao rascunho gerado."
                ),
                "is_error": True,
            }
            
        if "AVISO DE SEGURANÇA" in _last_tool_result_content and "discover_and_validate_email" in _last_tool_result_content:
            log.info("agent.interceptor.suggest_next_actions_blocked", reason="security_warning_pending")
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "tool_name": tool_name,
                "content": (
                    "AÇÃO BLOQUEADA: Você recebeu um AVISO DE SEGURANÇA no passo anterior que ainda não foi resolvido.\n"
                    "CHAME AGORA a ferramenta `discover_and_validate_email` conforme instruído, antes de sugerir próximos passos."
                ),
                "is_error": True,
            }

    # 2. email_send / email_reply validation & enrichment
    if tool_name in ("email_send", "email_reply"):
        # Fallbacks for LLM hallucinations
        if "contact_email" in tool_args and not tool_args.get("to"):
            tool_args["to"] = tool_args["contact_email"]
        if "message" in tool_args and not tool_args.get("body"):
            tool_args["body"] = tool_args["message"]

        _target_email = tool_args.get("to") or ""
        _contact_name = tool_args.get("contact_name") or ""

        # Auto-enrich: Adiciona assinatura e apresentação automaticamente
        try:
            # Força a Apresentação se não estiver definida
            if tool_name == "email_send" and not tool_args.get("attachment_name"):
                tool_args["attachment_name"] = "apresentacao_linkb2b"

            # Embutir assinatura no corpo do email
            _body = tool_args.get("body") or ""
            if "<!-- SIGNATURE_START -->" not in _body and "J.Ferres" not in _body:
                sig_path = ctx.get("signature_path")
                if sig_path and os.path.exists(sig_path):
                    try:
                        import base64 as _base64
                        ext = Path(sig_path).suffix.lower().replace(".", "")
                        if ext in ("png", "jpg", "jpeg", "gif"):
                            with open(sig_path, "rb") as f:
                                b64_data = _base64.b64encode(f.read()).decode()
                            mime = f"image/{ext}" if ext != "jpg" else "image/jpeg"
                            sig_html = f'<br><br><!-- SIGNATURE_START --><img src="data:{mime};base64,{b64_data}" style="max-width: 400px; height: auto;" /><!-- SIGNATURE_END -->'
                            if sig_html not in _body:
                                tool_args["body"] = _body + sig_html
                    except Exception as sig_err:
                        log.warning(f"Erro ao embutir assinatura em loop_interceptors: {sig_err}")
                else:
                    sig_text = f"<br><br>--<br><b>{seller_name}</b><br>Equipe Comercial {company_name}"
                    if sig_text not in _body:
                        tool_args["body"] = _body + sig_text
        except Exception as enrich_err:
            log.warning(f"Erro ao enriquecer email com assinatura/apresentação: {enrich_err}")

        # Check if already validated in session
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

        _looks_like_pattern = _target_email and ("." in _target_email.split("@")[0] or "_" in _target_email.split("@")[0])
        if not _already_validated and (_looks_like_pattern or not _target_email):
            log.info("agent.interceptor.email_validation_forced", email=_target_email)
            _auto_validated = False
            _auto_validated_email = None
            try:
                from modules.agent.service.tools.intelligence import exec_discover_and_validate_email
                _domain = ""
                if org_id:
                    from modules.crm.service.pipedrive_service import pipedrive_service
                    org_details = await pipedrive_service.get_organization_details(org_id)
                    if isinstance(org_details, dict):
                        _domain = org_details.get("domain") or org_details.get("website") or ""

                if not _domain and org_id:
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
                        log.warning(f"E-mail {_auto_validated_email} estimado por heuristica (SMTP result: {_smtp_result}).")
                    tool_args["to"] = _auto_validated_email
                    _auto_validated = True
                    _already_validated = True
            except Exception as val_err:
                log.warning(f"Falha na validação inline automática: {val_err}")

            if not _auto_validated:
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": (
                        f"AVISO DE SEGURANÇA: O e-mail '{_target_email}' para o contato '{_contact_name}' "
                        "precisa ser validado antes do envio real para evitar que caia em SPAM ou retorne erro.\n\n"
                        "Por favor, chame a ferramenta `discover_and_validate_email` no próximo passo para confirmar o e-mail.\n"
                        f"Chame: discover_and_validate_email(contact_name='{_contact_name}', org_name='{tool_args.get('org_name', '')}', person_id=<SE_SOUBER_PASSE_AQUI>)"
                    ),
                    "is_error": False,
                }

    # 3. pipedrive_update_task done check
    if tool_name == "pipedrive_update_task":
        _done_val = tool_args.get("done")
        _is_marking_done = _done_val is True or str(_done_val).lower() in ("true", "1", "yes", "y")
        if _is_marking_done:
            # Reconstrói a instrução textual das msgs do usuário
            _user_instructions_clean = []
            for _m in messages:
                if _m.get("role") == "user":
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        _text_content = " ".join(_b.get("text", "") for _b in _mc if isinstance(_b, dict) and _b.get("type") == "text")
                        if _text_content.strip():
                            _user_instructions_clean.append(re.sub(r'\[.*?\]', '', _text_content, flags=re.DOTALL))
                    elif isinstance(_mc, str):
                        _user_instructions_clean.append(re.sub(r'\[.*?\]', '', _mc, flags=re.DOTALL))
            _user_instructions_text = " ".join(_user_instructions_clean).lower()
            
            _is_comm_task = (not is_find_decisor_task) and any(kw in _user_instructions_text for kw in ["enviar", "email", "whatsapp", "mensagem", "mandar", "falar", "apresentação", "proposta", "follow", "otimização"])
            if _is_comm_task:
                _comm_proposed = False
                _COMM_TOOLS = {"whatsapp_send_message", "email_send", "email_reply", "generate_sales_message"}
                for _m in messages:
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict) and (_b.get("tool_name") or _b.get("name")) in _COMM_TOOLS:
                                _comm_proposed = True
                                break
                if not _comm_proposed:
                    for _b in tool_use_blocks:
                        if _b.get("name") in _COMM_TOOLS:
                            _comm_proposed = True
                if not _comm_proposed:
                    log.info("agent.interceptor.value_task_close_blocked", tool=tool_name, reason="no_comm_found")
                    return {
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
                    }

    # 4. Target locking
    if session_task_person and is_task_action:
        _tpn_lower = session_task_person.lower()
        if tool_name == "evaluate_prospects":
            log.info("agent.interceptor.target_locked.eval_blocked", person=session_task_person)
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "tool_name": tool_name,
                "content": (
                    f"AÇÃO BLOQUEADA: A tarefa atual é para um contato específico: '{session_task_person}'. "
                    "Não é necessário avaliar outros perfis. PROSSIGA imediatamente para a geração do rascunho de e-mail/WhatsApp "
                    f"com '{session_task_person}' usando a ferramenta generate_sales_message ou chame a ferramenta de envio correspondente."
                ),
                "is_error": False,
            }
        if tool_name in ("whatsapp_get_messages", "email_get_contact_history"):
            _target_args = (tool_args.get("contact") or tool_args.get("contact_name") or tool_args.get("contact_email") or tool_args.get("email") or "").lower()
            _is_different_person = _tpn_lower.split()[0] not in _target_args
            if _is_different_person:
                log.info("agent.interceptor.target_locked.search_blocked", target=session_task_person, requested=_target_args)
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": (
                        f"AÇÃO BLOQUEADA: Foco no Alvo. A tarefa é para '{session_task_person}'. "
                        f"É proibido investigar '{_target_args}' enquanto a tarefa principal não for concluída. "
                        f"Busque apenas o histórico de '{session_task_person}'."
                    ),
                    "is_error": False,
                }

    # 5. suggest_next_actions block
    if tool_name == "suggest_next_actions" and is_task_action:
        _user_instructions_clean = []
        for _m in messages:
            if _m.get("role") == "user":
                _mc = _m.get("content", "")
                if isinstance(_mc, list):
                    _text_content = " ".join(_b.get("text", "") for _b in _mc if isinstance(_b, dict) and _b.get("type") == "text")
                    if _text_content.strip():
                        _user_instructions_clean.append(re.sub(r'\[.*?\]', '', _text_content, flags=re.DOTALL))
                elif isinstance(_mc, str):
                    _user_instructions_clean.append(re.sub(r'\[.*?\]', '', _mc, flags=re.DOTALL))
        _user_instructions_text = " ".join(_user_instructions_clean).lower()
        _is_comm_task = (not is_find_decisor_task) and any(kw in _user_instructions_text for kw in ["enviar", "email", "whatsapp", "mensagem", "mandar", "falar", "apresentação", "proposta", "follow", "otimização"])
        
        if _is_comm_task:
            _has_sent_global = False
            _SEND_TOOLS = {"whatsapp_send_message", "email_send", "email_reply"}
            for _m in messages:
                _mc = _m.get("content", "")
                if isinstance(_mc, list):
                    for _b in _mc:
                        if isinstance(_b, dict) and (_b.get("tool_name") or _b.get("name")) in _SEND_TOOLS:
                            _has_sent_global = True
                            break
            if not _has_sent_global:
                log.info("agent.interceptor.suggestion_blocked_comm_pending", tool=tool_name)
                return {
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
                }

    # 6. P phase checks
    _INVESTIGATION_REQUIRED = {"whatsapp_send_message", "email_send", "email_reply", "pipedrive_create_task", "pipedrive_create_person", "suggest_next_actions", "prepare_live_coaching_session"}
    if tool_name in _INVESTIGATION_REQUIRED:
        from modules.agent.service.core.phase_tracker import _build_phase_status
        try:
            _phase = _build_phase_status(messages, query_type=query_type, org_id=org_id)
            context_mode_active = False
            command_mode_active = False
            for msg in messages:
                if msg.get("role") == "user":
                    _content = str(msg.get("content", "")).lower()
                    if "[modo contexto" in _content:
                        context_mode_active = True
                    _is_task_crm = any(s.lower() in _content for s in [
                        "execute a seguinte atividade do crm", "atividade #",
                        "execute agora, começando pelo raciocínio",
                        "execute estas etapas em ordem", "etapa 1 — pipedrive",
                        "investigue a empresa"
                    ])
                    if not _is_task_crm:
                        if re.search(r'\b(execute|realizar|realize|marque|crie|adicione|atualize|altere|mande|envie|agende|ligue)\b', _content):
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
                or is_task_action 
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
                    _local_missing = {"pipedrive_get_org", "pipedrive_get_persons"} - _local_called_ctx
                if _local_missing:
                    _write_allowed = False
                
                _passed_phone = str(tool_args.get("phone", "")).strip()
                if not _passed_phone or _passed_phone.lower() == "nenhum":
                    return {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "tool_name": tool_name,
                        "content": f"AÇÃO BLOQUEADA: Contato sem telefone válido. CHAME A FERRAMENTA 'find_company_contact' para buscar o número antes de preparar a ligação.",
                        "is_error": True,
                    }
        except Exception:
            _write_allowed = True

        if not _write_allowed:
            if tool_name == "suggest_next_actions":
                pass
            elif tool_name == "prepare_live_coaching_session":
                _missing_names = ", ".join(f"'{t}'" for t in _local_missing)
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": f"AÇÃO BLOQUEADA: Você deve executar as ferramentas fundamentais ({_missing_names}) antes de gerar o plano de voo da ligação.",
                    "is_error": True,
                }
            else:
                _block_reason = (
                    "criar tarefas embasadas" if tool_name == "pipedrive_create_task"
                    else "criar novos contatos" if tool_name == "pipedrive_create_person"
                    else "enviar mensagens ou emails"
                )
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "content": (
                        f"BLOQUEADO: complete a investigação de comunicação (whatsapp_get_messages e email_get_contact_history) antes de {_block_reason}. "
                        + _phase
                    ),
                    "is_error": False,
                }

    # 7. open_ligacao_view checks
    if tool_name == "open_ligacao_view":
        _passed_phone = str(tool_args.get("phone", "")).strip()
        if not _passed_phone or _passed_phone.lower() == "nenhum":
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "tool_name": tool_name,
                "content": f"AÇÃO BLOQUEADA: Contato sem telefone válido. CHAME A FERRAMENTA 'find_company_contact' para buscar o número na Receita Federal antes de invocar a ligação.",
                "is_error": True,
            }

    # 8. generate_dossier block
    if tool_name == "generate_dossier":
        from modules.agent.service.core.phase_tracker import _build_phase_status
        try:
            _gd_phase = _build_phase_status(messages, query_type=query_type, org_id=org_id)
            _gd_allowed = (
                is_task_action
                or "Todas as fontes foram investigadas" in _gd_phase
                or "Fase final" in _gd_phase
                or query_type not in ("agent_workflow", "deal_status")
            )
        except Exception:
            _gd_allowed = True
        if not _gd_allowed:
            return {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "tool_name": tool_name,
                "content": (
                    "BLOQUEADO: complete todas as buscas de comunicação antes de consolidar. "
                    + _gd_phase
                ),
                "is_error": False,
            }

    return None


async def intercept_post_llm_turn(
    messages: list,
    content: list,
    response_text: str,
    query_type: str,
    org_id: int | None,
    direct_action: bool,
    is_task_action: bool,
    is_find_decisor_task: bool,
    first_msg_content_clean: str,
    first_msg_content: str,
    session_task_person: str | None,
    persons_with_wa: list,
    persons_with_email: list,
    has_local_decision_maker: bool,
    iteration: int,
    max_iters: int,
    process_id: str,
    stop_reason: str,
    tool_use_blocks: list,
    collected_tool_summaries: list,
    active_skill: Any,
    ctx: dict,
    final_emitted: bool,
) -> tuple[bool, str | None, bool, str | None]:
    """
    Analisa o estado pós-resposta da IA.
    Retorna uma tupla:
      (should_continue: bool, final_response: str | None, updated_final_emitted: bool, cached_final_response: str | None)
    Se should_continue for True, indica que o loop do agente deve dar `continue` para a próxima iteração.
    """
    from modules.agent.service.core.phase_tracker import _build_phase_status
    from modules.agent.service.core.loop_utils import _suggest_actions_done
    from modules.agent.service.core._activity_prompts import _build_task_action_prompt
    
    # ── MODO EXECUÇÃO DIRETA E TAREFA CRM ──
    if stop_reason in ("end_turn", "stop") or not tool_use_blocks:
        # Encontra o índice da última mensagem do usuário para escopar as verificações à tarefa atual
        _last_user_idx = 0
        for _i, _m in enumerate(messages):
            if _m.get("role") == "user":
                _last_user_idx = _i
        _current_task_history = messages[_last_user_idx:] + [{"role": "assistant", "content": content}]

        if direct_action and is_task_action:
            _CTX_TOOLS = {
                "deep_company_investigation", "pipedrive_get_org", "pipedrive_get_persons", "evaluate_prospects", "pipedrive_get_deals",
                "pipedrive_get_activities", "whatsapp_get_messages", "email_get_contact_history",
            }
            # Detecta quais ferramentas de contexto já foram chamadas no histórico
            _called_ctx = set()
            for _m in _current_task_history:
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
                _CORE_CTX = {"pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals", "pipedrive_get_activities"}
                _CTX_ORDER = [
                    "pipedrive_get_org", "pipedrive_get_persons", "pipedrive_get_deals",
                    "pipedrive_get_activities", "whatsapp_get_messages", "email_get_contact_history",
                ]

            # Se o plano de prospecção já existe no banco local para esta organização,
            # as ferramentas de enriquecimento e ranking estratégico são consideradas opcionais
            # e não são forçadas pelo interceptor.
            _has_prospecting_plan = False
            if org_id:
                try:
                    from core.infra.database import async_session
                    from models.organization import Organization
                    from sqlalchemy import select
                    async with async_session() as session:
                        _stmt = select(Organization).where((Organization.id == org_id) | (Organization.pipedrive_id == org_id))
                        _res = await session.execute(_stmt)
                        _org = _res.scalar_one_or_none()
                        if _org and _org.prospecting_context and len(_org.prospecting_context.strip()) > 100:
                            _has_prospecting_plan = True
                except Exception:
                    pass

            if _has_prospecting_plan:
                _CORE_CTX = _CORE_CTX - {"deep_company_investigation", "evaluate_prospects"}
                _CTX_ORDER = [t for t in _CTX_ORDER if t not in ("deep_company_investigation", "evaluate_prospects")]

            if session_task_person:
                _CORE_CTX.discard("evaluate_prospects")
                if "evaluate_prospects" in _CTX_ORDER:
                    _CTX_ORDER.remove("evaluate_prospects")

            _missing_core = _CORE_CTX - _called_ctx
            _next_tool = next((t for t in _CTX_ORDER if t not in _called_ctx), None)

            if _missing_core and _next_tool and iteration < max_iters - 2:
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
                return True, None, final_emitted, None

            # Detecta se já gerou rascunho de mensagem
            _has_draft = False
            for _m in _current_task_history:
                _mc = _m.get("content", "")
                if isinstance(_mc, list):
                    for _b in _mc:
                        if isinstance(_b, dict) and (_b.get("tool_name") == "generate_sales_message" or (_b.get("type") == "tool_use" and _b.get("name") == "generate_sales_message")):
                            _has_draft = True
                            break
                if _has_draft: break

            # Interceptor: Email obrigatório para contato-tarefa
            if session_task_person and is_task_action and not _has_draft and iteration < max_iters - 2:
                _tpn_first = session_task_person.split()[0].lower()
                _task_wa_done = False
                _task_email_done = False
                for _hm in _current_task_history:
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
                                    or _tpn_first in (_inp.get("contact_email") or "").lower()
                                    or _tpn_first in (_inp.get("email") or "").lower()
                                    or _tpn_first in (_inp.get("org_name") or "").lower()):
                                _task_email_done = True
                if _task_wa_done and not _task_email_done:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Você já verificou o WhatsApp de {session_task_person}. "
                            f"OBRIGATÓRIO: verifique também o e-mail antes de finalizar — "
                            f"chame email_get_contact_history com contact_name='{session_task_person}' "
                            f"para ter o histórico completo de comunicações."
                        ),
                    })
                    return True, None, final_emitted, None

            # Interceptor: Varredura de contatos adicionais
            if not _has_draft and iteration < max_iters - 2:
                _skip_others = False
                if session_task_person and is_task_action:
                    _tpn_f = session_task_person.lower().split()[0]
                    _target_searched = False
                    for _m in _current_task_history:
                        _mc = _m.get("content", "")
                        if not isinstance(_mc, list): continue
                        for _b in _mc:
                            if isinstance(_b, dict) and _b.get("type") == "tool_use":
                                _tn_s = _b.get("name", "")
                                _ta_s = _b.get("input") or {}
                                if _tn_s == "whatsapp_get_messages" and _tpn_f in str(_ta_s.get("contact", "")).lower():
                                    _target_searched = True
                                if _tn_s == "email_get_contact_history" and (_tpn_f in str(_ta_s.get("contact_name", "")).lower() or _tpn_f in str(_ta_s.get("contact_email", "")).lower() or _tpn_f in str(_ta_s.get("email", "")).lower() or _tpn_f in str(_ta_s.get("org_name", "")).lower()):
                                    _target_searched = True
                                if _tn_s == "batch_communication_search":
                                    _c_str = str(_ta_s.get("contacts", ""))
                                    _o_str = str(_ta_s.get("org_name", ""))
                                    if _tpn_f in _c_str.lower() or _tpn_f in _o_str.lower():
                                        _target_searched = True
                    if _target_searched:
                        _skip_others = True

                if not _skip_others:
                    _tpn_lower = session_task_person.lower() if session_task_person else ""
                    _task_entry_wa = None
                    for p in persons_with_wa:
                        if _tpn_lower and (_tpn_lower in p[0].lower() or p[0].lower().split()[0] in _tpn_lower):
                            _task_entry_wa = p
                            break
                    if _task_entry_wa and persons_with_wa.index(_task_entry_wa) != 0:
                        persons_with_wa.remove(_task_entry_wa)
                        persons_with_wa.insert(0, _task_entry_wa)

                    _task_entry_email = None
                    for p in persons_with_email:
                        if _tpn_lower and (_tpn_lower in p[0].lower() or p[0].lower().split()[0] in _tpn_lower):
                            _task_entry_email = p
                            break
                    if _task_entry_email and persons_with_email.index(_task_entry_email) != 0:
                        persons_with_email.remove(_task_entry_email)
                        persons_with_email.insert(0, _task_entry_email)

                # Busca quais contatos já foram buscados
                _already_searched = set()
                for _m in _current_task_history:
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
                            _cn = (_ta2.get("contact_name") or _ta2.get("contact_email") or _ta2.get("email") or _ta2.get("org_name") or "").lower()
                            if _cn: _already_searched.add(_cn)
                        elif _tn2 == "batch_communication_search":
                            _contacts = _ta2.get("contacts") or []
                            for _c in _contacts:
                                if _c.get("name"): _already_searched.add(_c["name"].lower())
                            _on = (_ta2.get("org_name") or "").lower()
                            if _on: _already_searched.add(_on)

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
                            except Exception: pass

                _next_unsearched_wa = None
                for _pname, _pphone in persons_with_wa:
                    if _pname.lower() not in _already_searched and _pname.split()[0].lower() not in _already_searched:
                        _next_unsearched_wa = (_pname, _pphone)
                        break

                _next_unsearched_email = None
                for _pname, _pemail in persons_with_email:
                    if _pname.lower() not in _already_searched and _pname.split()[0].lower() not in _already_searched:
                        _next_unsearched_email = (_pname, _pemail)
                        break

                _ai_response_text = " ".join(b.get("text", "") for b in content if b.get("type") == "text").lower()
                _has_sent_check = False
                _has_flight_plan = False
                for _m in _current_task_history:
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict):
                                if _b.get("tool_name") == "generate_sales_message" or (_b.get("type") == "tool_use" and _b.get("name") == "generate_sales_message"):
                                    _has_sent_check = True
                                if _b.get("tool_name") == "prepare_live_coaching_session" or (_b.get("type") == "tool_use" and _b.get("name") == "prepare_live_coaching_session"):
                                    _has_flight_plan = True

                _found_decision_maker = _has_sent_check or _has_flight_plan or ("decisor" in _ai_response_text and any(word in _ai_response_text for word in ["encontrado", "confirmado", "identificado"]))
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

                _COMM_KEYWORDS = ["enviar", "email", "whatsapp", "mensagem", "mandar", "falar", "apresentação", "proposta", "follow"]
                _is_comm_task = any(k in first_msg_content_clean.lower() for k in _COMM_KEYWORDS)
                _ligacao_finalizada = any(
                    "ALERTA DE CONTEXTO: LIGAÇÃO FINALIZADA" in (
                        _m.get("content", "") if isinstance(_m.get("content"), str) 
                        else json.dumps(_m.get("content", ""))
                    )
                    for _m in messages
                )
                _is_call_task = any(k in first_msg_content_clean.lower() for k in ["ligação", "ligar", "telefonar", "telefone"]) and not _ligacao_finalizada

                if not _found_decision_maker and not _has_draft and not _has_flight_plan:
                    if (_is_task_action or _is_call_task) and _already_searched and _has_useful_history:
                        pass
                    elif _next_unsearched_wa:
                        _first_name = _next_unsearched_wa[0].split()[0]
                        _phone_val = _next_unsearched_wa[1]
                        _phone_param = f", phone='{_phone_val}'" if "@" not in _phone_val else ""
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
                        return True, None, final_emitted, None
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
                        return True, None, final_emitted, None

                # Interceptor: Mapeador de hierarquia
                _hierarchy_already_called = any(
                    isinstance(_b, dict) and (
                        (_b.get("type") == "tool_use" and _b.get("name") == "open_hierarchy_drawer") or
                        (_b.get("type") == "tool_result" and _b.get("tool_name") == "open_hierarchy_drawer")
                    )
                    for _m in messages + [{"role": "assistant", "content": content}]
                    for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
                )
                if (
                    is_find_decisor_task
                    and not persons_with_wa
                    and not persons_with_email
                    and not _missing_core
                    and not _hierarchy_already_called
                    and not has_local_decision_maker
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
                    return True, None, final_emitted, None

                # Interceptor: ICP evaluation
                if has_local_decision_maker and not session_task_person:
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
                        return True, None, final_emitted, None

            # Interceptor: Rascunho gerado mas não enviado
            if is_task_action:
                _last_draft_idx = -1
                _last_send_idx = -1
                _last_validation_idx = -1
                _validation_failed = False
                _SEND_TOOLS = {"whatsapp_send_message", "email_send", "email_reply"}
                
                _idx = 0
                for _m in _current_task_history:
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if not isinstance(_b, dict): continue
                            _tn_check = _b.get("tool_name") or _b.get("name")
                            if _tn_check == "generate_sales_message":
                                _last_draft_idx = _idx
                            elif _tn_check in _SEND_TOOLS:
                                _last_send_idx = _idx
                            elif _tn_check == "discover_and_validate_email":
                                _last_validation_idx = _idx
                            
                            # Track if validation tool returned an error or failure
                            if _b.get("type") == "tool_result" and _b.get("tool_name") == "discover_and_validate_email":
                                _res_text = str(_b.get("content", "")).lower()
                                if "error" in _res_text or "nenhum e-mail" in _res_text or "forneça o nome" in _res_text or "false" in _res_text:
                                    _validation_failed = True
                                else:
                                    _validation_failed = False
                    _idx += 1
                
                _has_draft_now = _last_draft_idx >= 0
                _has_sent_now = _last_send_idx > _last_draft_idx and _last_send_idx > _last_validation_idx
                
                if _has_draft_now and not _has_sent_now and not (_last_validation_idx > _last_draft_idx and _validation_failed):
                    _att_name = ""
                    _draft_channel = ""
                    for _m in _current_task_history:
                        _mc = _m.get("content", "")
                        if isinstance(_mc, list):
                            for _b in _mc:
                                if isinstance(_b, dict) and _b.get("tool_name") == "generate_sales_message":
                                    try:
                                        _rd = json.loads(_b.get("content", "{}"))
                                        _att_name = _rd.get("attachment_name") or ""
                                        _draft_channel = _rd.get("channel") or ""
                                    except: pass

                    _suggested_tool = "whatsapp_send_message" if _draft_channel == "whatsapp" else "email_send" if _draft_channel == "email" else "a ferramenta de envio correspondente (email_send ou whatsapp_send_message)"

                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            "REGRA DE OURO: Você gerou um rascunho de mensagem mas a ferramenta de envio final AINDA não foi chamada com sucesso.\n"
                            "(Se você tentou enviar antes, mas recebeu um aviso para validar o e-mail, e a validação agora foi concluída com sucesso, VOCÊ DEVE CHAMAR A FERRAMENTA DE ENVIO NOVAMENTE COM O E-MAIL VALIDADO).\n"
                            "O 'Sucesso' da sua tarefa é fazer o card de aprovação aparecer para o João Luccas.\n"
                            f"CHAME AGORA: {_suggested_tool} com o texto do rascunho"
                            + (f" e attachment_name='{_att_name}'" if _att_name else "") + ".\n"
                            "É PROIBIDO terminar o turno apenas com texto quando há um rascunho pronto."
                        ),
                    })
                    return True, None, final_emitted, None

                # Interceptor: AVISO DE SEGURANÇA pendente
                _has_security_warning = False
                _has_validation_called = False
                for _m in _current_task_history:
                    _mc = _m.get("content", "")
                    if isinstance(_mc, list):
                        for _b in _mc:
                            if isinstance(_b, dict):
                                _tn = _b.get("tool_name") or _b.get("name")
                                if _b.get("type") == "tool_result" and "AVISO DE SEGURANÇA" in str(_b.get("content", "")):
                                    _has_security_warning = True
                                    _has_validation_called = False # Reseta se houver um novo aviso
                                elif _tn == "discover_and_validate_email":
                                    _has_validation_called = True
                                    
                if _has_security_warning and not _has_validation_called and stop_reason in ("end_turn", "stop") and not tool_use_blocks:
                    log.info("agent.interceptor.loop_end_blocked", reason="security_warning_pending")
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            "REGRA DE OURO: Você recebeu um AVISO DE SEGURANÇA no passo anterior que ainda não foi resolvido.\n"
                            "O e-mail precisa ser validado ANTES de prosseguir.\n"
                            "CHAME AGORA a ferramenta `discover_and_validate_email` com os dados do contato e não pare a investigação."
                        ),
                    })
                    return True, None, final_emitted, None

                # Interceptor: Ligação call task flow
                _COMM_KEYWORDS = ["enviar", "email", "whatsapp", "mensagem", "mandar", "falar", "apresentação", "proposta", "follow"]
                _is_comm_task = any(k in first_msg_content_clean.lower() for k in _COMM_KEYWORDS)
                _ligacao_finalizada = any(
                    "ALERTA DE CONTEXTO: LIGAÇÃO FINALIZADA" in (
                        _m.get("content", "") if isinstance(_m.get("content"), str) 
                        else json.dumps(_m.get("content", ""))
                    )
                    for _m in messages
                )
                _is_call_task = any(k in first_msg_content_clean.lower() for k in ["ligação", "ligar", "telefonar", "telefone"]) and not _ligacao_finalizada

                if _is_call_task and iteration < max_iters - 2:
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
                    _ligacao_view_called = any(
                        isinstance(_b, dict) and (
                            (_b.get("type") == "tool_use" and _b.get("name") == "open_ligacao_view") or
                            (_b.get("type") == "tool_result" and _b.get("tool_name") == "open_ligacao_view")
                        )
                        for _m in messages + [{"role": "assistant", "content": content}]
                        for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
                    )

                    _has_phone = len(persons_with_wa) > 0 or _find_contact_called
                    _extracted_phone = ""
                    for _m in _current_task_history:
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

                    if _has_phone and _coaching_called and not _ligacao_view_called:
                        _fp_to_pass = {}
                        for _m in reversed(_current_task_history):
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

                        if _fp_to_pass:
                            _p_name = session_task_person or (persons_with_wa[0][0] if persons_with_wa else "o contato")
                            _p_phone = persons_with_wa[0][1] if persons_with_wa else (_extracted_phone or "3537311491")

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
                            return True, None, final_emitted, None

                    if _has_phone and not _coaching_called and not _ligacao_view_called:
                        _p_name = persons_with_wa[0][0] if persons_with_wa else (session_task_person or "o contato")
                        _p_phone = persons_with_wa[0][1] if persons_with_wa else (_extracted_phone or "3537311491")

                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"SINAL DE EXECUÇÃO: O telefone de '{_p_name}' já foi identificado ({_p_phone}). "
                                "PARE qualquer investigação adicional (E-mail, OSINT, Dossiê). "
                                "OBRIGATÓRIO: Chame `prepare_live_coaching_session` AGORA para gerar o roteiro e abrir a ligação."
                            ),
                        })
                        return True, None, final_emitted, None

                    _contact_has_no_phone = _persons_called and not persons_with_wa
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
                        return True, None, final_emitted, None

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
                     return True, None, final_emitted, None

                # Interceptor: Followup history missing message draft trigger
                if not _has_draft_now and not _has_sent_now:
                    _is_followup = any(kw in first_msg_content_clean.lower() for kw in ["follow-up", "cobrar retorno", "acompanhar", "orçamento"])
                    if _is_followup:
                        _found_history = False
                        for _hm in _current_task_history:
                            _mc = _hm.get("content", "")
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
                            return True, None, final_emitted, None

            # Interceptor: Anti-questionamento de nome de empresa
            _ai_text_full = " ".join(b.get("text", "") for b in content if b.get("type") == "text").lower()
            if "confirmar o nome da empresa" in _ai_text_full or "qual o nome da empresa" in _ai_text_full:
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
                    return True, None, final_emitted, None

        # Proteção contra parada prematura em ligações com telefones encontrados na busca
        if "parada antecipada" in response_text.lower() and iteration < max_iters - 2:
            _search_attempted = any(
                isinstance(_b, dict) and (_b.get("name") == "find_company_contact" or _b.get("tool_name") == "find_company_contact")
                for _m in _current_task_history
                for _b in (_m.get("content") if isinstance(_m.get("content"), list) else [])
            )
            _phone_found_now = False
            for _m in _current_task_history:
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
                return True, None, final_emitted, None

        if direct_action and not is_task_action:
            return False, response_text, final_emitted, None

        # Interceptor: Anti-permissão
        _PERMISSION_PHRASES = [
            "você gostaria", "gostaria de verificar", "gostaria de buscar",
            "deseja continuar", "deseja verificar", "posso verificar",
            "posso buscar", "posso investigar", "quer que eu",
            "para prosseguir", "preciso de mais informações",
            "você prefere", "prefere que eu",
        ]
        _resp_lower = response_text.lower()
        _is_asking_permission = any(p in _resp_lower for p in _PERMISSION_PHRASES)

        if _is_asking_permission and iteration < max_iters - 2:
            messages.append({"role": "assistant", "content": content})
            try:
                _status = _build_phase_status(messages, query_type=query_type, org_id=org_id)
                m_action = re.search(r'(PRÓXIMA FERRAMENTA:[^\n]+)', _status)
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
            return True, None, final_emitted, None

        # Extração de dados históricos para o suggest_next_actions
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

        # Interceptor: Investigação incompleta (enforça fases)
        if iteration < max_iters - 2:
            try:
                _msgs_with_current = _current_task_history
                _status = _build_phase_status(_msgs_with_current, query_type=query_type, org_id=org_id)
                context_mode_active = False
                for msg in messages:
                    if msg.get("role") == "user" and "[MODO CONTEXTO" in str(msg.get("content", "")):
                        context_mode_active = True
                        break

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

                if is_task_action:
                    _SEND_TOOLS = {"whatsapp_send_message", "email_send", "email_reply"}
                    _has_sent_global = False
                    _has_draft_global = False
                    
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
                    
                    if not _has_sent_global or not _has_draft_global:
                        for _b in content if isinstance(content, list) else []:
                            if isinstance(_b, dict) and _b.get("type") == "tool_use":
                                _tn_curr = _b.get("name")
                                if _tn_curr in _SEND_TOOLS: _has_sent_global = True
                                if _tn_curr == "generate_sales_message": _has_draft_global = True

                    _COMM_KEYWORDS = ["enviar", "email", "whatsapp", "mensagem", "mandar", "falar", "apresentação", "proposta", "follow"]
                    _is_comm_task = any(k in first_msg_content_clean.lower() for k in _COMM_KEYWORDS)

                    if _is_comm_task and (_has_sent_global or _has_draft_global):
                        _is_complete = True
                    elif _is_comm_task:
                        _is_complete = False
                    else:
                        _is_complete = True

                if not _is_complete and stop_reason in ("end_turn", "stop") and not tool_use_blocks:
                    m_action = re.search(r'(PRÓXIMA FERRAMENTA:[^\n]+)', _status)
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
                    return True, None, final_emitted, None

                # Interceptor: Ligação concluída mas ferramentas CRM não chamadas
                _ligacao_finalizada = any(
                    "ALERTA DE CONTEXTO: LIGAÇÃO FINALIZADA" in (
                        _m.get("content", "") if isinstance(_m.get("content"), str) 
                        else json.dumps(_m.get("content", ""))
                    )
                    for _m in messages
                )
                if _ligacao_finalizada and stop_reason in ("end_turn", "stop") and not tool_use_blocks:
                    _called_write_tools = False
                    _WRITE_TOOLS_CHECK = {"pipedrive_update_task", "pipedrive_create_note", "pipedrive_create_task"}
                    for _m in _current_task_history:
                        _mc = _m.get("content", "")
                        if isinstance(_mc, list):
                            for _b in _mc:
                                if isinstance(_b, dict) and (_b.get("name") in _WRITE_TOOLS_CHECK or _b.get("tool_name") in _WRITE_TOOLS_CHECK):
                                    _called_write_tools = True
                    
                    if not _called_write_tools:
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                "REGRA DE OURO: Você listou os próximos passos mas NÃO executou as ferramentas do CRM ou de envio de mensagem! "
                                "OBRIGATÓRIO: Chame as ferramentas `pipedrive_update_task`, `pipedrive_create_note`, `pipedrive_create_task`, "
                                "`whatsapp_send_message` ou `email_send` AGORA para executar essas ações no sistema. Se validou contatos/emails, "
                                "chame a ferramenta de envio novamente."
                            ),
                        })
                        return True, None, final_emitted, None

                # Injeção e disparo do suggest_next_actions
                if not _suggest_actions_done(_msgs_with_current) and stop_reason in ("end_turn", "stop") and not tool_use_blocks:
                    _final_response = response_text
                    if not _final_response.strip():
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
                            
                    if final_emitted and "concluída" in _final_response:
                        # Se já havíamos emitido o final e ele não chamou a tool, forçamos com erro
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": "ERRO: VOCÊ NÃO CHAMOU A FERRAMENTA `suggest_next_actions`. RETORNE IMEDIATAMENTE A CHAMADA DA FERRAMENTA `suggest_next_actions`. É ESTRITAMENTE PROIBIDO RESPONDER COM TEXTO."
                        })
                        return True, None, True, None
                    _task_action_hint = ""
                    if is_task_action:
                        _task_action_hint = (
                            f"\nTAREFA CRM CONCLUÍDA: A atividade #{first_msg_content[:20]}... foi processada.\n"
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

                    if org_id:
                        try:
                            from core.infra.database import async_session
                            from models.organization import Organization
                            from sqlalchemy import select
                            async with async_session() as session:
                                stmt = select(Organization.prospecting_context).where((Organization.id == org_id) | (Organization.pipedrive_id == org_id))
                                res = await session.execute(stmt)
                                pc = res.scalar_one_or_none()
                                if pc:
                                    real_data_summary.append(f"\n  [CONTEXTO ESTRATÉGICO / PLANO DE PROSPECÇÃO]:\n{pc}\n")
                        except: pass

                    real_data_str = "\n".join(real_data_summary) if real_data_summary else "  (Nenhum ID específico encontrado)"
                    messages.append({"role": "assistant", "content": content})
                    context_lines = [s for s in collected_tool_summaries[-10:] if s]
                    context_str = "\n".join(f"  • {s}" for s in context_lines) if context_lines else "  (sem dados específicos)"
                    
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Dossiê entregue. DADOS REAIS EXTRAÍDOS DO HISTÓRICO (USE APENAS ESTES IDS):\n{real_data_str}\n\n"
                            f"RESUMO DAS FONTES:\n{context_str}\n\n"
                            f"{_task_action_hint}\n"
                            "Você é um Consultor de Vendas B2B sênior e altamente estratégico.\n"
                            "AÇÃO OBRIGATÓRIA 1: Se a instrução do usuário exigia CONCLUIR/FECHAR uma tarefa específica, você DEVE chamar `pipedrive_update_task` com `done=true` agora. ATENÇÃO: Se o usuário pediu APENAS para atualizar a tarefa (ex: 'atribuir a Renata', 'mudar a data'), NÃO passe `done=true`! Atualize apenas os campos solicitados.\n"
                            "AÇÃO OBRIGATÓRIA 2: Chame OBRIGATORIAMENTE 'suggest_next_actions' com ações específicas, contextualizadas e comercialmente brilhantes.\n"
                            "IMPORTANTE: Você não precisa fazer as duas coisas no mesmo turno. Se precisar chamar `pipedrive_update_task`, faça-o agora e no turno seguinte você chamará `suggest_next_actions`.\n"
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
                            "ATENÇÃO CRÍTICA: NÃO ESCREVA NENHUM OUTRO TEXTO NO SEU RETORNO. APENAS CHAME A FERRAMENTA `suggest_next_actions` (TOOL CALL OBRIGATÓRIA)."
                        ),
                    })
                    return True, None, True, _final_response if not final_emitted else None
            except Exception as e:
                log.warning(f"Erro no post llm phase status validation: {e}")
                pass

    return False, None, final_emitted, None
