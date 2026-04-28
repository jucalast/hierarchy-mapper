import asyncio
import json
import uuid
import httpx
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from core.logging_config import get_logger
from services.external.base_gemini_service import ask_gemini
from services.pipedrive.pipedrive_service import pipedrive_service
from services.ai.data_fetcher import fetch_contextual_data
from services.ai.prompts import (
    WORKFLOW_ANALYSIS_PROMPT,
    WORKFLOW_PLANNER_PROMPT,
    DISTILL_AND_ANALYZE_PROMPT,
    EMAIL_WRITER_PROMPT,
    WHATSAPP_WRITER_PROMPT,
    FINAL_RESPONSE_PROMPT
)

log = get_logger(__name__)
# Ações que REQUEREM aprovação do usuário (Obrigatório para segurança)
ACTIONS_REQUIRING_APPROVAL = {"send_email", "reply_email", "send_whatsapp"}


# ─────────────────────────────────────────────────────────────────────────────
# Contexto compartilhado e progressivamente enriquecido ao longo do pipeline.
# Cada estágio lê apenas seus campos de entrada e escreve apenas seus de saída.
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PipelineContext:
    # ── Estágio 1: Dados coletados (Pipedrive + comunicações) ─────────────────
    org_name: str = ""
    organization: Dict = field(default_factory=dict)
    deals: List[dict] = field(default_factory=list)
    activities: List[dict] = field(default_factory=list)
    contacts: List[dict] = field(default_factory=list)       # Pipedrive persons
    email_result: dict = field(default_factory=dict)
    whatsapp_result: dict = field(default_factory=dict)

    # ── Estágio 2: Contatos resolvidos (contact_map) ──────────────────────────
    contact_map: Dict[str, dict] = field(default_factory=dict)
    emails_by_contact: Dict[str, list] = field(default_factory=dict)
    whatsapp_by_contact: Dict[str, list] = field(default_factory=dict)

    # ── Estágio 3: Destilação + Diagnóstico (1 LLM call) ─────────────────────
    distilled_facts: List[str] = field(default_factory=list)  # bullet points do que foi conversado
    deal_state: str = ""                                       # diagnóstico em 2-3 frases

    # ── Estágio 4: Plano de ação ──────────────────────────────────────────────
    plan: List[dict] = field(default_factory=list)

    # ── Estágio 5: Execução ───────────────────────────────────────────────────
    execution_results: List[dict] = field(default_factory=list)
    pending_approvals: List[dict] = field(default_factory=list)
    created_tasks: List[dict] = field(default_factory=list)

    # ── Flags ─────────────────────────────────────────────────────────────────
    using_cached_context: bool = False
    cold_lead: bool = False
    cold_contacts: List[dict] = field(default_factory=list)

    # ── Compatibilidade backward: mantém o raw dict original para métodos legados ──
    _raw: dict = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict) -> "PipelineContext":
        """Constrói um PipelineContext a partir do raw_context cacheado."""
        pd = raw.get("pipedrive_details", {})
        return cls(
            org_name=raw.get("organization", {}).get("name", ""),
            organization=raw.get("organization", {}),
            deals=pd.get("deals", []),
            activities=pd.get("activities", []),
            contacts=pd.get("persons", []),
            email_result=raw.get("email_result", {}),
            whatsapp_result=raw.get("whatsapp_result", {}),
            using_cached_context=True,
            cold_lead=raw.get("cold_lead", False),
            cold_contacts=raw.get("cold_contacts", []),
            _raw=raw,
        )

    def to_raw(self) -> dict:
        """Serializa de volta para o formato raw_context (para cache e métodos legados)."""
        base = dict(self._raw)
        base.update({
            "organization": self.organization,
            "pipedrive_details": {
                **self._raw.get("pipedrive_details", {}),
                "deals": self.deals,
                "activities": self.activities,
                "persons": self.contacts,
            },
            "email_result": self.email_result,
            "whatsapp_result": self.whatsapp_result,
            "cold_lead": self.cold_lead,
            "cold_contacts": self.cold_contacts,
            "emails_by_contact": self.emails_by_contact,
            "whatsapp_by_contact": self.whatsapp_by_contact,
            # distilled_facts como string para backward compat com cache
            "_precomputed_distilled": "\n".join(self.distilled_facts),
        })
        return base



class AgentService:
    """
    Serviço de Agente Autônomo de Vendas B2B.
    Pipeline de 5 estágios: Diagnóstico → Resolução de Contatos → Plano → Aprovação → Execução.
    """

    # Armazena ações pendentes de aprovação (in-memory, por sessão)
    _pending_actions: Dict[str, dict] = {}

    @staticmethod
    async def run_workflow(goal: str, initial_intent: dict, org_id: int, selected_entities: List[dict], session, log_queue: Optional[asyncio.Queue] = None, history: Optional[List[dict]] = None, initial_raw_context: Optional[dict] = None, thread_id: Optional[str] = None):
        """
        Executa o workflow completo do agente autônomo.
        """
        def emit(msg):
            if isinstance(msg, str):
                log.info("agent.workflow", msg=msg)
                if log_queue:
                    log_queue.put_nowait({"type": "log", "content": msg})
            else:
                if log_queue:
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
                emit({"type": "thought", "content": clean_thought, "icon": None})

        emit({"type": "status", "content": "Iniciando workflow..."})
        
        # ═══════════════════════════════════════
        # ESTÁGIO 1: Coleta de Dados → PipelineContext
        # ═══════════════════════════════════════
        raw_context = initial_raw_context or {}

        # Detecta se estamos usando contexto cacheado (de mensagem anterior na mesma thread)
        using_cached_context = bool(initial_raw_context)

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
        
        # ── Constrói o PipelineContext a partir dos dados coletados ──────────────
        if using_cached_context:
            ctx = PipelineContext.from_raw(raw_context)
        else:
            pd_stats = raw_context.get("pipedrive_details", {})
            ctx = PipelineContext(
                org_name=raw_context.get("organization", {}).get("name", "Empresa"),
                organization=raw_context.get("organization", {}),
                deals=pd_stats.get("deals", []),
                activities=pd_stats.get("activities", []),
                contacts=pd_stats.get("persons", []),
                email_result=raw_context.get("email_result", {}),
                whatsapp_result=raw_context.get("whatsapp_result", {}),
                using_cached_context=False,
                _raw=raw_context,
            )

        # ═══════════════════════════════════════
        # ESTÁGIO 2: Resolução de Contatos e Comunicações
        # ═══════════════════════════════════════
        # _resolve_contact_map ainda recebe o raw dict (sem refatorar internos)
        contact_map = await AgentService._resolve_contact_map(ctx.to_raw(), org_id, session)
        ctx.contact_map = contact_map

        # Mapeamento auxiliar por nome/email/telefone (usado no display e na execução)
        existing_emails = ctx.email_result.get("resultado", {}).get("messages_by_contact", [])
        existing_wa = ctx.whatsapp_result.get("resultado", {}).get("messages_by_contact", [])

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

        ctx.emails_by_contact = emails_by_contact
        ctx.whatsapp_by_contact = whatsapp_by_contact

        # Atalhos locais para variáveis já usadas no bloco de display abaixo
        pd_stats = raw_context.get("pipedrive_details", {})
        notes = pd_stats.get("notes", [])
        deals = ctx.deals
        activities = ctx.activities

        # ═══════════════════════════════════════════════
        # ESTÁGIO 3: Geração do Roteiro Narrativo (Estrategista de Vendas)
        # ═══════════════════════════════════════════════
        emit({"type": "status", "content": "Gerando análise estratégica...", "icon": "auto_awesome"})
        
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
        # Atalho de custo: skip da LLM se não há dados reais para narrar (evita alucinação e gasta API)
        has_real_data = bool(deal_info or activity_subjects or num_emails or num_wa)
        if not has_real_data:
            narrative_script = {
                "intro": f"Analisando {org_name} para '{goal}'. Nenhum dado de CRM ou comunicação encontrado ainda.",
                "tasks_reaction": "Sem atividades registradas no Pipedrive para este contexto.",
                "finding_people": f"Mapeando contatos disponíveis na empresa {org_name}.",
                "maturity_analysis": "Lead sem histórico — recomendado iniciar com prospecção a frio."
            }
        else:
            try:
                # Usa o Tier FAST para ser rápido e econômico
                from services.ai.llm import LLMTier, ask_llm
                script_res = await ask_llm(script_prompt, json_mode=True, tier=LLMTier.FAST, cacheable=True)
                narrative_script = script_res.json_data or {}
            except:
                emit("IA ocupada, seguindo com análise técnica...")

        # ═══════════════════════════════════════════════
        # ESTÁGIO 3: Descoberta de Negócio e Tarefas (Narrativa Intercalada)
        # ═══════════════════════════════════════════════
        
        # Se usando contexto cacheado, mostra resumo rápido em vez de todos os cards
        if using_cached_context:
            emit({"type": "status", "content": "Continuando conversa... (dados carregados da sessão anterior)", "icon": "cached"})
            org_name_cache = raw_context.get("organization", {}).get("name", "Empresa")
            deals_count = len(deals)
            acts_count = len(activities)
            await add_thought(f"Continuando diálogo sobre {org_name_cache}. {deals_count} negócios e {acts_count} atividades em contexto.")
        else:
            # 1. BLOCO: Negócio e Valores (modo completo)
            intro_text = narrative_script.get("intro", f"Vou analisar o contexto de '{goal}' no Pipedrive agora.")
            await add_thought(intro_text)
            await asyncio.sleep(0.8)
            
            for deal in deals:
                emit({"type": "data_found", "entity": "deal", "data": deal})

            await asyncio.sleep(0.5)

            # 2. BLOCO: Tarefas e Contexto (Reativo)
            if activities:
                tasks_text = narrative_script.get("tasks_reaction", "Analisando o padrão de atividades registradas.")
                await add_thought(tasks_text)
                await asyncio.sleep(0.8)
                for act in activities[:5]:
                    emit({"type": "data_found", "entity": "activity", "data": act})
            
            await asyncio.sleep(0.8)
            
            # 3. BLOCO: Pessoas e Comunicações
            people_text = narrative_script.get("finding_people", "Mapeando os principais interlocutores e histórico de mensagens.")
            await add_thought(people_text)
            emit({"type": "status", "content": "Cruzando histórico de comunicações...", "icon": "search"})

        # ── DETECÇÃO DE LEAD FRIO ───────────────────────────────────────────
        # Roda APÓS a coleta de dados, ANTES de exibir contatos ao usuário.
        # Não substitui nenhuma lógica existente — apenas enriquece o contexto.
        from services.ai.cold_lead_service import is_cold_lead, get_mapped_employees_for_cold_outreach
        _is_cold = is_cold_lead(raw_context)
        if _is_cold:
            _org_local_id = raw_context.get("organization", {}).get("local_id") or raw_context.get("org", {}).get("id")
            _cold_contacts = []
            if _org_local_id and session:
                try:
                    _cold_contacts = await get_mapped_employees_for_cold_outreach(int(_org_local_id), session)
                except Exception as _e:
                    log.warning("agent.cold_contacts_error", error=str(_e))

            if _cold_contacts:
                emit({"type": "status", "content": "🧊 Lead frio — usando contatos mapeados para prospecção", "icon": "person_search"})
                # Injeta no contact_map para que o agente os use ao planejar ações
                for _cc in _cold_contacts:
                    _cname = _cc["name"]
                    contact_map[_cname] = _cc
                raw_context["cold_lead"] = True
                raw_context["cold_contacts"] = _cold_contacts
                ctx.cold_lead = True
                ctx.cold_contacts = _cold_contacts
            else:
                emit({"type": "suggest_mapping", "message": "Empresa sem histórico de comunicação e sem contatos mapeados. Recomendo rodar o Mapeamento de Hierarquia para identificar os compradores antes de iniciar a prospecção.", "org_name": org_name})
                raw_context["cold_lead"] = True
                raw_context["cold_contacts"] = []
                ctx.cold_lead = True
                ctx.cold_contacts = []
        # ── FIM DETECÇÃO DE LEAD FRIO ───────────────────────────────────────

        # Marcar entidades selecionadas no mapa e logar
        selected_names = [e.get("name") for e in selected_entities]
        logged_count = 0
        
        # Se usando cache, apenas resumo rápido dos contatos (não mostra todos os cards)
        if using_cached_context:
            contacts_with_comms = sum(1 for name in contact_map if 
                emails_by_contact.get(name.lower()) or whatsapp_by_contact.get(name.lower()))
            if contact_map:
                emit({"type": "log", "content": f"{len(contact_map)} contatos disponíveis, {contacts_with_comms} com comunicação."})
        else:
            # Loga Contatos e Comunicações de forma intercalada (modo completo)
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
                    emit({"type": "data_found", "entity": "contact", "data": info, "label": "Prioritário" if is_key_contact else None})
                    await asyncio.sleep(0.4)

                    if has_comms:
                        await add_thought(f"Encontrei histórico de conversas com {name}. Vou analisar o tom da negociação...")
                        await asyncio.sleep(0.6)

                        if person_emails:
                            # Emite todos os threads deste contato (até 5), não só o primeiro
                            for email_thread in person_emails[:5]:
                                emit({
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
                            # Emite o card visual do WhatsApp (Thread Completa)
                            # O frontend espera uma estrutura específica: data.whatsapp_result.resultado.messages
                            emit({
                                "type": "data_found",
                                "entity": "whatsapp",
                                "data": {
                                    "whatsapp_result": {
                                        "resultado": {
                                            "messages": person_wa
                                        },
                                        "contact": {"name": name, "phone": info.get("phone")}
                                    }
                                }
                            })
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
                emit({"type": "log", "content": f"... e mais {remaining} contatos mapeados."})

        # Injeta no contexto para análise de maturidade
        raw_context["emails_by_contact"] = emails_by_contact
        raw_context["whatsapp_by_contact"] = whatsapp_by_contact

        # PENSAMENTO 3: Análise de Maturidade e Próximos Passos
        maturity_text = narrative_script.get("maturity_analysis", "Analisando maturidade das interações para definir estratégia.")
        await add_thought(maturity_text)
        
        # Pausa reduzida para performance
        await asyncio.sleep(1.0)

        emit({"type": "status", "content": "Gerando estratégia e plano de ação...", "icon": "auto_awesome"})

        # ── ESTÁGIO 3: Destilação + Diagnóstico (1 LLM call, substitui 2 antigas) ──
        log.debug("agent.distill_start")
        await AgentService._distill_and_analyze(ctx)

        # Exibe os fatos destilados como pensamento na UI
        if ctx.distilled_facts:
            await add_thought("\n".join(ctx.distilled_facts[:8]))
            await asyncio.sleep(0.5)

        # Mantém raw_context sincronizado (para métodos legados que ainda leem dele)
        raw_context["_precomputed_distilled"] = "\n".join(ctx.distilled_facts)
        deal_analysis = ctx.deal_state  # compat com exec_context no estágio 6

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
                    emit({"type": "status", "content": "Consultando histórico de interações...", "icon": "history"})
            except Exception as act_err:
                log.warning("agent.activity_log_failed", error=str(act_err))

        try:
            plan_raw = await AgentService._create_logical_plan(goal, ctx, contact_map, selected_entities, history=history, activity_context=activity_context_str)
            
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
            log.warning("agent.plan_fallback", error=str(e))
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
            emit({"type": "log", "content": "⚠️ IA instável. Aplicando plano de contingência para garantir o follow-up.", "status": "warning"})

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
            contact_name = (params.get("contact_name") or "").strip()
            org_name_lower = (raw_context.get("organization", {}).get("name") or "").lower()
            pd_persons = raw_context.get("pipedrive_details", {}).get("persons", [])

            # Se a IA colocou o nome da organização como contact_name (erro comum),
            # ou se não há contact_name, usa o primeiro contato real do Pipedrive
            if not contact_name or contact_name.lower() == org_name_lower:
                if pd_persons:
                    contact_name = pd_persons[0].get("name") or contact_name
                # Segunda tentativa: pega o primeiro contato do contact_map com preferência pelo canal da ação
                if (not contact_name or contact_name.lower() == org_name_lower) and contact_map:
                    for _cname, _cinfo in contact_map.items():
                        if action == "send_whatsapp" and _cinfo.get("whatsapp_available"):
                            contact_name = _cname
                            break
                        elif "email" in action and _cinfo.get("email_available"):
                            contact_name = _cname
                            break
                    if not contact_name or contact_name.lower() == org_name_lower:
                        contact_name = next(iter(contact_map), contact_name) or "Contato"

            params["contact_name"] = contact_name

            # Resolve Phone/Email via contact_map se estiverem vazios (Enriquecimento de Ação)
            if contact_map:
                # Tenta match exato primeiro, depois case-insensitive
                info = contact_map.get(contact_name)
                if not info:
                    info = next((v for k, v in contact_map.items() if k.lower() == contact_name.lower()), None)
                
                if info:
                    if not params.get("phone") and info.get("phone"):
                        params["phone"] = info["phone"]
                        log.debug("agent.contact_phone_resolved", contact=contact_name)
                    if not params.get("email") and info.get("email"):
                        params["email"] = info["email"]
                        log.debug("agent.contact_email_resolved", contact=contact_name)

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
                            log.debug("agent.email_entry_resolved_fallback", contact=_name)
                            break
                    # Se ainda não encontrou, degrada para send_email com log de aviso
                    if not params.get("email_entry_id"):
                        action = "send_email"
                        step["action"] = "send_email"
                        emit({"type": "log", "content": "⚠️ Thread não encontrado — enviando como novo e-mail.", "status": "warning"})

                emit({"type": "log", "content": f"📝 Sugestão de {channel} preparada para {contact_name}...", "status": "pending"})

                # Refinamento de IA para o corpo da mensagem
                if "email" in action:
                    params["body"] = await AgentService._beautify_email(
                        params,
                        raw_context.get("organization", {}).get("name", "Empresa"),
                        original_history=raw_context
                    )
                elif action == "send_whatsapp":
                    params["message"] = await AgentService._beautify_whatsapp(
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
                # Enriquecimento de Params para o Executor
                if contact_name in contact_map:
                    info = contact_map[contact_name]
                    if not params.get("pipedrive_person_id") and info.get("pipedrive_person_id"):
                        params["pipedrive_person_id"] = info["pipedrive_person_id"]

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
            emit(f"Executando: {desc}")
            try:
                result = await AgentService._execute_real_action(step, raw_context, initial_intent, org_id, session, thread_id)
            except Exception as e:
                log.error("agent.action_exec_error", action=action, error=str(e))
                emit(f"❌ Falha técnica ao executar {desc}: {str(e)}")
                result = None

            # Tratamento de log de sucesso/erro
            if action == "update_pipedrive_deal" and result:
                if isinstance(result, dict) and result.get("success"):
                    deal_id = params.get("deal_id") or (raw_context.get("pipedrive_details", {}).get("deals", [{}])[0].get("id"))
                    emit({"type": "log", "content": f"🚀 Negócio atualizado no Pipedrive (ID: {deal_id})", "status": "success"})
                    execution_results.append({"description": desc, "status": "success"})
                else:
                    err = result.get("error") if isinstance(result, dict) else "Erro desconhecido"
                    emit(f"❌ Falha ao atualizar negócio no Pipedrive: {err}")
                    execution_results.append({"description": desc, "status": "failed", "error": err})
            elif action == "create_pipedrive_task" and result:
                if isinstance(result, dict) and result.get("success"):
                    act_id = result.get("data", {}).get("id")
                    emit({"type": "log", "content": f"✅ Atividade criada no Pipedrive (ID: {act_id})", "status": "success"})
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
                    emit(f"❌ Falha ao criar atividade no Pipedrive: {err}")
                    execution_results.append({"description": desc, "status": "failed", "error": err})
            elif action in ["send_whatsapp", "send_email", "reply_email"]:
                status = "success" if result else "failed"
                emit({"type": "log", "content": f"{'✅' if result else '❌'} {channel} para {contact_name}: {status.upper()}", "status": status})
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

        # Descreve as aprovações pendentes de forma que a IA não confunda com "enviado"
        pending_desc = []
        for pa in pending_approvals:
            ch = "WhatsApp" if "whatsapp" in pa.get("action_type", "") else "E-mail"
            pending_desc.append(f"{ch} para {pa.get('contact_name','?')} — AGUARDANDO APROVAÇÃO DO USUÁRIO (não enviado)")

        exec_context = (
            f"Canais: {', '.join(channels_checked) or 'nenhum'}\n"
            f"Diagnóstico: {(deal_analysis or '')[:500]}\n"
            f"Executadas: {json.dumps(_compact_results([r for r in execution_results if r.get('status') == 'success']))}\n"
            f"Falhas: {json.dumps(_compact_results([r for r in execution_results if r.get('status') == 'failed']))}\n"
            f"Aprovações pendentes: {len(pending_approvals)}\n"
            f"Detalhes pendentes: {'; '.join(pending_desc) or 'nenhum'}"
        )
        
        executive_summary = await ask_gemini(FINAL_RESPONSE_PROMPT.format(context=exec_context))
        
        # Se falhou por cota, usa um fallback amigável em vez da mensagem de erro crua
        if isinstance(executive_summary, str) and "Desculpe, ocorreu um erro de cota" in executive_summary:
            executive_summary = f"Concluí as ações para **{org_name}**. O plano foi executado e as atividades foram registradas no CRM conforme solicitado."

        # Strip qualquer [[NEW_TASKS]] que o LLM possa ter inserido no meio da summary
        # (o placeholder só é válido no FINAL da mensagem, adicionado programaticamente)
        clean_summary = (executive_summary or "").replace("[[NEW_TASKS]]", "").strip()

        full_response_parts = [clean_summary]

        # Reinsere o marcador [[NEW_TASKS]] no lugar correto (final) para o frontend renderizá-lo
        if created_tasks:
            full_response_parts.append("\n\n[[NEW_TASKS]]")

        final_content = "\n\n".join(full_response_parts)

        # Envia a resposta final
        emit({"type": "final_response", "content": final_content})
        
        # SINAL DE CONCLUSÃO TOTAL (Limpa todos os spinners residuais)
        emit({"type": "status", "content": "Concluído", "status": "done", "icon": "done_all"})
        emit({"type": "finish"})
        
        return {
            "status": "completed",
            "full_response": "\n\n".join(full_response_parts),
            "past_activities": ctx.activities,
            "new_activities": created_tasks,
            "organization_data": ctx.organization,
            "pending_approvals": pending_approvals,
            "_internal_context": ctx.to_raw()  # serializado para cache entre mensagens
        }

    # ═══════════════════════════════════════
    # RESOLUÇÃO DE CONTATOS (Mapa de Alcance)
    # ═══════════════════════════════════════
    @staticmethod
    def _is_real_wa_message(msg: dict) -> bool:
        """
        Filtra mensagens WhatsApp espúrias: blobs base64, stickers sem contexto.
        Retorna True para mensagens com conteúdo legível ou mídias identificáveis.
        """
        body = msg.get("body") or msg.get("caption") or ""
        msg_type = (msg.get("type") or "chat").lower()

        # Mídias são interações REAIS, mesmo sem legenda (exceto stickers que podem ser ruído)
        if msg_type in ("image", "video", "audio", "document", "ptt", "vcard"):
            return True

        if msg_type == "sticker":
            # Aceita sticker apenas se tiver legenda ou se for o único contexto (não filtramos por enquanto)
            return True

        if not body:
            return False

        # Detecta base64: string longa sem espaços ou pontuação comum de texto
        if len(body) > 100:
            has_spaces = " " in body
            has_text_punctuation = any(c in body for c in [".", "!", "?", ",", "\n", ":", ";"])
            if not has_spaces and not has_text_punctuation:
                return False

        # Mensagem muito curta e sem contexto
        if len(body.strip()) < 1:
            return False

        return True

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
                    
                    # WhatsApp só é considerado disponível se houver histórico REAL de mensagens de texto.
                    # Ter apenas o número cadastrado no Pipedrive NÃO garante que há conversa no WhatsApp.
                    wa_res = context.get("whatsapp_result", {}).get("resultado", {}).get("messages_by_contact", [])
                    person_wa_msgs = [m for m in wa_res if (m.get("contact") or "").lower() == name.lower()]
                    # Filtra apenas mensagens de texto reais (exclui blobs base64 e mídias sem legenda)
                    real_wa_msgs = [
                        m for group in person_wa_msgs
                        for m in group.get("messages", [])
                        if AgentService._is_real_wa_message(m)
                    ]
                    wa_msg_count = len(real_wa_msgs)
                    has_wa_history = wa_msg_count > 0

                    channels = []
                    # WA disponível SOMENTE se existe histórico real de texto — nunca apenas por ter telefone
                    wa_available = has_wa_history
                    if phone:
                        channels.append("Telefone")
                    
                    if wa_available and "WhatsApp" not in channels:
                        channels.append("WhatsApp")
                    
                    if email:
                        channels.append("Email")
                    
                    if not channels:
                        continue # Pula contatos sem nenhuma forma de comunicação
                    
                    # Determina o canal preferencial baseado no volume de histórico REAL
                    email_res = context.get("email_result", {}).get("resultado", {}).get("messages_by_contact", [])
                    person_emails = [g for g in email_res if (g.get("contact") or "").lower() == name.lower()]
                    email_msg_count = sum(len(g.get("human_threads", [])) for g in person_emails)

                    if wa_msg_count > email_msg_count:
                        preferred_channel = "WhatsApp"
                    elif email_msg_count > 0:
                        preferred_channel = "Email"
                    else:
                        preferred_channel = "WhatsApp" if wa_available else "Email" if email else "Nenhum"

                    contact_map[name] = {
                        "name": name,
                        "pipedrive_person_id": p.get("id"),
                        "phone": phone,
                        "email": email,
                        "whatsapp_available": wa_available,
                        "email_available": bool(email),
                        "channels": channels,
                        "preferred_channel": preferred_channel,
                        "wa_msg_count": wa_msg_count,
                        "email_msg_count": email_msg_count,
                        "source": "Pipedrive",
                        "last_email_id": None
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
                        log.debug("agent.org_not_in_db", pipedrive_org_id=org_id)
                        local_employees = []
                    else:
                        stmt = select(Employee).where(Employee.company_id == local_org.id)
                        res = await session.execute(stmt)
                        local_employees = res.scalars().all()
                        log.debug("agent.org_employees_found", org_id=local_org.id, employees=len(local_employees))
                    
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
                        
                        # Se já existe no mapa (via Pipedrive), apenas enriquece se faltar algo, não sobrescreve a fonte primária
                        if emp.name in contact_map:
                            if not contact_map[emp.name].get("phone") and emp.whatsapp_number:
                                contact_map[emp.name]["phone"] = emp.whatsapp_number
                                contact_map[emp.name]["whatsapp_available"] = True
                            if not contact_map[emp.name].get("email") and emp.email:
                                contact_map[emp.name]["email"] = emp.email
                                contact_map[emp.name]["email_available"] = True
                            continue

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
                    log.warning("agent.local_contacts_error", error=str(e))

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

            # --- PÓS-PROCESSAMENTO UNIFICADO (COMUNICAÇÕES) ---
            # Garante que todos os contatos (independente da fonte) tenham sua preferência e disponibilidade
            # calculadas com base no histórico real encontrado no contexto.
            wa_res = context.get("whatsapp_result", {}).get("resultado", {}).get("messages_by_contact", [])
            email_res = context.get("email_result", {}).get("resultado", {}).get("messages_by_contact", [])

            for name, info in contact_map.items():
                name_low = name.lower()
                email_low = (info.get("email") or "").lower()
                phone_raw = info.get("phone")

                # Busca mensagens de WA para este contato — apenas mensagens de texto reais
                p_wa_groups = [m for m in wa_res if (m.get("contact") or "").lower() == name_low or (phone_raw and m.get("contact") == phone_raw)]
                wa_count = sum(
                    1 for group in p_wa_groups
                    for m in group.get("messages", [])
                    if AgentService._is_real_wa_message(m)
                )

                # Busca threads de Email para este contato
                p_emails = [g for g in email_res if (g.get("contact") or "").lower() == name_low or (email_low and (g.get("email") or "").lower() == email_low)]
                email_count = sum(len(g.get("human_threads", [])) for g in p_emails)

                # WA disponível SOMENTE se há mensagens de texto reais — não por ter telefone ou número WA
                if wa_count > 0:
                    info["whatsapp_available"] = True
                    if "WhatsApp" not in info["channels"]:
                        info["channels"].append("WhatsApp")
                else:
                    # Garante que não herdamos um True espúrio de etapas anteriores sem histórico real
                    if info.get("whatsapp_available") and info.get("wa_msg_count", 0) == 0:
                        info["whatsapp_available"] = False
                        if "WhatsApp" in info.get("channels", []):
                            info["channels"] = [c for c in info["channels"] if c != "WhatsApp"]
                
                if email_count > 0:
                    info["email_available"] = True
                    if "Email" not in info["channels"]:
                        info["channels"].append("Email")
                
                # Atualiza os contadores reais para o Planner ver
                info["wa_msg_count"] = wa_count
                info["email_msg_count"] = email_count
                
                # Determina Canal Preferencial com base no volume
                if wa_count > email_count:
                    info["preferred_channel"] = "WhatsApp"
                elif email_count > 0:
                    info["preferred_channel"] = "Email"
                else:
                    # Fallback por disponibilidade técnica se não houver histórico
                    wa_ok = info.get("whatsapp_available")
                    em_ok = info.get("email_available")
                    info["preferred_channel"] = "WhatsApp" if wa_ok else "Email" if em_ok else "Nenhum"
        
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

    # ═══════════════════════════════════════
    # DESTILAÇÃO + DIAGNÓSTICO (1 LLM call)
    # ═══════════════════════════════════════
    @staticmethod
    async def _distill_and_analyze(ctx: "PipelineContext") -> None:
        """
        Estágio 3 do pipeline: substitui as 2 chamadas separadas (distill + analyze)
        por uma única chamada estruturada que preenche ctx.distilled_facts e ctx.deal_state.

        Input:  ctx.email_result, ctx.whatsapp_result, ctx.activities
        Output: ctx.distilled_facts (List[str]), ctx.deal_state (str)
        """
        from services.ai.llm import LLMTier, ask_llm

        # ── Monta o bloco de comunicações brutas (mesmo pré-processamento do _distill_communications) ──
        all_text = []
        email_groups = ctx.email_result.get("resultado", {}).get("messages_by_contact", [])
        for g in email_groups:
            for m in g.get("human_threads", [])[:3]:
                body = (m.get("body") or "").strip()
                if not body:
                    continue
                trunc = body[:350]
                for delim in (". ", "! ", "? ", "\n"):
                    last = trunc.rfind(delim)
                    if last > 150:
                        trunc = trunc[:last + 1]
                        break
                sender_raw = (m.get("sender") or "").lower()
                to_raw = (m.get("to") or "").lower()
                if sender_raw.startswith("/o=") or "jferres.com.br" in sender_raw:
                    direction = "Eu→Cliente"
                elif "@" in sender_raw and "jferres.com.br" not in sender_raw:
                    direction = "Cliente→Eu"
                else:
                    direction = "Eu→Cliente" if ("@" in to_raw and "jferres.com.br" not in to_raw) else "Cliente→Eu"
                all_text.append(f"Email {m.get('date','')[:10]} [{direction}]: {trunc.strip()}")

        wa_groups = ctx.whatsapp_result.get("resultado", {}).get("messages_by_contact", [])
        for g in wa_groups:
            real_wa = [m for m in g.get("messages", []) if AgentService._is_real_wa_message(m)]
            for m in real_wa[:5]:
                body = (m.get("body") or "").strip()
                trunc = body[:180]
                if len(body) > 180 and " " in trunc:
                    trunc = trunc[:trunc.rfind(" ")]
                sender = "Eu" if m.get("fromMe") else "Cliente"
                all_text.append(f"WA {m.get('date_human','')[:10]} ({sender}): {trunc}")

        if not all_text:
            ctx.distilled_facts = []
            ctx.deal_state = "Sem histórico de comunicações encontrado."
            return

        # ── Atividades compactas para o diagnóstico ────────────────────────────────
        acts_str = "\n".join([
            f"- {a.get('subject')} (ID:{a.get('id')}, {'OK' if a.get('done') else 'PENDENTE'})"
            for a in ctx.activities[:8]
        ]) or "Nenhuma"

        communications_str = "\n".join(all_text)

        try:
            res = await ask_llm(
                DISTILL_AND_ANALYZE_PROMPT.format(
                    activities=acts_str,
                    communications=communications_str,
                ),
                tier=LLMTier.FAST,
                json_mode=True,
                cacheable=True,
            )
            data = res.json_data or {}
            ctx.distilled_facts = data.get("facts", [])
            ctx.deal_state = data.get("deal_state", "")
        except Exception as e:
            log.warning("agent.distill_fallback", error=str(e))
            # Fallback: facts como linha única, deal_state vazio
            ctx.distilled_facts = [f"- {line}" for line in all_text[:6]]
            ctx.deal_state = "Análise indisponível, seguindo com plano baseado nos dados do CRM."

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

        # Coleta WhatsApp — top 5 msgs de texto real, 180 chars
        wa_groups = wa_result.get("resultado", {}).get("messages_by_contact", [])
        for g in wa_groups:
            real_wa = [m for m in g.get("messages", []) if AgentService._is_real_wa_message(m)]
            for m in real_wa[:5]:
                body = (m.get("body") or "").strip()
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
        from services.ai.llm import LLMTier, ask_llm
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

        history_summary += "\n=== STATUS DO CRM (VERDADE ABSOLUTA - ATIVIDADES REALIZADAS) ===\n"
        for i, act in enumerate(activities[:8]):
            status = "CONCLUÍDA (OK)" if act.get("done") else "PENDENTE (EM ABERTO)"
            note_snip = (act.get("note_clean") or "")[:150].replace("\n", " ").strip()
            note_part = f" | Nota: {note_snip}" if note_snip else ""
            history_summary += f"- [{i+1}] {act.get('due_date')}: {act.get('subject')} -> Status: {status}{note_part}\n"
        
        # DESTILAÇÃO DE COMUNICAÇÕES — usa resultado pré-computado se disponível (evita chamada dupla)
        distilled = context.get("_precomputed_distilled")
        if distilled is None:
            log.debug("agent.distill_fallback_start")
            distilled = await AgentService._distill_communications(
                context.get("email_result", {}),
                context.get("whatsapp_result", {})
            )

        history_summary += f"\n=== ARQUEOLOGIA DE COMUNICAÇÕES (HISTÓRICO DE CHAT) ===\n{distilled}\n"

        # Injeção de Status Calculado (Cross-channel)
        calc_status = context.get("calculated_status", {})
        if calc_status:
            history_summary += f"\n📊 ANÁLISE DE TEMPO REAL (Métrica LINKB2B):\n"
            history_summary += f"- {calc_status.get('summary')}\n"
        else:
            history_summary += f"\n⏳ ALERTA DE CICLO: Verificando momentum...\n"

        # Atalho de custo: se não há deals nem atividades nem comunicações, sem contexto para analisar
        distilled_check = context.get("_precomputed_distilled", "")
        has_no_context = (
            not deals and not activities and not notes
            and (not distilled_check or "Nenhuma comunicação" in distilled_check)
        )
        if has_no_context:
            return (
                "Lead sem histórico no CRM e sem comunicações anteriores. "
                "Recomendação: iniciar prospecção a frio com apresentação institucional."
            )

        # Para análise, precisamos da identidade (seção 1) + anti-alucinação (seção 3).
        # 900 chars cobre as 3 primeiras seções, incluindo as regras críticas de evidência obrigatória.
        # O protocolo completo vai para o planejamento (onde as ações são definidas).
        protocol = AgentService._get_business_protocol()
        protocol_short = protocol[:900]  # cobre seções 1, 2 e 3 (Anti-Alucinação)
        prompt = WORKFLOW_ANALYSIS_PROMPT.format(
            protocol=protocol_short,
            history_summary=history_summary
        )
        # Usa ask_llm (cacheable=True) em vez de ask_gemini para aproveitar o cache da sessão
        try:
            res = await ask_llm(prompt, tier=LLMTier.STANDARD, cacheable=True)
            return res.text
        except Exception:
            # Fallback para ask_gemini legado se o router falhar
            return await ask_gemini(prompt)

    # ═══════════════════════════════════════
    # PLANO DE AÇÃO ESTRATÉGICO
    # ═══════════════════════════════════════
    # PLANO DE AÇÃO ESTRATÉGICO
    # ═══════════════════════════════════════
    @staticmethod
    async def _create_logical_plan(
        goal: str,
        ctx: "PipelineContext",
        contact_map: dict,
        selected_entities: List[dict],
        history: List[dict] = None,
        activity_context: str = "",
    ):
        """
        Estágio 4: gera o plano de ações concretas a partir do PipelineContext.

        Recebe dados estruturados (ctx.distilled_facts, ctx.deal_state, ctx.deals,
        ctx.activities) — sem truncagem arbitrária de texto interpretado.
        """
        # ── Deals compactos ───────────────────────────────────────────────────
        deals_info = "\n".join([
            f"- ID: {d.get('id')} | Título: {d.get('title')} | Valor: {d.get('formatted_value')} | Fase: {d.get('stage_name')}"
            for d in ctx.deals[:3]
        ])

        # ── Atividades existentes (incluindo ID para update_pipedrive_task) ──
        activities_info = "TAREFAS NO CRM: " + (
            ", ".join([
                f"{a.get('subject')} (ID: {a.get('id')}, {'OK' if a.get('done') else 'PENDENTE'})"
                for a in ctx.activities[:8]
            ]) if ctx.activities else "Nenhuma"
        )

        # ── Histórico da conversa (últimas 4 msgs, 400 chars cada) ───────────
        history_str = ""
        if history:
            history_str = "\n".join([
                f"{h.get('role')}: {h.get('content','')[:400]}" for h in history[-4:]
            ])

        # ── Mapa de contatos compacto com REPLY-FIRST e canal preferencial ───
        def _fmt_contact(n, info):
            pref = info.get("preferred_channel", "Email").upper()
            channels = "/".join(info.get("channels", []))
            entry_id = info.get("last_email_id")
            subject = info.get("last_email_subject", "")
            base_info = f"{n} [CANAL PREFERIDO: {pref}] ({channels})"
            if entry_id:
                return f"{base_info}, email_entry_id={entry_id}, last_subject='{subject[:40]}'"
            return base_info

        contacts_info = "CONTATOS: " + ", ".join([
            _fmt_contact(n, info) for n, info in list(contact_map.items())[:5]
        ])

        # ── Fatos de comunicação — lista estruturada, sem truncagem ──────────
        # distilled_facts já são bullet points curtos produzidos por _distill_and_analyze
        facts_str = "\n".join(ctx.distilled_facts[:20]) if ctx.distilled_facts else "(Sem comunicações registradas)"

        # ── Diagnóstico do negócio — curto por design (2-3 frases) ───────────
        deal_state = ctx.deal_state or "Sem diagnóstico disponível."

        # ── Histórico de atividades recentes do agente ───────────────────────
        activity_context_compact = (activity_context or "")[:700]

        # ── Contexto de Lead Frio ─────────────────────────────────────────────
        cold_context_str = ""
        if ctx.cold_lead:
            if ctx.cold_contacts:
                contact_lines = [
                    f"  - {cc['name']} ({cc.get('department','')}{' — ' + cc.get('role','') if cc.get('role') else ''}) [{'/'.join(cc.get('channels',[]))}]"
                    for cc in ctx.cold_contacts[:4]
                ]
                cold_context_str = (
                    "🧊 LEAD FRIO — PROSPECÇÃO A FRIO:\n"
                    "Esta empresa não possui histórico de comunicação com J.Ferres.\n"
                    "Contatos mapeados para abordagem inicial:\n"
                    + "\n".join(contact_lines)
                    + "\nUse tom introdutório. PROIBIDO referenciar conversas ou pedidos anteriores."
                )
            else:
                cold_context_str = (
                    "🧊 LEAD FRIO — SEM CONTATOS MAPEADOS:\n"
                    "Esta empresa não possui histórico e não tem contatos mapeados no sistema.\n"
                    "Gere uma tarefa para agendar prospecção manual ou aguarde o Mapeamento de Hierarquia ser executado."
                )

        prompt = WORKFLOW_PLANNER_PROMPT.format(
            protocol=AgentService._get_business_protocol(),
            today=datetime.now().strftime("%d/%m/%Y"),
            deal_state=deal_state,
            goal=goal,
            deals_info=deals_info or "Nenhum negócio encontrado.",
            contacts_info=contacts_info,
            activities_info=activities_info,
            history=history_str,
            activity_context=activity_context_compact,
            cold_context=cold_context_str,
            facts=facts_str,
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

        raw_stage_id = params.get("stage_id", 0)
        new_stage_id = 0
        
        # Tenta converter para int de forma segura
        try:
            if isinstance(raw_stage_id, str) and not raw_stage_id.isdigit():
                # IA enviou o Nome do Estágio em vez do ID. Vamos tentar resolver.
                stages_map = await pipedrive_service.get_all_stages()
                # Busca reversa (nome -> id)
                for sid, sname in stages_map.items():
                    if sname.lower() == raw_stage_id.lower():
                        new_stage_id = int(sid)
                        params["stage_id"] = new_stage_id # Corrige no param para a execução
                        break
            else:
                new_stage_id = int(raw_stage_id)
        except (ValueError, TypeError):
            new_stage_id = 0

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
            log.info(
                "agent.stage_blocked",
                type="stage_blocked",
                reason="invalid_stage",
                message=f"Estágio ID {new_stage_id} não existe no pipeline. Avanço cancelado.",
                current_stage=current_stage_name,
                proposed_stage=f"ID {new_stage_id} (desconhecido)",
            )
            log.warning("agent.invalid_stage", stage_id=new_stage_id)
            return True

        # Valida: regressão de estágio?
        if new_stage_order < current_stage_order:
            log.info(
                "agent.stage_blocked",
                type="stage_blocked",
                reason="regression",
                message=f"Regressão de estágio bloqueada: '{current_stage_name}' → '{new_stage_name}'. O negócio não pode retroceder.",
                current_stage=current_stage_name,
                proposed_stage=new_stage_name,
            )
            log.warning("agent.stage_regression_blocked", from_stage=current_stage_name, to_stage=new_stage_name)
            return True

        # Valida: salto de mais de 2 estágios?
        stage_delta = new_stage_order - current_stage_order
        if stage_delta > 2:
            log.info(
                "agent.stage_blocked",
                type="stage_blocked",
                reason="skip",
                message=f"Salto de {stage_delta} estágios bloqueado: '{current_stage_name}' → '{new_stage_name}'. Avance um estágio por vez.",
                current_stage=current_stage_name,
                proposed_stage=new_stage_name,
                delta=stage_delta,
            )
            log.warning("agent.stage_jump_blocked", delta=stage_delta)
            return True

        # Tudo certo — emite confirmação visual
        log.info(
            "agent.stage_ok",
            type="stage_ok",
            message=f"Avançando negócio: '{current_stage_name}' → '{new_stage_name}'",
            current_stage=current_stage_name,
            proposed_stage=new_stage_name,
        )
        return False

    # ═══════════════════════════════════════
    # EXECUTOR DE AÇÕES
    # ═══════════════════════════════════════
    @staticmethod
    async def _execute_real_action(step: dict, context: dict, intent: dict, org_id: int, session, thread_id: Optional[str] = None, bypass_approval: bool = False):
        """
        Executa a ação física no mundo real (Pipedrive, Outlook, WhatsApp).
        Centralizado para auditoria e segurança.
        """
        from api.v1.endpoints.conversations import log_activity
        
        action = step.get("action")
        params = step.get("params", {})

        # 🎯 Resolução centralizada de Deal ID (Anti-alucinação)
        # Garante que qualquer ação que interaja com Pipedrive esteja atrelada ao negócio CORRETO.
        deals = context.get("pipedrive_details", {}).get("deals", [])
        valid_deal_ids = [str(d.get("id")) for d in deals]
        primary_deal = next((d for d in deals if d.get("status") == "open"), deals[0] if deals else None)
        primary_deal_id = primary_deal.get("id") if primary_deal else None
        
        param_deal_id = params.get("deal_id")
        if not param_deal_id or str(param_deal_id) not in valid_deal_ids:
            if primary_deal_id:
                params["deal_id"] = primary_deal_id
                log.debug("agent.action_auto_linked", action=action, deal_id=primary_deal_id)

        # 🛑 HARD STOP DE SEGURANÇA: Bloqueia comunicações autônomas não autorizadas
        if action in ACTIONS_REQUIRING_APPROVAL and not bypass_approval:
            msg = f"🛑 BLOQUEIO DE SEGURANÇA: Tentativa de executar '{action}' autonomamente bloqueada."
            log.info("agent.execute_approved", msg=msg)
            
            # Registra no ActivityLog para visibilidade do usuário
            try:
                await log_activity(
                    session=session,
                    org_id=org_id,
                    activity_type="security_block",
                    payload={"action": action, "params_summary": str(params)[:200]},
                    thread_id=thread_id,
                    status="blocked"
                )
            except: pass
            
            return {"status": "error", "message": "Ação de comunicação requer aprovação manual."}
        
        result = None
        
        if action == "update_pipedrive_deal":
            deal_id = params.get("deal_id")
            if not deal_id: return False
            
            update_data = {}
            # Garante que stage_id seja int se presente
            if params.get("stage_id"):
                try:
                    update_data["stage_id"] = int(params.get("stage_id"))
                except: pass
            if params.get("status"): update_data["status"] = params.get("status")
            if params.get("value"): update_data["value"] = params.get("value")
            
            result = await pipedrive_service.update_deal(deal_id, update_data)
            if result:
                await log_activity(
                    session=session,
                    org_id=org_id,
                    activity_type="stage_changed" if "stage_id" in update_data else "deal_updated",
                    payload={
                        "deal_id": deal_id,
                        "from_stage": context.get("pipedrive_details", {}).get("deals", [{}])[0].get("stage_name"),
                        "to_stage": params.get("stage_name", "Novo Estágio") if "stage_id" in update_data else None,
                        "update_data": update_data
                    },
                    thread_id=thread_id
                )
            return result

        if action == "create_pipedrive_task":
            # Pipedrive ID da organização
            target_org_id = context.get("organization", {}).get("pipedrive_id")
            target_deal_id = params.get("deal_id") # Já resolvido centralmente
            
            if not target_deal_id:
                log.warning("agent.no_deal_for_org", org_id=target_org_id)

            # Validação anti-alucinação de Person ID
            persons = context.get("pipedrive_details", {}).get("persons", [])
            valid_person_ids = [str(p.get("id")) for p in persons]
            target_person_id = params.get("person_id")
            
            if target_person_id and str(target_person_id) not in valid_person_ids:
                target_person_id = None # Remove se alucinado
            
            if not target_person_id and persons:
                # Tenta resolver o person_id com base nos contatos do contexto se disponíveis
                # Procura se há um email selecionado na UI para tentar casar
                selected_emails = [e.get("email") for e in context.get("selected_entities", []) if isinstance(e, dict) and e.get("type") == "email" and e.get("email")]
                
                if selected_emails:
                    # Tenta match por email
                    for p in persons:
                        p_emails = p.get("email", [])
                        if isinstance(p_emails, list):
                            if any(pem.get("value") in selected_emails for pem in p_emails):
                                target_person_id = p.get("id")
                                break
                
                if not target_person_id:
                    target_person_id = persons[0].get("id")
            
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
                        log.info("agent.task_duplicate_skipped", subject=subject)
                        return {"success": True, "data": {"id": act.get("id"), "is_duplicate": True}}

            # Monta payload apenas com campos não nulos
            # Pipedrive prefere 1/0 para o campo 'done'
            is_done = 1 if params.get("done") is True else 0
            
            # Normaliza tipo de atividade — Pipedrive só aceita tipos específicos
            _VALID_PD_TYPES = {"call", "meeting", "task", "deadline", "email", "lunch"}
            _PD_TYPE_MAP = {
                "follow-up": "task", "follow_up": "task", "followup": "task",
                "tarefa": "task", "lembrete": "task", "reminder": "task",
                "ligação": "call", "ligacao": "call", "phone": "call", "call_back": "call",
                "reunião": "meeting", "reuniao": "meeting", "visita": "meeting",
                "almoço": "lunch", "almoco": "lunch",
                "prazo": "deadline",
            }
            raw_type = (params.get("type") or "task").lower().strip()
            activity_type = raw_type if raw_type in _VALID_PD_TYPES else _PD_TYPE_MAP.get(raw_type, "task")

            task_data = {
                "subject": subject,
                "due_date": due_date,
                "type": activity_type,
                "done": is_done
            }
            
            # Forçar casting para int em campos de ID para evitar erros de validação da API
            try:
                if target_org_id: task_data["org_id"] = int(target_org_id)
                if target_deal_id: task_data["deal_id"] = int(target_deal_id)
                if target_person_id: task_data["person_id"] = int(target_person_id)
            except (ValueError, TypeError) as e:
                log.warning("agent.id_conversion_error", error=str(e))
                # Fallback mantém como estava se falhar, mas loga
                if target_org_id: task_data["org_id"] = target_org_id
                if target_deal_id: task_data["deal_id"] = target_deal_id
                if target_person_id: task_data["person_id"] = target_person_id

            if params.get("note"): task_data["note"] = params.get("note")

            log.debug("agent.pipedrive_task_payload", subject=task_data.get("subject"))
            pd_res = await pipedrive_service.create_activity(task_data)
            if pd_res.get("success"):
                await log_activity(
                    session=session,
                    org_id=org_id,
                    activity_type="task_created",
                    payload={
                        "task_id": pd_res.get("data", {}).get("id"),
                        "subject": subject,
                        "due_date": due_date
                    },
                    thread_id=thread_id
                )
            else:
                log.error("agent.pipedrive_task_error", pd_error=pd_res.get("error"), info=pd_res.get("error_info"))
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


        if action == "send_whatsapp":
            phone = params.get("phone", "")
            message = params.get("message", "")
            
            # --- RESOLUÇÃO INTELIGENTE DE NÚMERO (Anti-@lid) ---
            if not phone or "@lid" in str(phone) or (isinstance(phone, str) and len(phone) > 15 and not phone.isdigit()):
                log.debug("agent.wa_phone_resolve", phone=phone)
                p_id = params.get("pipedrive_person_id")
                if p_id:
                    try:
                        p_details = await pipedrive_service.get_person_details(p_id)
                        if p_details and p_details.get("phone"):
                            phone = p_details["phone"][0].get("value")
                    except: pass

            clean_num = str(phone).replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "").split("@")[0]
            if len(clean_num) <= 11 and not clean_num.startswith("55"):
                clean_num = f"55{clean_num}"
            
            try:
                async with httpx.AsyncClient(timeout=40.0) as client:
                    resp = await client.post("http://localhost:8001/api/whatsapp/send", json={"number": clean_num, "message": message})
                    if resp.status_code == 200:
                        # --- SINCRONIZAÇÃO PIPEDRIVE ---
                        deal_id = params.get("deal_id")
                        if deal_id:
                            await pipedrive_service.create_note(deal_id, f"✅ WhatsApp enviado via Assistente LINKB2B.\nPara: {params.get('contact_name', clean_num)}\nMensagem: {message[:100]}...")
                        
                        await log_activity(
                            session=session,
                            org_id=org_id,
                            activity_type="whatsapp_sent",
                            payload={
                                "to_name": params.get("contact_name", phone),
                                "to_phone": phone,
                                "message_preview": message[:200]
                            },
                            thread_id=thread_id
                        )
                        return True
                    return False
            except Exception as e:
                log.error("agent.wa_send_error", error=str(e))
                return False

        if action == "send_email":
            email_to = params.get("email", "")
            subject = params.get("subject", "Contato Comercial")
            body = params.get("body", "")
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post("http://localhost:8002/api/email/send", json={"to": email_to, "subject": subject, "body": body})
                    if resp.status_code == 200:
                        # --- SINCRONIZAÇÃO PIPEDRIVE ---
                        activity_id = params.get("activity_id")
                        deal_id = params.get("deal_id")
                        if activity_id:
                            await pipedrive_service.update_activity(activity_id, {"done": 1})
                        if deal_id:
                            await pipedrive_service.create_note(deal_id, f"✅ E-mail enviado via Assistente LINKB2B.\nPara: {email_to}\nAssunto: {subject}")

                        await log_activity(
                            session=session,
                            org_id=org_id,
                            activity_type="email_sent",
                            payload={
                                "to_name": params.get("contact_name", email_to),
                                "to_email": email_to,
                                "subject": subject,
                                "message_preview": body[:200]
                            },
                            thread_id=thread_id,
                            status="awaiting_reply"
                        )
                        return True
                    return False
            except Exception as e:
                log.error("agent.email_send_error", error=str(e))
                return False

        if action == "reply_email":
            entry_id = params.get("email_entry_id")
            body = params.get("body", "")
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post("http://localhost:8002/api/email/reply", json={"entry_id": entry_id, "body": body, "reply_all": True})
                    if resp.status_code == 200:
                        # --- SINCRONIZAÇÃO PIPEDRIVE ---
                        activity_id = params.get("activity_id")
                        deal_id = params.get("deal_id")
                        if activity_id:
                            await pipedrive_service.update_activity(activity_id, {"done": 1})
                        if deal_id:
                            await pipedrive_service.update_deal(deal_id, {"stage_id": 19}) # Contatado
                            await pipedrive_service.create_note(deal_id, f"✅ E-mail respondido via Assistente LINKB2B.\nAssunto: {params.get('subject', 'Thread')}")

                        await log_activity(
                            session=session,
                            org_id=org_id,
                            activity_type="email_reply_sent",
                            payload={
                                "to_name": params.get("contact_name", "Contato"),
                                "subject": params.get("subject", "Re: Contato"),
                                "message_preview": body[:200],
                                "is_reply": True
                            },
                            thread_id=thread_id,
                            external_ref=entry_id
                        )
                        return True
                    return False
            except Exception as e:
                log.error("agent.email_reply_error", error=str(e))
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
        org_id = pending.get("org_id")
        
        log.info("agent.approved_action_exec", action=action, action_id=action_id)

        # Chama o executor central com bypass_approval=True
        # Simula o 'step' esperado pelo _execute_real_action
        step = {"action": action, "params": params}
        
        # O contexto pode ser reconstruído parcialmente se necessário, 
        # mas as ações de comunicação usam principalmente os params.
        # Passamos um contexto vazio ou o necessário para o log_activity.
        context = {"organization": {"id": org_id}} 
        
        success = await AgentService._execute_real_action(
            step=step,
            context=context,
            intent={}, # Intent não é crítico para envio direto
            org_id=org_id,
            session=session,
            bypass_approval=True # <--- AUTORIZAÇÃO EXPLÍCITA
        )

        if success:
            return {"status": "success", "message": f"Ação '{action}' executada com sucesso."}
        else:
            return {"status": "error", "message": f"Falha ao executar '{action}'."}


    @staticmethod
    async def _beautify_email(params: dict, company_name: str, original_history: dict) -> str:
        """
        Usa o EMAIL_WRITER_PROMPT para transformar um rascunho em um e-mail profissional.
        """
        contact_name = params.get("contact_name", "Contato")
        subject = params.get("subject", "Assunto")

        # Extrai histórico destilado para o contexto do redator
        history_distilled = ""
        try:
            # Tenta pegar a destilação que já foi feita para a análise (arqueologia)
            history_distilled = await AgentService._distill_communications(
                original_history.get("email_result", {}),
                original_history.get("whatsapp_result", {})
            )
        except: pass

        try:
            # Instrução extra para evitar redundância de "Atenciosamente"
            prompt = EMAIL_WRITER_PROMPT.format(
                contact_name=contact_name,
                company_name=company_name,
                subject=subject,
                body_hint=params.get("body") or params.get("message") or "",
                history=history_distilled or "Sem histórico recente."
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
            log.warning("agent.email_beautify_error", error=str(e))
            return params.get("body") or ""

    @staticmethod
    async def _beautify_whatsapp(params: dict, company_name: str, original_history: dict) -> str:
        """
        Usa o WHATSAPP_WRITER_PROMPT para transformar um rascunho em mensagem WhatsApp profissional.
        """
        contact_name = params.get("contact_name", "Contato")
        body_hint = params.get("message") or params.get("body") or ""
        
        # Extrai histórico destilado para o contexto do redator
        history_distilled = ""
        try:
            # Tenta pegar a destilação que já foi feita para a análise (arqueologia)
            history_distilled = await AgentService._distill_communications(
                original_history.get("email_result", {}),
                original_history.get("whatsapp_result", {})
            )
        except: pass

        try:
            prompt = WHATSAPP_WRITER_PROMPT.format(
                contact_name=contact_name,
                company_name=company_name,
                body_hint=body_hint,
                history=history_distilled or "Sem histórico recente."
            )
            refined = await ask_gemini(prompt)
            if refined and isinstance(refined, str):
                if "Desculpe, ocorreu um erro de cota" in refined:
                    return body_hint
                # Remove placeholders residuais
                refined = refined.replace("{contact_name}", contact_name)
                refined = refined.replace("{company_name}", company_name)
                return refined.strip().strip('"')
            return body_hint
        except Exception as e:
            log.warning("agent.wa_beautify_error", error=str(e))
            return body_hint

    @staticmethod
    async def reject_action(action_id: str) -> dict:
        """Remove uma ação pendente (rejeitada pelo usuário)."""
        pending = AgentService._pending_actions.pop(action_id, None)
        if pending:
            return {"status": "rejected", "description": pending.get("description")}
        return {"status": "not_found"}
