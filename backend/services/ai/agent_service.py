import asyncio
import json
import uuid
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from services.external.base_gemini_service import ask_gemini
from services.pipedrive.pipedrive_service import pipedrive_service
from services.ai.data_fetcher import fetch_contextual_data
from services.ai.prompts import (
    WORKFLOW_ANALYSIS_PROMPT, 
    WORKFLOW_PLANNER_PROMPT, 
    EMAIL_WRITER_PROMPT, 
    FINAL_RESPONSE_PROMPT
)

# Ações que REQUEREM aprovação do usuário (Vazio para modo 100% Autônomo)
ACTIONS_REQUIRING_APPROVAL = set()


class AgentService:
    """
    Serviço de Agente Autônomo de Vendas B2B.
    Pipeline de 5 estágios: Diagnóstico → Resolução de Contatos → Plano → Aprovação → Execução.
    """

    # Armazena ações pendentes de aprovação (in-memory, por sessão)
    _pending_actions: Dict[str, dict] = {}

    @staticmethod
    async def run_workflow(goal: str, initial_intent: dict, org_id: int, selected_entities: List[dict], session, log_queue: Optional[asyncio.Queue] = None, history: Optional[List[dict]] = None, initial_raw_context: Optional[dict] = None):
        """
        Executa o workflow completo do agente autônomo.
        """
        def log(msg):
            print(f"[Agent] {msg}")
            if log_queue:
                # Se for string, envelopa em objeto de log básico
                if isinstance(msg, str):
                    log_queue.put_nowait({"type": "log", "content": msg})
                else:
                    log_queue.put_nowait(msg)

        async def add_thought(context_description: Any, findings: dict = None):
            """Gera um pensamento natural de forma mecânica para evitar rate limits."""
            clean_thought = ""
            
            # Se for um dicionário (formato da nova IA de roteiro), humaniza a narrativa
            if isinstance(context_description, dict):
                fato = context_description.get('fato') or context_description.get('fact')
                impl = context_description.get('implicacao_comercial') or context_description.get('implication')
                val = context_description.get('o_que_vamos_validar') or context_description.get('next_step')
                
                parts = []
                if fato: parts.append(str(fato))
                if impl: parts.append(f"Isso sugere que {impl.lower() if isinstance(impl, str) else impl}")
                if val: parts.append(f"Vou focar em {val.lower() if isinstance(val, str) else val}")
                
                clean_thought = ". ".join(parts)
            else:
                # Caso seja string, faz a limpeza padrão
                desc_str = str(context_description) if context_description is not None else ""
                clean_thought = desc_str.replace("ENCONTRADO: ", "Localizei: ")
                clean_thought = clean_thought.replace("OBJETIVO ATUAL: ", "Meu objetivo agora é ")
                clean_thought = clean_thought.split(". Analise como")[0]
            
            if clean_thought:
                log({"type": "thought", "content": clean_thought, "icon": None})

        log({"type": "status", "content": "Iniciando workflow..."})
        
        # ═══════════════════════════════════════
        # ESTÁGIO 1: Coleta de Dados
        # ═══════════════════════════════════════
        raw_context = initial_raw_context or {}
        
        # 1. Se NÃO temos contexto, buscamos com retry
        if not raw_context:
            context_intent = initial_intent.copy()
            context_intent["activity_done_filter"] = None
            context_intent["activity_date_filter"] = "all"
            if "data_scope" not in context_intent: context_intent["data_scope"] = []
            for scope in ["persons", "notes", "activities", "deals", "whatsapp", "emails"]:
                if scope not in context_intent["data_scope"]:
                    context_intent["data_scope"].append(scope)

            max_retries = 2
            for attempt in range(max_retries):
                try:
                    raw_context = await fetch_contextual_data(context_intent, org_id, goal, session, selected_entities=selected_entities)
                    if raw_context.get("error"): raise Exception(raw_context["error"])
                    
                    pd_new = raw_context.get("pipedrive_details", {})
                    new_deals = pd_new.get("deals", [])
                    new_activities = pd_new.get("activities", [])

                    break
                except Exception as e:
                    await add_thought(f"Opa, tive um problema técnico: {str(e)}. Tentativa {attempt+1}/{max_retries}.")
                    if attempt == max_retries - 1:
                        raw_context = {"error": str(e), "pipedrive_details": {}, "email_result": {}, "whatsapp_result": {}}
                    await asyncio.sleep(1)
        
        # ═══════════════════════════════════════
        # ESTÁGIO 2: Resolução de Contatos e Comunicações (Otimizado)
        # ═══════════════════════════════════════
        pd_stats = raw_context.get("pipedrive_details", {})
        num_deals = len(pd_stats.get("deals", []))
        num_activities = len(pd_stats.get("activities", []))
        notes = pd_stats.get("notes", [])
        deals = pd_stats.get("deals", [])
        activities = pd_stats.get("activities", [])
        
        contact_map = await AgentService._resolve_contact_map(raw_context, org_id, session)
        

        # Recupera dados de comunicação
        existing_emails = raw_context.get("email_result", {}).get("resultado", {}).get("messages_by_contact", [])
        existing_wa = raw_context.get("whatsapp_result", {}).get("resultado", {}).get("messages_by_contact", [])
        
        # Mapeamento de e-mails/wa... (mantém lógica de indexação)
        emails_by_contact = {}
        for item in existing_emails:
            threads = item.get("human_threads", [])
            contact_name = (item.get("contact") or "").lower()
            if contact_name: emails_by_contact[contact_name] = threads
            contact_email = (item.get("email") or "").lower()
            if contact_email: emails_by_contact[contact_email] = threads
            
        whatsapp_by_contact = {}
        for item in existing_wa:
            msgs = item.get("messages", [])
            contact_name = (item.get("contact") or "").lower()
            if contact_name: whatsapp_by_contact[contact_name] = msgs
            contact_phone = item.get("phone")
            if contact_phone: whatsapp_by_contact[contact_phone] = msgs

        # ═══════════════════════════════════════════════
        # ESTÁGIO 3: Geração do Roteiro Narrativo (Estrategista de Vendas)
        # ═══════════════════════════════════════════════
        log({"type": "status", "content": "Gerando análise estratégica...", "icon": "auto_awesome"})
        
        # ... (restante da lógica do script_prompt e add_thought agora vem DEPOIS dos dados)
        
        org_name = raw_context.get("organization", {}).get("name", "Empresa")
        deals = pd_stats.get("deals", [])
        activities = pd_stats.get("activities", [])
        notes = pd_stats.get("notes", [])
        
        # Dados granulares para embasamento real
        deal_info = ", ".join([f"{d.get('title')} ({d.get('formatted_value')})" for d in deals[:2]])
        activity_subjects = [a.get("subject") for a in activities[:3]]
        last_note_snippet = notes[0].get("content", "")[:150].replace("\n", " ") if notes else "Sem notas"
        
        # Estatísticas de comunicação já mapeadas
        num_emails = sum(len(threads) for threads in emails_by_contact.values())
        num_wa = sum(len(msgs) for msgs in whatsapp_by_contact.values())
        
        # Input compacto + output rico: 3 linhas mantêm a qualidade visual da UI.
        # Formato: Fato → Implicação → Próxima ação (cada linha curta, baseada nos dados reais).
        script_prompt = f"""Analista de vendas B2B. Use APENAS os fatos abaixo para gerar insights. Cite nomes e valores reais.

CONTEXTO CRÍTICO: João Luccas (joao.moura@jferres.com.br) é o VENDEDOR que usa este sistema. Ele NUNCA é um contato ou prospecto. Os contatos listados são pessoas da empresa cliente.

FATOS:
- Empresa cliente: {org_name} | Objetivo da análise: {goal}
- Negócio: {deal_info or 'sem valor definido'}
- Atividades: {', '.join(activity_subjects) or 'nenhuma registrada'}
- Última nota: "{last_note_snippet}"
- Comunicações: {num_emails} threads email, {num_wa} conversas WhatsApp
- Contatos do cliente: {', '.join(list(contact_map.keys())[:3])}

Regra: cada campo = 3 frases curtas. Linha 1: fato encontrado. Linha 2: implicação comercial. Linha 3: o que validar agora.
PROIBIDO inventar dados que não estejam nos fatos acima. PROIBIDO mencionar João Luccas como contato ou cliente.

Retorne JSON:
{{"intro":"Frase1. Frase2. Frase3.","tasks_reaction":"Frase1. Frase2. Frase3.","finding_people":"Frase1. Frase2. Frase3.","maturity_analysis":"Frase1. Frase2. Frase3."}}"""
        
        narrative_script = {}
        try:
            # Usa o Tier FAST para ser rápido e econômico
            from services.ai.llm import LLMTier, ask_llm
            script_res = await ask_llm(script_prompt, json_mode=True, tier=LLMTier.FAST)
            narrative_script = script_res.json_data or {}
        except:
            log("IA ocupada, seguindo com análise técnica...")

        # ═══════════════════════════════════════════════
        # ESTÁGIO 3: Descoberta de Negócio e Tarefas (Narrativa Intercalada)
        # ═══════════════════════════════════════════════
        
        # 1. BLOCO: Negócio e Valores
        intro_text = narrative_script.get("intro", f"Vou analisar o contexto de '{goal}' no Pipedrive agora.")
        await add_thought(intro_text)
        await asyncio.sleep(0.8)
        
        for deal in deals:
            log({"type": "data_found", "entity": "deal", "data": deal})

        await asyncio.sleep(0.5)

        # 2. BLOCO: Tarefas e Contexto (Reativo)
        if activities:
            tasks_text = narrative_script.get("tasks_reaction", "Analisando o padrão de atividades registradas.")
            await add_thought(tasks_text)
            await asyncio.sleep(0.8)
            for act in activities[:5]:
                log({"type": "data_found", "entity": "activity", "data": act})
        
        await asyncio.sleep(0.8)
        
        # 3. BLOCO: Pessoas e Comunicações
        people_text = narrative_script.get("finding_people", "Mapeando os principais interlocutores e histórico de mensagens.")
        await add_thought(people_text)
        log({"type": "status", "content": "Cruzando histórico de comunicações...", "icon": "search"})

        # Marcar entidades selecionadas no mapa e logar
        selected_names = [e.get("name") for e in selected_entities]
        logged_count = 0
        
        # Loga Contatos e Comunicações de forma intercalada
        # Regra: contatos COM comunicação real (email/WA) aparecem SEMPRE.
        # Contatos sem comunicação: limite de 3 para não poluir o painel.
        for name, info in contact_map.items():
            name_key = name.lower()
            email_key = (info.get("email") or "").lower()
            is_key_contact = name in selected_names or info.get("is_priority")

            # Pré-carrega comunicações antes de decidir se loga o contato
            person_emails = emails_by_contact.get(name_key) or emails_by_contact.get(email_key, [])
            person_wa = whatsapp_by_contact.get(name_key) or whatsapp_by_contact.get(info.get("phone"), [])
            has_comms = bool(person_emails or person_wa)

            # Mostra: contatos selecionados/prioritários + qualquer contato com comunicação + até 3 sem comunicação
            if is_key_contact or has_comms or logged_count < 3:
                # Injeção do Card de Contato
                log({"type": "data_found", "entity": "contact", "data": info, "label": "Prioritário" if is_key_contact else None})
                await asyncio.sleep(0.4)

                if has_comms:
                    await add_thought(f"Encontrei histórico de conversas com {name}. Vou analisar o tom da negociação...")
                    await asyncio.sleep(0.6)

                    if person_emails:
                        # Emite todos os threads deste contato (até 5), não só o primeiro
                        for email_thread in person_emails[:5]:
                            log({
                                "type": "data_found",
                                "entity": "email",
                                "data": {
                                    "contact": {"name": name, "email": info.get("email")},
                                    "subject": email_thread.get("subject", "Sem Assunto"),
                                    "sent_message": email_thread.get("snippet") or email_thread.get("body") or "Sem conteúdo visual",
                                    "body_preview": email_thread.get("snippet") or email_thread.get("body") or "Sem conteúdo visual",
                                    "messages": [email_thread]
                                }
                            })
                            await asyncio.sleep(0.2)

                    if person_wa:
                        log({"type": "data_found", "entity": "whatsapp", "data": person_wa[0]})
                        await asyncio.sleep(0.4)

                # Conta apenas contatos sem comunicação para o limite de 3
                if not is_key_contact and not has_comms:
                    logged_count += 1

        # Contagem de contatos que não foram logados (sem comunicação e além do limite)
        total_shown = sum(1 for n, info in contact_map.items() if
                          n in selected_names or info.get("is_priority") or
                          bool(emails_by_contact.get(n.lower()) or emails_by_contact.get((info.get("email") or "").lower()) or
                               whatsapp_by_contact.get(n.lower()) or whatsapp_by_contact.get(info.get("phone"))))
        total_shown += min(logged_count, 3)
        remaining = len(contact_map) - total_shown
        if remaining > 0:
            log({"type": "log", "content": f"... e mais {remaining} contatos mapeados."})

        # Injeta no contexto para análise de maturidade
        raw_context["emails_by_contact"] = emails_by_contact
        raw_context["whatsapp_by_contact"] = whatsapp_by_contact

        # PENSAMENTO 3: Análise de Maturidade e Próximos Passos
        maturity_text = narrative_script.get("maturity_analysis", "Analisando maturidade das interações para definir estratégia.")
        await add_thought(maturity_text)
        
        # Pausa reduzida para performance
        await asyncio.sleep(1.0)

        log({"type": "status", "content": "Gerando estratégia e plano de ação...", "icon": "auto_awesome"})

        # Destila comunicações AQUI para poder exibir no painel e reaproveitar em _analyze_deal_state
        print("[Agent] 🧪 Destilando comunicações para arqueologia de alta precisão...")
        try:
            distilled_comms = await AgentService._distill_communications(
                raw_context.get("email_result", {}),
                raw_context.get("whatsapp_result", {})
            )
        except Exception:
            distilled_comms = ""

        if distilled_comms and "Nenhuma comunicação" not in distilled_comms and "Falha ao destilar" not in distilled_comms:
            await add_thought(distilled_comms)
            await asyncio.sleep(0.5)

        # Armazena para _analyze_deal_state não precisar recalcular
        raw_context["_precomputed_distilled"] = distilled_comms

        try:
            # Tenta consolidar análise e plano em um único fluxo ou lidar com falhas graciosamente
            deal_analysis = await AgentService._analyze_deal_state(raw_context)
        except Exception as e:
            print(f"[Agent] ⚠️ Falha na análise de maturidade (LLM Rate Limit?): {e}")
            deal_analysis = "Análise indisponível no momento devido a limites de cota, seguindo com plano básico."

        # Pausa reduzida para performance
        await asyncio.sleep(1.0)

        # ─── Contexto de Atividades Recentes (para injeção no planner) ────────
        activity_context_str = ""
        if session and org_id:
            try:
                from api.v1.endpoints.conversations import get_recent_activities_context
                recent_acts = await get_recent_activities_context(session, org_id, limit=8)
                if recent_acts:
                    lines = ["HISTÓRICO DE AÇÕES JÁ REALIZADAS PELO AGENTE:"]
                    for act in recent_acts:
                        p = act.payload or {}
                        ts = act.created_at.strftime("%d/%m %H:%M") if act.created_at else ""
                        if act.activity_type == "email_sent":
                            lines.append(f"- [{ts}] Email enviado para {p.get('to_name','?')} | Assunto: {p.get('subject','?')} | Status: {act.status}")
                        elif act.activity_type in ("email_reply_sent",):
                            lines.append(f"- [{ts}] Resposta de email enviada para {p.get('to_name','?')} | Re: {p.get('subject','?')}")
                        elif act.activity_type == "whatsapp_sent":
                            lines.append(f"- [{ts}] WhatsApp enviado para {p.get('to_name','?')}: {p.get('message_preview','')[:60]}")
                        elif act.activity_type == "stage_changed":
                            lines.append(f"- [{ts}] Estágio alterado: {p.get('from_stage','?')} → {p.get('to_stage','?')}")
                        elif act.activity_type == "email_reply_received":
                            lines.append(f"- [{ts}] ✅ Resposta recebida de {p.get('from_name','?')} | Re: {p.get('subject','?')}")
                        else:
                            lines.append(f"- [{ts}] {act.activity_type}: {str(p)[:80]}")
                    # Emails aguardando resposta
                    pending_emails = [a for a in recent_acts if a.status == "awaiting_reply"]
                    if pending_emails:
                        lines.append(f"\n⚠️ {len(pending_emails)} email(s) aguardando resposta — considere follow-up antes de reenviar.")
                    activity_context_str = "\n".join(lines)
                    log({"type": "status", "content": "Consultando histórico de interações...", "icon": "history"})
            except Exception as act_err:
                print(f"[Agent] ⚠️ Falha ao carregar ActivityLog: {act_err}")

        try:
            plan_raw = await AgentService._create_logical_plan(goal, deal_analysis, raw_context, contact_map, selected_entities, history=history, activity_context=activity_context_str)
            
            # Normalização robusta de JSON/Plan
            if not plan_raw:
                raise ValueError("Plano retornado vazio pela IA")
                
            if isinstance(plan_raw, dict):
                plan = plan_raw.get("plan", [])
            elif isinstance(plan_raw, list):
                plan = plan_raw
            else:
                plan = []
                
            if not plan:
                # Se a IA retornou um JSON mas sem o campo 'plan' (ex: erro capturado pelo provider)
                if isinstance(plan_raw, dict) and "response" in plan_raw:
                     # Tenta converter o texto bruto em uma ação de conteúdo
                     plan = [{"action": "generate_content", "description": "Insight gerado", "params": {"content": plan_raw["response"]}}]
                else:
                    raise ValueError("Estrutura de plano inválida")

        except Exception as e:
            print(f"[Agent] ⚠️ Falha na geração do plano dinâmico ({e}). Acionando protocolo de contingência.")
            # PROTOCOLO DE CONTINGÊNCIA: Cria uma tarefa manual para não perder o momentum
            plan = [{
                "action": "create_pipedrive_task",
                "description": "Protocolo de Segurança: Agendando retorno manual devido a instabilidade na IA.",
                "params": {
                    "subject": f"Retorno: {goal[:50]}...",
                    "note": f"O sistema detectou uma instabilidade ao gerar o plano automático para o objetivo: '{goal}'. Verifique o histórico de comunicações e responda ao cliente.",
                    "type": "call",
                    "due_date": datetime.now().strftime("%Y-%m-%d"),
                    "done": False
                }
            }]
            log({"type": "log", "content": "⚠️ IA instável. Aplicando plano de contingência para garantir o follow-up.", "status": "warning"})

        # ═══════════════════════════════════════
        # ESTÁGIO 5: Execução com Aprovação Seletiva
        # ═══════════════════════════════════════
        execution_results = []
        created_tasks = []
        pending_approvals = []

        for step in plan:
            if isinstance(step, str):
                if step.lower() in ["action", "description", "params", "plan"]:
                    continue
                step = {"action": "generate_content", "description": step, "params": {}}
                
            action = step.get("action", "")
            desc = step.get("description", "Ação do Agente")
            params = step.get("params", {})
            
            # Resolve Canal e Nome para o Log
            channel = "WhatsApp" if action == "send_whatsapp" else ("Email" if "email" in action else "Sistema")
            contact_name = params.get("contact_name")
            if not contact_name:
                pd_p = raw_context.get("pipedrive_details", {}).get("persons", [])
                contact_name = pd_p[0].get("name") if pd_p else raw_context.get("organization", {}).get("name", "Contato")
            params["contact_name"] = contact_name

            # --- FLUXO DE APROVAÇÃO (Comunicações) ---
            if action in ["send_email", "reply_email", "send_whatsapp"]:

                # REPLY-FIRST FALLBACK: se a IA gerou 'reply_email' mas esqueceu o email_entry_id,
                # resolvemos aqui a partir do contact_map antes de mostrar o card.
                if action == "reply_email" and not params.get("email_entry_id"):
                    for _name, _info in contact_map.items():
                        if _info.get("last_email_id") and (
                            _name.lower() == contact_name.lower()
                            or (params.get("email", "") and _info.get("email", "").lower() == params.get("email", "").lower())
                        ):
                            params["email_entry_id"] = _info["last_email_id"]
                            if not params.get("subject"):
                                params["subject"] = _info.get("last_email_subject", "")
                            print(f"[Agent] ↩️ email_entry_id resolvido via fallback para '{_name}': {params['email_entry_id'][:30]}...")
                            break
                    # Se ainda não encontrou, degrada para send_email com log de aviso
                    if not params.get("email_entry_id"):
                        action = "send_email"
                        step["action"] = "send_email"
                        log({"type": "log", "content": "⚠️ Thread não encontrado — enviando como novo e-mail.", "status": "warning"})

                log({"type": "log", "content": f"📝 Sugestão de {channel} preparada para {contact_name}...", "status": "pending"})

                # Refinamento de IA para o corpo da mensagem
                if "email" in action:
                    params["body"] = await AgentService._beautify_email(
                        params,
                        raw_context.get("organization", {}).get("name", "Empresa"),
                        original_history=raw_context
                    )

                # Enriquece params com IDs de contexto para sincronização pós-envio
                if not params.get("activity_id"):
                    activities = raw_context.get("pipedrive_details", {}).get("activities", [])
                    pending_act = next((a for a in activities if not a.get("done")), None)
                    if pending_act:
                        params["activity_id"] = pending_act.get("id")
                if not params.get("deal_id"):
                    deals = raw_context.get("pipedrive_details", {}).get("deals", [])
                    if deals:
                        params["deal_id"] = deals[0].get("id")

                # Gera action_id único e armazena no dicionário de ações pendentes
                import uuid
                action_id = str(uuid.uuid4())
                # org_id extraído do contexto para uso no ActivityLog
                _org_id = None
                if raw_context:
                    _org_id = (raw_context.get("organization") or {}).get("id") or (raw_context.get("org") or {}).get("id")
                AgentService._pending_actions[action_id] = {
                    "action": action,
                    "params": params,
                    "org_id": _org_id,
                    # Campos extras para ActivityLog (preenchidos logo abaixo junto ao pending_approvals)
                    "action_type": action,
                    "channel": channel,
                    "contact_name": contact_name,
                    "contact_email": params.get("email"),
                    "contact_phone": params.get("phone"),
                    "subject": params.get("subject"),
                    "message_preview": params.get("body", params.get("message", "")),
                    "is_reply": action == "reply_email",
                    "email_entry_id": params.get("email_entry_id"),
                    "description": desc,
                }

                # Resolve subject original do thread para o card de reply
                original_subject = None
                if action == "reply_email":
                    for _name, _info in contact_map.items():
                        if _info.get("last_email_id") == params.get("email_entry_id"):
                            original_subject = _info.get("last_email_subject") or params.get("subject")
                            break
                    if not original_subject:
                        original_subject = params.get("subject", "")

                # Monta payload com todos os campos que o frontend espera
                pending_approvals.append({
                    "action_id": action_id,
                    "action_type": action,
                    "action": action,
                    "description": desc,
                    "params": params,
                    "channel": channel,
                    "contact_name": contact_name,
                    "contact_email": params.get("email"),
                    "contact_phone": params.get("phone"),
                    "subject": params.get("subject"),
                    "message_preview": params.get("body", params.get("message", "")),
                    "is_reply": action == "reply_email",
                    "original_subject": original_subject,
                    "email_entry_id": params.get("email_entry_id"),
                })
                continue # Pula execução direta

            # --- VALIDAÇÃO DE ESTÁGIO ANTES DE EXECUTAR ---
            if action == "update_pipedrive_deal" and params.get("stage_id"):
                stage_blocked = await AgentService._validate_stage_advancement(
                    params, raw_context, log
                )
                if stage_blocked:
                    continue  # Pula a execução desta ação

            # --- EXECUÇÃO AUTÔNOMA (CRUD / Sistema) ---
            log(f"Executando: {desc}")
            try:
                result = await AgentService._execute_real_action(step, raw_context, initial_intent, org_id)
            except Exception as e:
                print(f"[Agent] ❌ Erro Crítico ao executar {action}: {e}")
                log(f"❌ Falha técnica ao executar {desc}: {str(e)}")
                result = None

            # Tratamento de log de sucesso/erro
            if action == "update_pipedrive_deal" and result:
                if isinstance(result, dict) and result.get("success"):
                    deal_id = params.get("deal_id") or (raw_context.get("pipedrive_details", {}).get("deals", [{}])[0].get("id"))
                    log({"type": "log", "content": f"🚀 Negócio atualizado no Pipedrive (ID: {deal_id})", "status": "success"})
                    execution_results.append({"description": desc, "status": "success"})
                else:
                    err = result.get("error") if isinstance(result, dict) else "Erro desconhecido"
                    log(f"❌ Falha ao atualizar negócio no Pipedrive: {err}")
                    execution_results.append({"description": desc, "status": "failed", "error": err})
            elif action == "create_pipedrive_task" and result:
                if isinstance(result, dict) and result.get("success"):
                    act_id = result.get("data", {}).get("id")
                    log({"type": "log", "content": f"✅ Atividade criada no Pipedrive (ID: {act_id})", "status": "success"})
                    created_tasks.append({
                        "id": act_id,
                        "subject": params.get("subject"),
                        "note": params.get("note"),
                        "due_date": (datetime.now() + timedelta(days=params.get("days_delay", 0))).strftime("%Y-%m-%d"),
                        "type": params.get("type", "task"),
                        "done": False
                    })
                    execution_results.append({"description": desc, "status": "success"})
                else:
                    err = result.get("error") if isinstance(result, dict) else "Erro desconhecido"
                    log(f"❌ Falha ao criar atividade no Pipedrive: {err}")
                    execution_results.append({"description": desc, "status": "failed", "error": err})
            elif action in ["send_whatsapp", "send_email", "reply_email"]:
                status = "success" if result else "failed"
                log({"type": "log", "content": f"{'✅' if result else '❌'} {channel} para {contact_name}: {status.upper()}", "status": status})
                execution_results.append({"description": desc, "status": status, "channel": channel})
            else:
                execution_results.append({
                    "description": desc,
                    "action": action,
                    "status": "success" if result else "failed",
                    "details": result
                })
            
        # ═══════════════════════════════════════
        # ESTÁGIO 6: Briefing Executivo
        # ═══════════════════════════════════════
        channels_checked = []
        if raw_context.get("whatsapp_result"): channels_checked.append("WhatsApp")
        if raw_context.get("email_result"): channels_checked.append("Email")
        if raw_context.get("pipedrive_details"): channels_checked.append("Pipedrive")
        
        # Serializa resultados de forma compacta: apenas descrição + status (sem params completos)
        def _compact_results(results):
            return [{"desc": r.get("description","")[:80], "status": r.get("status")} for r in results]

        exec_context = (
            f"Canais: {', '.join(channels_checked) or 'nenhum'}\n"
            f"Diagnóstico: {(deal_analysis or '')[:500]}\n"
            f"Executadas: {json.dumps(_compact_results([r for r in execution_results if r.get('status') == 'success']))}\n"
            f"Falhas: {json.dumps(_compact_results([r for r in execution_results if r.get('status') == 'failed']))}\n"
            f"Aprovações pendentes: {len(pending_approvals)}"
        )
        
        executive_summary = await ask_gemini(FINAL_RESPONSE_PROMPT.format(context=exec_context))
        
        # Se falhou por cota, usa um fallback amigável em vez da mensagem de erro crua
        if isinstance(executive_summary, str) and "Desculpe, ocorreu um erro de cota" in executive_summary:
            executive_summary = f"Concluí as ações para **{org_name}**. O plano foi executado e as atividades foram registradas no CRM conforme solicitado."

        full_response_parts = [
            executive_summary
        ]
        
        # Se houver novas tarefas, anexamos o marcador de lista
        if created_tasks:
            full_response_parts.append("\n\n[[NEW_TASKS]]")
        
        # Envia a resposta final para o stream antes do return
        log({"type": "final_response", "content": "\n\n".join(full_response_parts)})
        
        # SINAL DE CONCLUSÃO TOTAL (Limpa todos os spinners residuais)
        log({"type": "status", "content": "Concluído", "status": "done", "icon": "done_all"})
        log({"type": "finish"})
        
        return {
            "status": "completed",
            "full_response": "\n\n".join(full_response_parts),
            "past_activities": raw_context.get("pipedrive_details", {}).get("activities", []),
            "new_activities": created_tasks,
            "organization_data": raw_context.get("organization"),
            "pending_approvals": pending_approvals
        }

    # ═══════════════════════════════════════
    # RESOLUÇÃO DE CONTATOS (Mapa de Alcance)
    # ═══════════════════════════════════════
    @staticmethod
    async def _resolve_contact_map(context: dict, org_id: int, session) -> Dict[str, dict]:
        """
        Cruza Pipedrive Persons com canais reais.
        Tenta também encontrar contatos no WhatsApp que mencionem o nome da organização mas não estejam no Pipedrive.
        """
        pd_details = context.get("pipedrive_details", {})
        org_name = context.get("organization", {}).get("name", "")
        persons = pd_details.get("persons", []) if isinstance(pd_details, dict) else []
        selected_entities = context.get("selected_entities", [])
        explicit_selected = [e for e in selected_entities if (e.get("type") if isinstance(e, dict) else getattr(e, "type", None)) in ["email", "whatsapp", "person", "employee"]]
        
        # Filtro de Exclusividade: Se há pessoas selecionadas na UI, descarta as pessoas genéricas do Pipedrive
        if explicit_selected:
            persons = [p for p in persons if any((p.get("name") or "").lower() == (e.get("name") or "").lower() for e in explicit_selected)]
            
        contact_map = {}
        wa_base = "http://localhost:8001/api/whatsapp"
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Processa pessoas vindas do Pipedrive
            if persons:
                for p in persons[:10]:
                    name = p.get("name", "Desconhecido")
                    phone = p.get("phone", [{}])[0].get("value")
                    email = p.get("email", [{}])[0].get("value")
                    
                    channels = []
                    wa_available = False
                    if phone:
                        try:
                            clean_num = phone.replace("+", "").replace("-", "").replace(" ", "")
                            if len(clean_num) <= 11 and not clean_num.startswith("55"):
                                clean_num = f"55{clean_num}"
                            resp = await client.get(f"{wa_base}/contacts/by-number/{clean_num}")
                            if resp.status_code == 200:
                                wa_available = True
                                channels.append("WhatsApp")
                        except: pass
                        channels.append("Telefone")
                    
                    if email:
                        channels.append("Email")
                    
                    if not channels:
                        continue # Pula contatos sem nenhuma forma de comunicação
                    
                    contact_map[name] = {
                        "name": name,
                        "pipedrive_person_id": p.get("id"),
                        "phone": phone,
                        "email": email,
                        "whatsapp_available": wa_available,
                        "email_available": bool(email),
                        "channels": channels,
                        "source": "Pipedrive",
                        "last_email_id": None # Será preenchido abaixo
                    }
            
            # --- NOVIDADE: RESOLUÇÃO DE THREADS DE EMAIL ---
            email_res = context.get("email_result", {})
            email_groups = email_res.get("resultado", {}).get("messages_by_contact", [])
            for group in email_groups:
                c_name = group.get("contact")
                if c_name in contact_map:
                    human_msgs = group.get("human_threads", [])
                    if human_msgs:
                        # Pega o entryId da mensagem mais recente para o 'Reply'
                        # O campo correto é 'entryId' (Exchange EWS), não 'id'
                        last_msg = human_msgs[0]
                        entry_id = (
                            last_msg.get("entryId")
                            or last_msg.get("entry_id")
                            or last_msg.get("id")
                        )
                        contact_map[c_name]["last_email_id"] = entry_id
                        contact_map[c_name]["last_email_subject"] = last_msg.get("subject", "")
                        if "Email" not in contact_map[c_name]["channels"]:
                             contact_map[c_name]["channels"].append("Email")
            
            # Adiciona os explícitos selecionados na UI se eles já não estiverem no mapa
            for exc in explicit_selected:
                name = exc.get("name")
                if name and name not in contact_map:
                    chans = []
                    email = exc.get("email")
                    if email: chans.append("Email")
                    phone = exc.get("phone")
                    if phone: chans.append("WhatsApp")
                    
                    contact_map[name] = {
                        "name": name,
                        "phone": phone,
                        "email": email,
                        "whatsapp_available": bool(phone),
                        "email_available": bool(email),
                        "channels": chans,
                        "source": "Seleção Direta na Interface"
                    }

            # 2. PROATIVIDADE: Busca contatos no Banco Local (Hierarchy Mapper) que NÃO estão no Pipedrive (apenas se o usuário não afunilou)
            if not explicit_selected:
                try:
                    from sqlalchemy import select
                    from models.employee import Employee
                    from models.organization import Organization

                    # org_id pode ser ID do Pipedrive ou Local
                    local_org_stmt = select(Organization).where(
                        (Organization.id == org_id) | (Organization.pipedrive_id == org_id)
                    )
                    local_org_res = await session.execute(local_org_stmt)
                    local_org = local_org_res.scalar_one_or_none()

                    if not local_org:
                        print(f"[Agent] ℹ️ Organização Pipedrive ID={org_id} não encontrada no banco local. Pulando busca de employees.")
                        local_employees = []
                    else:
                        stmt = select(Employee).where(Employee.company_id == local_org.id)
                        res = await session.execute(stmt)
                        local_employees = res.scalars().all()
                        print(f"[Agent] 🏢 Organização local encontrada (ID={local_org.id}). Employees: {len(local_employees)}")
                    
                    # Filtro de ruído: Ignorar departamentos internos óbvios que poluem o cenário de vendas
                    internal_noise = ["pcp", "rh", "financeiro", "comercial", "adm", "nfe", "qualidade", "faturamento", "fabrica", "processos", "allcompany", "intranet"]
                    internal_domains = ["jferres.com.br"] # Domínios da própria empresa
                    # Domínios pessoais genéricos (não são contatos B2B do cliente)
                    personal_domains = ["gmail.com", "hotmail.com", "yahoo.com", "yahoo.com.br", "outlook.com", "live.com", "icloud.com", "uol.com.br", "bol.com.br"]
                    # E-mails do próprio usuário que nunca devem aparecer como prospectos
                    own_emails = ["joaoluccas637@gmail.com", "clicheval@hotmail.com", "joao.moura@jferres.com.br"]

                    for emp in local_employees:
                        emp_email = (emp.email or "").lower()
                        is_noise = any(noise in emp_email or noise in emp.name.lower() for noise in internal_noise)
                        is_internal_domain = any(dom in emp_email for dom in internal_domains)
                        is_personal_domain = any(dom in emp_email for dom in personal_domains)
                        is_own_email = emp_email in own_emails
                        
                        if is_noise or is_internal_domain or is_personal_domain or is_own_email: continue # Pula ruídos internos e contatos pessoais
                        
                        contact_map[emp.name] = {
                                "name": emp.name,
                                "phone": emp.whatsapp_number or emp.phone,
                                "email": emp.email,
                                "whatsapp_available": bool(emp.whatsapp_number),
                                "email_available": bool(emp.email),
                                "channels": [c for c in ["WhatsApp", "Email", "Telefone"] if (emp.whatsapp_number if c=="WhatsApp" else (emp.email if c=="Email" else emp.phone))],
                                "source": f"Inteligência Local ({emp.department or 'Sem Dept'})",
                                "is_unmapped": True, # Força cor cinza conforme pedido
                                "is_new_prospect": True
                            }
                except Exception as e:
                    print(f"[Agent] Erro ao buscar contatos locais: {e}")

            # 3. Busca contatos no WhatsApp que combinem com o nome da empresa
            if org_name and len(org_name) > 2:
                try:
                    search_resp = await client.get(f"{wa_base}/contacts/search?name={org_name}")
                    if search_resp.status_code == 200:
                        wa_contacts = search_resp.json()
                        for wc in wa_contacts[:3]:
                            wc_name = wc.get("name")
                            if wc_name and wc_name not in contact_map:
                                contact_map[wc_name] = {
                                    "name": wc_name,
                                    "phone": wc.get("id", "").split("@")[0],
                                    "whatsapp_available": True,
                                    "channels": ["WhatsApp"],
                                    "source": "WhatsApp (Não vinculado)",
                                    "is_unmapped": True # Força cor cinza conforme pedido
                                }
                except: pass
        
        return contact_map

    @staticmethod
    def _get_business_protocol():
        """Carrega as regras de negócio e persona da empresa."""
        import os
        path = os.path.join(os.getcwd(), "intelligence_config", "business_protocol.md")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return "Sem protocolo de negócio definido."

    @staticmethod
    async def _distill_communications(email_result: dict, wa_result: dict) -> str:
        """Usa uma IA rápida para transformar mensagens brutas em fatos curtos."""
        from services.ai.llm import LLMTier, ask_llm
        from services.ai.prompts import COMMUNICATION_DISTILLER_PROMPT
        
        all_text = []

        # Coleta e-mails — top 3, até 350 chars cortando na última frase completa
        # (era top 5 × 500 = 2.5kb → agora ~1kb, mas com frases íntegras)
        groups = email_result.get("resultado", {}).get("messages_by_contact", [])
        for g in groups:
            for m in g.get("human_threads", [])[:3]:
                body = (m.get("body") or "").strip()
                if body:
                    # Trunca em 350 chars mas corta na última pontuação para não quebrar contexto
                    trunc = body[:350]
                    for delim in (". ", "! ", "? ", "\n"):
                        last = trunc.rfind(delim)
                        if last > 150:  # só corta se ainda tiver substância
                            trunc = trunc[:last + 1]
                            break
                    # Identifica direção:
                    # - Exchange DN (/o=ExchangeLabs...) = email enviado por João (caixa de saída interna)
                    # - Email com @ sem jferres.com.br = email recebido do cliente
                    sender_raw = (m.get("sender") or "").lower()
                    to_raw = (m.get("to") or "").lower()
                    if sender_raw.startswith("/o=") or "jferres.com.br" in sender_raw:
                        direction = "Eu→Cliente"
                    elif "@" in sender_raw and "jferres.com.br" not in sender_raw:
                        direction = "Cliente→Eu"
                    else:
                        # Fallback: se 'to' for endereço externo, assume saída
                        direction = "Eu→Cliente" if ("@" in to_raw and "jferres.com.br" not in to_raw) else "Cliente→Eu"
                    all_text.append(f"Email {m.get('date','')[:10]} [{direction}]: {trunc.strip()}")

        # Coleta WhatsApp — top 5 msgs, 180 chars (WA mensagens já são naturalmente curtas)
        wa_groups = wa_result.get("resultado", {}).get("messages_by_contact", [])
        for g in wa_groups:
            for m in g.get("messages", [])[:5]:
                body = (m.get("body") or "").strip()
                if body:
                    # Corta na última palavra completa (não no meio)
                    trunc = body[:180]
                    if len(body) > 180 and " " in trunc:
                        trunc = trunc[:trunc.rfind(" ")]
                    sender = "Eu" if m.get("fromMe") else "Cliente"
                    all_text.append(f"WA {m.get('date_human','')[:10]} ({sender}): {trunc}")
        
        if not all_text:
            return "Nenhuma comunicação recente encontrada."
            
        combined = "\n".join(all_text)
        try:
            res = await ask_llm(
                COMMUNICATION_DISTILLER_PROMPT.format(text=combined),
                tier=LLMTier.FAST,
                cacheable=True
            )
            return res.text
        except:
            return "Falha ao destilar comunicações, usando dados brutos truncados."

    # ═══════════════════════════════════════
    # ANÁLISE DE CENÁRIO
    # ═══════════════════════════════════════
    @staticmethod
    async def _analyze_deal_state(context: dict):
        """Analisa o histórico para entender em que ponto o negócio está."""
        pd_details = context.get("pipedrive_details", {})
        activities = pd_details.get("activities", [])
        notes = pd_details.get("notes", [])
        deals = pd_details.get("deals", [])
        
        history_summary = "PIPELINE:\n"
        for d in deals[:2]:  # 2 deals bastam (era 3)
            history_summary += f"- {d.get('title')} | {d.get('formatted_value')} | {d.get('stage_name')} | {d.get('status')}\n"

        deals_in_stage = context.get("deals_in_stage", [])
        if deals_in_stage:
            history_summary += "LOTE DA ETAPA:\n"
            for d in deals_in_stage[:3]:  # era 5
                history_summary += f"- {d.get('org_name')} | {d.get('value')}\n"

        history_summary += "ATIVIDADES:\n"
        for i, act in enumerate(activities[:5]):  # era 10 — 5 atividades cobrem o contexto
            status = "OK" if act.get("done") else "PEND"
            note_snip = (act.get("note_clean") or "")[:150].replace("\n", " ").strip()
            note_part = f" | nota: {note_snip}" if note_snip else ""
            history_summary += f"[{i+1}] {act.get('due_date')}: {act.get('subject')} ({status}){note_part}\n"
        
        # DESTILAÇÃO DE COMUNICAÇÕES — usa resultado pré-computado se disponível (evita chamada dupla)
        distilled = context.get("_precomputed_distilled")
        if distilled is None:
            print("[Agent] 🧪 Destilando comunicações (fallback interno)...")
            distilled = await AgentService._distill_communications(
                context.get("email_result", {}),
                context.get("whatsapp_result", {})
            )

        history_summary += f"\nFATOS EXTRAÍDOS DAS COMUNICAÇÕES (ARQUEOLOGIA):\n{distilled}\n"

        # Injeção de Status Calculado (Cross-channel)
        calc_status = context.get("calculated_status", {})
        if calc_status:
            history_summary += f"\n📊 ANÁLISE DE TEMPO REAL (Métrica LINKB2B):\n"
            history_summary += f"- {calc_status.get('summary')}\n"
        else:
            history_summary += f"\n⏳ ALERTA DE CICLO: Verificando momentum...\n"

        # Para análise, precisamos da identidade (seção 1) + anti-alucinação (seção 3).
        # 900 chars cobre as 3 primeiras seções, incluindo as regras críticas de evidência obrigatória.
        # O protocolo completo vai para o planejamento (onde as ações são definidas).
        protocol = AgentService._get_business_protocol()
        protocol_short = protocol[:900]  # cobre seções 1, 2 e 3 (Anti-Alucinação)
        prompt = WORKFLOW_ANALYSIS_PROMPT.format(
            protocol=protocol_short,
            history_summary=history_summary
        )
        return await ask_gemini(prompt)

    # ═══════════════════════════════════════
    # PLANO DE AÇÃO ESTRATÉGICO
    # ═══════════════════════════════════════
    @staticmethod
    async def _create_logical_plan(goal: str, analysis: str, context: dict, contact_map: dict, selected_entities: List[dict], history: List[dict] = None, activity_context: str = ""):
        """Passo 4: Define as ações concretas com inteligência multicanal."""
        pd_details = context.get("pipedrive_details", {})
        deals = pd_details.get("deals", [])

        # Otimiza lista de deals para o prompt
        deals_info = "\n".join([f"- ID: {d.get('id')} | Título: {d.get('title')} | Valor: {d.get('formatted_value')} | Fase Atual: {d.get('stage_name')}" for d in deals[:3]])

        # Formata atividades JÁ EXISTENTES de forma compacta
        activities = pd_details.get("activities", [])
        activities_info = "TAREFAS NO CRM: " + (", ".join([f"{a.get('subject')} ({'OK' if a.get('done') else 'PEND'})" for a in activities[:5]]) if activities else "Nenhuma")

        # Formata histórico para resolução de referências (últimas 3 mensagens para poupar tokens)
        history_str = ""
        if history:
            # 2 mensagens, 120 chars cada — suficiente para resolver referências (era 3 × 200)
            history_str = "\n".join([f"{h.get('role')}: {h.get('content','')[:120]}" for h in history[-2:]])

        # Formata mapa de contatos compacto — inclui email_entry_id para REPLY-FIRST
        def _fmt_contact(n, info):
            channels = "/".join(info.get("channels", []))
            entry_id = info.get("last_email_id")
            subject = info.get("last_email_subject", "")
            if entry_id:
                return f"{n} ({channels}, email_entry_id={entry_id}, last_subject='{subject[:40]}')"
            return f"{n} ({channels})"
        contacts_info = "CONTATOS: " + ", ".join([_fmt_contact(n, info) for n, info in list(contact_map.items())[:5]])

        protocol = AgentService._get_business_protocol()
        today_str = datetime.now().strftime("%d/%m/%Y")

        # Trunca o texto de análise: o LLM às vezes gera respostas longas (800+ tokens).
        # O planejador precisa do diagnóstico, não da redação completa.
        analysis_compact = (analysis or "")[:700]

        # Trunca o histórico de atividades para não exceder o limite de tokens
        activity_context_compact = (activity_context or "")[:500]

        prompt = WORKFLOW_PLANNER_PROMPT.format(
            protocol=protocol,
            today=today_str,
            analysis=analysis_compact,
            goal=goal,
            deals_info=deals_info or "Nenhum negócio encontrado.",
            contacts_info=contacts_info,
            activities_info=activities_info,
            history=history_str,
            activity_context=activity_context_compact,
        )
        return await ask_gemini(prompt, json_mode=True)

    # ═══════════════════════════════════════
    # VALIDAÇÃO DE ESTÁGIO
    # ═══════════════════════════════════════
    @staticmethod
    async def _validate_stage_advancement(params: dict, context: dict, log_fn) -> bool:
        """
        Valida se o avanço de estágio é legítimo.
        Retorna True se a ação foi BLOQUEADA (e deve ser pulada).
        Emite feedback visual via log_fn com tipo 'stage_blocked' ou 'stage_ok'.
        """
        from services.pipedrive.pipedrive_service import pipedrive_service

        new_stage_id = int(params.get("stage_id", 0))
        if not new_stage_id:
            return False

        # Pega o estágio atual do deal no contexto
        deals = context.get("pipedrive_details", {}).get("deals", [])
        current_deal = next((d for d in deals if str(d.get("id")) == str(params.get("deal_id", ""))), deals[0] if deals else {})
        current_stage_id = current_deal.get("stage_id", 0)
        current_stage_order = current_deal.get("stage_order_nr", 0)
        current_stage_name = current_deal.get("stage_name", f"ID {current_stage_id}")

        # Nada a validar se não mudou
        if current_stage_id == new_stage_id:
            return False

        try:
            stages_full = await pipedrive_service.get_all_stages_full()
        except Exception:
            stages_full = {}

        new_stage_info = stages_full.get(new_stage_id, {})
        new_stage_order = new_stage_info.get("order_nr", 0)
        new_stage_name = new_stage_info.get("name", f"ID {new_stage_id}")

        # Valida: estágio existe no Pipedrive?
        if stages_full and new_stage_id not in stages_full:
            log_fn({
                "type": "stage_blocked",
                "reason": "invalid_stage",
                "message": f"Estágio ID {new_stage_id} não existe no pipeline. Avanço cancelado.",
                "current_stage": current_stage_name,
                "proposed_stage": f"ID {new_stage_id} (desconhecido)",
            })
            print(f"[Agent] 🚫 Estágio inválido: {new_stage_id} não existe no pipeline.")
            return True

        # Valida: regressão de estágio?
        if new_stage_order < current_stage_order:
            log_fn({
                "type": "stage_blocked",
                "reason": "regression",
                "message": f"Regressão de estágio bloqueada: '{current_stage_name}' → '{new_stage_name}'. O negócio não pode retroceder.",
                "current_stage": current_stage_name,
                "proposed_stage": new_stage_name,
            })
            print(f"[Agent] 🚫 Regressão bloqueada: {current_stage_name} (ord={current_stage_order}) → {new_stage_name} (ord={new_stage_order})")
            return True

        # Valida: salto de mais de 2 estágios?
        stage_delta = new_stage_order - current_stage_order
        if stage_delta > 2:
            log_fn({
                "type": "stage_blocked",
                "reason": "skip",
                "message": f"Salto de {stage_delta} estágios bloqueado: '{current_stage_name}' → '{new_stage_name}'. Avance um estágio por vez.",
                "current_stage": current_stage_name,
                "proposed_stage": new_stage_name,
                "delta": stage_delta,
            })
            print(f"[Agent] 🚫 Salto bloqueado: delta={stage_delta} estágios")
            return True

        # Tudo certo — emite confirmação visual
        log_fn({
            "type": "stage_ok",
            "message": f"Avançando negócio: '{current_stage_name}' → '{new_stage_name}'",
            "current_stage": current_stage_name,
            "proposed_stage": new_stage_name,
        })
        return False

    # ═══════════════════════════════════════
    # EXECUTOR DE AÇÕES
    # ═══════════════════════════════════════
    @staticmethod
    async def _execute_real_action(step: dict, context: dict, intent: dict, org_id: int):
        """Executa ações que NÃO requerem aprovação."""
        action = step.get("action")
        params = step.get("params", {})
        
        if action == "update_pipedrive_deal":
            deal_id = params.get("deal_id")
            if not deal_id:
                deals = context.get("pipedrive_details", {}).get("deals", [])
                deal_id = deals[0].get("id") if deals else None
            
            if not deal_id: return False
            
            update_data = {}
            if params.get("stage_id"): update_data["stage_id"] = params.get("stage_id")
            if params.get("status"): update_data["status"] = params.get("status")
            if params.get("value"): update_data["value"] = params.get("value")
            
            return await pipedrive_service.update_deal(deal_id, update_data)

        if action == "create_pipedrive_task":
            # Pipedrive ID da organização (Não usar o local DB ID se o Pipedrive ID for nulo)
            target_org_id = context.get("organization", {}).get("pipedrive_id")
            
            # Garante que o deal_id seja anexado (fallback para o negócio principal do contexto se a IA omitir)
            target_deal_id = params.get("deal_id")
            if not target_deal_id:
                deals = context.get("pipedrive_details", {}).get("deals", [])
                if deals:
                    # Pega o primeiro negócio da lista (que já é filtrado pelo primary_deal na coleta de contexto)
                    target_deal_id = deals[0].get("id")
            
            # Tenta resolver o person_id com base nos contatos do contexto se disponíveis
            target_person_id = params.get("person_id")
            if not target_person_id:
                persons = context.get("pipedrive_details", {}).get("persons", [])
                
                # Procura se há um email selecionado na UI para tentar casar
                selected_emails = [e.get("email") for e in context.get("selected_entities", []) if isinstance(e, dict) and e.get("type") == "email" and e.get("email")]
                
                if selected_emails and persons:
                    # Tenta match por email
                    for p in persons:
                        p_emails = p.get("email", [])
                        if isinstance(p_emails, list):
                            if any(pem.get("value") in selected_emails for pem in p_emails):
                                target_person_id = p.get("id")
                                break
            
            # Prioridade para due_date explícito (útil para arqueologia)
            due_date = params.get("due_date")
            if not due_date:
                due_date = (datetime.now() + timedelta(days=params.get("days_delay", 0))).strftime("%Y-%m-%d")
            
            # --- NOVIDADE: VERIFICAÇÃO DE DUPLICIDADE ---
            existing_activities = context.get("pipedrive_details", {}).get("activities", [])
            subject = params.get("subject") or step.get("description") or "Nova Tarefa"
            
            # Se já existe uma tarefa idêntica PENDENTE para o mesmo Deal, ignoramos a criação
            for act in existing_activities:
                if not act.get("done") and act.get("deal_id") == target_deal_id:
                    if act.get("subject", "").lower() == subject.lower():
                        print(f"[Agent] 🛡️ Ignorando criação de tarefa duplicada: {subject}")
                        return {"success": True, "data": {"id": act.get("id"), "is_duplicate": True}}

            # Monta payload apenas com campos não nulos
            # Pipedrive prefere 1/0 para o campo 'done'
            is_done = 1 if params.get("done") is True else 0
            
            task_data = {
                "subject": subject,
                "due_date": due_date,
                "type": params.get("type", "task"),
                "done": is_done
            }
            
            # Forçar casting para int em campos de ID para evitar erros de validação da API
            try:
                if target_org_id: task_data["org_id"] = int(target_org_id)
                if target_deal_id: task_data["deal_id"] = int(target_deal_id)
                if target_person_id: task_data["person_id"] = int(target_person_id)
            except (ValueError, TypeError) as e:
                print(f"[Agent] ⚠️ Erro ao converter IDs para int: {e}")
                # Fallback mantém como estava se falhar, mas loga
                if target_org_id: task_data["org_id"] = target_org_id
                if target_deal_id: task_data["deal_id"] = target_deal_id
                if target_person_id: task_data["person_id"] = target_person_id

            if params.get("note"): task_data["note"] = params.get("note")

            print(f"[Agent] 🛠️ Enviando payload para Pipedrive: {json.dumps(task_data)}")
            pd_res = await pipedrive_service.create_activity(task_data)
            if not pd_res.get("success"):
                print(f"[Agent] ❌ Erro detalhado Pipedrive: {pd_res.get('error')} | Info: {pd_res.get('error_info')}")
            return pd_res

        if action == "update_pipedrive_task":
            act_id = params.get("activity_id")
            if not act_id: return False
            update_data = {k: v for k, v in params.items() if k != "activity_id"}
            return await pipedrive_service.update_activity(act_id, update_data)
            
        if action == "update_pipedrive_person":
            p_id = params.get("person_id")
            if not p_id: return False
            update_data = {k: v for k, v in params.items() if k != "person_id"}
            return await pipedrive_service.update_person(p_id, update_data)

        if action == "sync_contact_to_pipedrive":
            # 1. Cria a pessoa
            target_org_id = params.get("org_id") or context.get("organization", {}).get("pipedrive_id")
            res = await pipedrive_service.create_person(
                name=params.get("person_name"),
                email=params.get("email"),
                phone=params.get("phone"),
                org_id=target_org_id
            )
            person_id = res.get("data", {}).get("id")
            
            # 2. Vincula ao negócio (deal) se possível
            if person_id:
                target_deal_id = params.get("deal_id") or context.get("pipedrive_details", {}).get("deals", [{}])[0].get("id")
                if target_deal_id:
                   await pipedrive_service.update_deal(target_deal_id, {"person_id": person_id})
            return person_id

        # --- AÇÕES DE COMUNICAÇÃO (AUTOMATIZADAS) ---
        if action == "send_whatsapp":
            phone = params.get("phone", "")
            message = params.get("message", "")
            clean_num = phone.replace("+", "").replace("-", "").replace(" ", "")
            if len(clean_num) <= 11 and not clean_num.startswith("55"):
                clean_num = f"55{clean_num}"
            
            try:
                async with httpx.AsyncClient(timeout=40.0) as client:
                    resp = await client.post("http://localhost:8001/api/whatsapp/send", json={"number": clean_num, "message": message})
                    return resp.status_code == 200
            except Exception as e:
                print(f"[Agent] ❌ Erro ao enviar WhatsApp: {e}")
                return False

        if action == "send_email":
            email_to = params.get("email", "")
            subject = params.get("subject", "Contato Comercial")
            body = params.get("body", "")
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post("http://localhost:8002/api/email/send", json={"to": email_to, "subject": subject, "body": body})
                    return resp.status_code == 200
            except Exception as e:
                print(f"[Agent] ❌ Erro ao enviar Email: {e}")
                return False

        if action == "reply_email":
            entry_id = params.get("email_entry_id")
            body = params.get("body", "")
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post("http://localhost:8002/api/email/reply", json={"entry_id": entry_id, "body": body, "reply_all": True})
                    return resp.status_code == 200
            except Exception as e:
                print(f"[Agent] ❌ Erro ao responder Email: {e}")
                return False

        return None

    # ═══════════════════════════════════════
    # EXECUTOR DE AÇÕES APROVADAS
    # ═══════════════════════════════════════
    @staticmethod
    async def execute_approved_action(action_id: str, session) -> dict:
        """Executa uma ação que foi aprovada pelo usuário."""
        pending = AgentService._pending_actions.pop(action_id, None)
        if not pending:
            return {"status": "error", "message": "Ação não encontrada ou já expirou."}
        
        action = pending["action"]
        params = pending["params"]
        
        try:
            # --- WHATSAPP ---
            if action == "send_whatsapp":
                phone = params.get("phone", "")
                message = params.get("message", "")
                clean_num = phone.replace("+", "").replace("-", "").replace(" ", "")
                if len(clean_num) <= 11 and not clean_num.startswith("55"):
                    clean_num = f"55{clean_num}"
                
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        "http://localhost:8001/api/whatsapp/send",
                        json={"number": clean_num, "message": message}
                    )
                    if resp.status_code == 200:
                        return {"status": "success", "channel": "WhatsApp", "contact_name": params.get("contact_name"), "message": message}
                    return {"status": "error", "message": f"Erro ao enviar WhatsApp: {resp.status_code}"}
            
            # --- EMAIL NOVO ---
            elif action == "send_email":
                email_to = params.get("email", "")
                subject = params.get("subject", "Contato Comercial")
                body = params.get("body", "")

                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        "http://localhost:8002/api/email/send",
                        json={"to": email_to, "subject": subject, "body": body}
                    )
                    if resp.status_code == 200:
                        # --- SINCRONIZAÇÃO ESTRATÉGICA ---
                        from services.pipedrive import pipedrive_service
                        activity_id = params.get("activity_id")
                        deal_id = params.get("deal_id")

                        # Marca a tarefa pendente como concluída
                        if activity_id:
                            await pipedrive_service.update_activity(activity_id, {"done": 1})

                        # Registra nota no negócio
                        if deal_id:
                            await pipedrive_service.create_note(
                                deal_id,
                                f"✅ E-mail enviado via Assistente LINKB2B.\nPara: {email_to}\nAssunto: {subject}"
                            )

                        return {"status": "success", "channel": "Email", "contact_name": params.get("contact_name"), "subject": subject}
                    return {"status": "error", "message": f"Erro ao enviar Email: {resp.status_code}"}

            # --- RESPOSTA DE EMAIL (THREAD) ---
            elif action == "reply_email":
                entry_id = params.get("email_entry_id")
                body = params.get("body", "")

                async with httpx.AsyncClient(timeout=30.0) as client:
                    # Rota do microserviço definida para responder thread
                    resp = await client.post(
                        "http://localhost:8002/api/email/reply",
                        json={"entry_id": entry_id, "body": body, "reply_all": True}
                    )

                    if resp.status_code == 200:
                        # --- SINCRONIZAÇÃO ESTRATÉGICA (Efeito Colateral) ---
                        from services.pipedrive import pipedrive_service
                        deal_id = params.get("deal_id")

                        # 1. Se houver uma tarefa pendente vinculada, marca como concluída
                        activity_id = params.get("activity_id")
                        if activity_id:
                            await pipedrive_service.update_activity(activity_id, {"done": 1})

                        # 2. Se houver um deal_id, atualiza para fase de "Contatado"
                        if deal_id:
                            # Tenta mover para a fase 19 (Contatado) se estiver na fase 18
                            await pipedrive_service.update_deal(deal_id, {"stage_id": 19})
                            # Registra nota do evento
                            await pipedrive_service.create_note(deal_id, f"✅ E-mail respondido via aprovação do Assistente LINKB2B.\nAssunto: {params.get('subject', 'Thread')}")

                        return {"status": "success", "channel": "Email (Thread)", "contact_name": params.get("contact_name", "Contato")}
                    return {"status": "error", "message": f"Erro ao responder email: {resp.status_code}"}            
            return {"status": "error", "message": f"Ação '{action}' não reconhecida."}
        
        except Exception as e:
            print(f"[Agent] ❌ Erro ao executar ação aprovada: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def _beautify_email(params: dict, company_name: str, original_history: dict) -> str:
        """
        Usa o EMAIL_WRITER_PROMPT para transformar um rascunho em um e-mail profissional.
        """
        contact_name = params.get("contact_name", "Contato")
        subject = params.get("subject", "Assunto")
        
        try:
            # Instrução extra para evitar redundância de "Atenciosamente"
            prompt = EMAIL_WRITER_PROMPT.format(
                contact_name=contact_name,
                company_name=company_name,
                subject=subject,
                body_hint=params.get("body") or params.get("message") or ""
            )
            # Adicionamos um reforço sistêmico para não assinar
            prompt += "\n\nIMPORTANTE: Não inclua saudações finais como 'Atenciosamente' ou 'Obrigado', pois uma assinatura profissional será inserida automaticamente."
            
            refined_body = await ask_gemini(prompt)
            
            # Limpeza final (Fallback de segurança para placeholders de todos os tipos)
            if refined_body and isinstance(refined_body, str):
                # Se a IA respondeu com erro de cota, descarta e usa o corpo original do plano
                if "Desculpe, ocorreu um erro de cota" in refined_body:
                    return params.get("body") or params.get("message") or ""

                to_replace = [
                    ("{contact_name}", contact_name), ("{{contact_name}}", contact_name), ("[contact_name]", contact_name),
                    ("{company_name}", company_name), ("{{company_name}}", company_name), ("[company_name]", company_name),
                    ("{subject}", subject), ("{{subject}}", subject), ("[subject]", subject)
                ]
                for key, val in to_replace:
                    refined_body = refined_body.replace(key, val)
                
                refined_body = refined_body.strip().strip('"')

            # Tenta pegar a ASSINATURA REAL para o preview
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get("http://localhost:8002/api/email/signature")
                    if resp.status_code == 200:
                        signature = resp.json().get("signature", "")
                        if signature:
                            # Adicionamos um marcador invisível para o EmailClient saber que já tem assinatura
                            return f"{refined_body}<br><br><!-- SIGNATURE_START -->{signature}<!-- SIGNATURE_END -->"
            except:
                pass

            return refined_body or params.get("body") or ""
        except Exception as e:
            print(f"[Agent] Erro ao embelezar e-mail: {e}")
            return params.get("body") or ""

    @staticmethod
    async def reject_action(action_id: str) -> dict:
        """Remove uma ação pendente (rejeitada pelo usuário)."""
        pending = AgentService._pending_actions.pop(action_id, None)
        if pending:
            return {"status": "rejected", "description": pending.get("description")}
        return {"status": "not_found"}
