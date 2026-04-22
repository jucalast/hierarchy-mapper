import asyncio
import json
import uuid
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from services.external.base_gemini_service import ask_gemini
from services.pipedrive.pipedrive_service import pipedrive_service
from services.ai.data_fetcher import fetch_contextual_data

# Ações que REQUEREM aprovação do usuário antes de executar
ACTIONS_REQUIRING_APPROVAL = {"send_whatsapp", "send_email"}


class AgentService:
    """
    Serviço de Agente Autônomo de Vendas B2B.
    Pipeline de 5 estágios: Diagnóstico → Resolução de Contatos → Plano → Aprovação → Execução.
    """

    # Armazena ações pendentes de aprovação (in-memory, por sessão)
    _pending_actions: Dict[str, dict] = {}

    @staticmethod
    async def run_workflow(goal: str, initial_intent: dict, org_id: int, selected_entities: List[dict], session, log_queue: Optional[asyncio.Queue] = None):
        """
        Executa o workflow completo do agente autônomo.
        """
        def log(msg):
            print(f"[Agent] {msg}")
            if log_queue:
                log_queue.put_nowait(msg)

        # Converte entidades Pydantic para dict se necessário para evitar AttributeError
        selected_entities = [e.model_dump() if hasattr(e, "model_dump") else e for e in selected_entities]

        log(f"Iniciando workflow especializado: {goal}")
        
        # ═══════════════════════════════════════
        # ESTÁGIO 1: Coleta de Contexto Total
        # ═══════════════════════════════════════
        context_intent = initial_intent.copy()
        context_intent["activity_done_filter"] = None
        context_intent["activity_date_filter"] = "all"
        if "data_scope" not in context_intent: context_intent["data_scope"] = []
        for scope in ["persons", "notes", "activities", "deals", "whatsapp", "emails"]:
            if scope not in context_intent["data_scope"]:
                context_intent["data_scope"].append(scope)
        
        log("Coletando histórico completo (Contatos, Atividades, Notas, Negócios e Mensagens)...")
        raw_context = await fetch_contextual_data(context_intent, org_id, goal, session, selected_entities=selected_entities)
        
        # ═══════════════════════════════════════
        # ESTÁGIO 2: Resolução de Contatos (Mapa de Alcance)
        # ═══════════════════════════════════════
        log("Identificando contatos e canais disponíveis...")
        contact_map = await AgentService._resolve_contact_map(raw_context, org_id, session)
        
        # Marcar entidades selecionadas no mapa
        selected_names = [e.get("name") for e in selected_entities]
        for name, info in contact_map.items():
            if name in selected_names:
                info["is_priority"] = True
                log(f"📍 Contato PRIORITÁRIO identificado: {name}")
        
        if contact_map:
            contacts_summary = ", ".join([f"{c['name']} ({', '.join(c['channels'])})" for c in contact_map.values()])
            log(f"Contatos mapeados: {contacts_summary}")
        else:
            log("AVISO: Nenhum contato com dados de comunicação identificado. O agente poderá sugerir ações de prospecção/coleta.")
        
        # ═══════════════════════════════════════
        # ESTÁGIO 3: Análise de Cenário (Senior Sales Analysis)
        # ═══════════════════════════════════════
        log("Analisando maturidade do negócio com base no histórico...")
        deal_analysis = await AgentService._analyze_deal_state(raw_context)
        
        # ═══════════════════════════════════════
        # ESTÁGIO 4: Plano de Ação Estratégico
        # ═══════════════════════════════════════
        log("Gerando plano de ação multicanal...")
        plan_raw = await AgentService._create_logical_plan(goal, deal_analysis, raw_context, contact_map, selected_entities)
        
        # Normaliza
        if isinstance(plan_raw, dict) and "plan" in plan_raw:
            plan = plan_raw["plan"]
        elif isinstance(plan_raw, list):
            plan = plan_raw
        else:
            plan = []

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
            
            # ── Ação que REQUER aprovação ──
            if action in ACTIONS_REQUIRING_APPROVAL:
                action_id = str(uuid.uuid4())[:8]
                pending_action = {
                    "action_id": action_id,
                    "action": action,
                    "description": desc,
                    "params": params,
                    "contact_map": contact_map,
                    "org_id": org_id,
                    "context": raw_context,
                    "intent": initial_intent
                }
                AgentService._pending_actions[action_id] = pending_action
                
                # Monta preview para o frontend
                channel = "WhatsApp" if action == "send_whatsapp" else "Email"
                contact_name = params.get("contact_name", "Contato")
                message_preview = params.get("message") or params.get("body") or params.get("note") or ""
                
                pending_approvals.append({
                    "action_id": action_id,
                    "action_type": action,
                    "channel": channel,
                    "contact_name": contact_name,
                    "contact_phone": params.get("phone"),
                    "contact_email": params.get("email"),
                    "subject": params.get("subject"),
                    "message_preview": message_preview,
                    "description": desc
                })
                log(f"⏳ Aguardando aprovação: {channel} para {contact_name}")
                
            # ── Ação que NÃO requer aprovação ──
            else:
                log(f"Executando: {desc}")
                result = await AgentService._execute_real_action(step, raw_context, initial_intent, org_id)
                
                if action == "create_pipedrive_task" and result:
                    log(f"✅ Atividade criada no Pipedrive (ID: {result})")
                    created_tasks.append({
                        "id": result,
                        "subject": params.get("subject"),
                        "note": params.get("note"),
                        "due_date": (datetime.now() + timedelta(days=params.get("days_delay", 0))).strftime("%Y-%m-%d"),
                        "type": params.get("type", "task"),
                        "done": False
                    })
                elif action == "update_pipedrive_task" and result:
                    log(f"✅ Atividade atualizada no Pipedrive")

                execution_results.append({
                    "description": desc,
                    "action": action,
                    "status": "success" if result else "failed",
                    "details": result
                })
            
        # ═══════════════════════════════════════
        # ESTÁGIO 6: Briefing Final
        # ═══════════════════════════════════════
        final_summary = await AgentService._generate_final_briefing(goal, execution_results, pending_approvals)
        
        # Estruturamos a resposta
        analysis_part = deal_analysis
        if "[[TASK:" not in analysis_part:
            analysis_part += "\n\n[[PAST_TASKS]]"
            
        summary_part = final_summary
        if "[[NEW_TASK:" not in summary_part:
            summary_part += "\n\n[[NEW_TASKS]]"

        full_response_parts = [
            analysis_part,
            "### Próximo Passo Definido",
            summary_part
        ]
        
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
            persons = [p for p in persons if any(p.get("name", "").lower() == e.get("name", "").lower() for e in explicit_selected)]
            
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
                    
                    contact_map[name] = {
                        "name": name,
                        "pipedrive_person_id": p.get("id"),
                        "phone": phone,
                        "email": email,
                        "whatsapp_available": wa_available,
                        "email_available": bool(email),
                        "channels": channels,
                        "source": "Pipedrive"
                    }
            
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
                    stmt = select(Employee).where(Employee.company_id == org_id)
                    res = await session.execute(stmt)
                    local_employees = res.scalars().all()
                    for emp in local_employees:
                        if emp.name not in contact_map:
                            contact_map[emp.name] = {
                                "name": emp.name,
                                "phone": emp.whatsapp_number or emp.phone,
                                "email": emp.email,
                                "whatsapp_available": bool(emp.whatsapp_number),
                                "email_available": bool(emp.email),
                                "channels": [c for c in ["WhatsApp", "Email", "Telefone"] if (emp.whatsapp_number if c=="WhatsApp" else (emp.email if c=="Email" else emp.phone))],
                                "source": f"Inteligência Local ({emp.department or 'Sem Dept'})",
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
                                    "source": "WhatsApp (Não vinculado no Pipedrive)"
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
        
        history_summary = "DADOS DO NEGÓCIO (PIPELINE):\n"
        for d in deals[:3]:
            history_summary += f"- Negócio: {d.get('title')} | Valor: {d.get('formatted_value')} | Estágio: {d.get('stage_name')} | Status: {d.get('status')}\n"
        
        history_summary += "\nHistórico de Atividades (INDEXADO):\n"
        for i, act in enumerate(activities[:15]):
            status = "CONCLUÍDA" if act.get("done") else "PENDENTE"
            history_summary += f"[{i+1}] {act.get('due_date')}: [{act.get('type')}] {act.get('subject')} ({status})\n"
            note_content = act.get("note")
            if note_content:
                history_summary += f"    Nota: {note_content[:200]}\n"
        
        history_summary += "\nNotas Adicionais:\n"
        for n in notes[:5]:
            history_summary += f"- {n.get('content', '')[:200]}\n"

        # Inclui snapshot de comunicações se disponível
        wa_result = context.get("whatsapp_result", {})
        wa_messages = wa_result.get("resultado", {}).get("messages_by_contact", [])
        if wa_messages:
            history_summary += "\nÚltimas Mensagens de WhatsApp:\n"
            for group in wa_messages[:2]:
                history_summary += f"\nConversa com {group.get('contact')}:\n"
                for m in group.get("messages", [])[:8]:
                    sender = "Eu" if m.get("fromMe") else "Contato"
                    history_summary += f"  {sender}: {m.get('body', '')[:150]}\n"

        # Inclui snapshot de Emails com Filtro de Humanidade
        email_result = context.get("email_result", {})
        email_messages_groups = email_result.get("resultado", {}).get("messages_by_contact", [])
        if email_messages_groups:
            history_summary += "\nMonitoramento de Emails (Análise de Humanidade):\n"
            for group in email_messages_groups[:3]:
                history_summary += f"\nCanal Email: {group.get('contact')} ({group.get('email')})\n"
                human_msgs = group.get("human_threads", [])
                # Garante ordem cronológica (mais antigo primeiro para o fluxo de leitura)
                try:
                    human_msgs.sort(key=lambda x: x.get("date", ""))
                except: pass
                
                auto_count = group.get("automated_count", 0)
                
                if human_msgs:
                    history_summary += f"  - E-mails Humanos Detectados ({len(human_msgs)}):\n"
                    for m in human_msgs[:8]:
                        # Identifica se o remetente sou EU
                        raw_sender = m.get("sender", "")
                        is_me_sender = "/o=ExchangeLabs" in raw_sender or "joao.moura" in raw_sender.lower()
                        lbl_from = "EU (João Luccas)" if is_me_sender else "CLIENTE"
                        
                        # Identifica se o destinatário sou EU
                        raw_to = m.get("to", "")
                        is_me_to = "joao.moura" in raw_to.lower() or "Joao" in raw_to or "João" in raw_to
                        lbl_to = "EU (João Luccas)" if is_me_to else "CLIENTE"
                        
                        history_summary += f"    [{m.get('date')}] DE: {lbl_from} > PARA: {lbl_to} | {m.get('subject')} -> {m.get('body', '')[:600]}\n"
                else:
                    history_summary += "  - Nenhuma comunicação humana direta encontrada recentemente.\n"
                
                if auto_count > 0:
                    history_summary += f"  - ⚠️ INFO: {auto_count} e-mails de automação (marketing/notificações) foram identificados e descartados da análise técnica, mas servem como prova de monitoramento.\n"

        # Injeção de Status Calculado (Cross-channel)
        calc_status = context.get("calculated_status", {})
        if calc_status:
            history_summary += f"\n📊 ANÁLISE DE TEMPO REAL (Métrica LINKB2B):\n"
            history_summary += f"- {calc_status.get('summary')}\n"
            if calc_status.get('is_critical'):
                history_summary += f"- ⚠️ RISCO: O momentum está baixando (Silêncio > 10 dias).\n"
        else:
            # Fallback antigo se por algum motivo não calculou
            all_dates = []
            for act in activities:
                if act.get("done") and act.get("due_date"):
                    try: all_dates.append(datetime.strptime(act.get("due_date"), "%Y-%m-%d"))
                    except: pass
            if all_dates:
                last_human_date = max(all_dates)
                delta = (datetime.now() - last_human_date).days
                history_summary += f"\n⏳ ALERTA DE CICLO (Pipedrive-only): Último registro há {delta} dias.\n"

        # NOVIDADE: Passo Intermediário de Arqueologia (Mapa de Resoluções)
        # Analisamos as comunicações separadamente para extrair fatos antes da análise de vendas
        resolution_map_prompt = f"""Analise este histórico de comunicações e identifique:
1. O que o CLIENTE pediu/perguntou?
2. O João (eu) já respondeu ou entregou o que foi pedido? Se sim, em qual data?
3. Há alguma pendência REAL que ainda não foi respondida nas comunicações?

HISTÓRICO:
{history_summary}

Responda em formato de resumo rápido: "Resolução: [Fato] -> [Resolvido/Pendente em Data]"
"""
        resolution_map = await ask_gemini(resolution_map_prompt)

        prompt = f"""Você é um Diretor de Vendas B2B Senior seguindo este PROTOCOLO DE NEGÓCIO:
{protocol}

Sua missão é extrair o ESTADO REAL do negócio cruzando o CRM com o histórico de comunicações.

DIRETRIZES DE PENSAMENTO:
1. FOCO DUPLO (ARQUEOLOGIA + PAUTA):
   - MODO ARQUEOLOGIA: Se algo foi resolvido nas conversas mas não está no CRM, relate como CONCLUÍDO na DATA REAL.
   - MODO PAUTA (SCRIPTAGEM): Se houver tarefas 'PENDENTES' no CRM, identifique-as como o objetivo principal da próxima ação. Determine o que deve ser dito ou enviado para resolver essa pauta específica.
2. MAPA DE RESOLUÇÃO (FATOS DESTILADOS): Analise "{resolution_map}" para confirmar o fluxo de entregas.
3. GATILHOS DE NEGÓCIO: Identifique quem detém a próxima ação (João ou Cliente) e se há dependências (Ex: "Aguardando X para poder fazer Y").

HISTÓRICO COMPLETO:
{history_summary}
"""
        return await ask_gemini(prompt)

    # ═══════════════════════════════════════
    # PLANO DE AÇÃO ESTRATÉGICO
    # ═══════════════════════════════════════
    @staticmethod
    async def _create_logical_plan(goal: str, analysis: str, context: dict, contact_map: dict, selected_entities: List[dict]):
        """Passo 4: Define as ações concretas com inteligência multicanal."""
        pd_details = context.get("pipedrive_details", {})
        deals = pd_details.get("deals", [])
        deals_info = "\n".join([f"- ID: {d.get('id')} | Título: {d.get('title')} | Valor: {d.get('formatted_value')} | Estágio: {d.get('stage_name')} | Status: {d.get('status')}" for d in deals])

        # Formata atividades JÁ EXISTENTES para evitar duplicidade
        activities = pd_details.get("activities", [])
        activities_info = "ATIVIDADES JÁ REGISTRADAS NO CRM (Não duplique estas):\n"
        for act in activities[:15]:
            status = "CONCLUÍDA" if act.get("done") else "PENDENTE"
            activities_info += f"- [{status}] {act.get('subject')} ({act.get('due_date')})\n"
        if not activities: activities_info += "- Nenhuma atividade registrada ainda.\n"

        # Formata mapa de contatos para a IA
        contacts_info = ""
        if contact_map:
            contacts_info = "CONTATOS DISPONÍVEIS E CANAIS:\n"
            for name, info in contact_map.items():
                channels_str = ", ".join(info["channels"]) if info["channels"] else "NENHUM CANAL"
                contacts_info += f"- {name}: {channels_str}"
                if info.get("phone"): contacts_info += f" | Tel: {info['phone']}"
                if info.get("email"): contacts_info += f" | Email: {info['email']}"
                contacts_info += "\n"
        else:
            contacts_info = "CONTATOS: Nenhum contato com dados de comunicação encontrado no CRM.\n"

        protocol = AgentService._get_business_protocol()

        prompt = f"""Você é um Gerente de Vendas Senior. Seu papel é gerar um PLANO DE AÇÃO PRECISO baseado no PROTOCOLO abaixo:
{protocol}

DATA ATUAL: {datetime.now().strftime("%d/%m/%Y")} (Assuma o ano {datetime.now().year} se a data extraída da conversa não tiver ano).

ANÁLISE DE VENDAS:
"{analysis}"

OBJETIVO: "{goal}"

NEGÓCIOS (DEALS):
{deals_info or "Nenhum negócio encontrado."}
- Entidades Marcadas pelo Usuário (FOCO EXCLUSIVO): Você DEVE priorizar a criação de tarefas e o engajamento com estas pessoas especificamente: {", ".join([e.get('name', '') for e in selected_entities]) or "Nenhuma"}. NÃO direcione suas tarefas para pessoas que não foram marcadas pelo usuário a menos que elas sejam o único contato viável.

{contacts_info}
{activities_info}

AÇÕES DISPONÍVEIS:
1. "create_pipedrive_task" - Criar atividade no CRM (executa imediatamente, sem permissão)
   Params: {{ "subject", "note", "type" (call/email/task/meeting), "deal_id", "due_date" (YYYY-MM-DD), "done" (boolean) }}
   IMPORTANTE: Se você encontrar um WhatsApp anterior (ex: 'enviei o orçamento dia 15/04'), use a data exata em "due_date" e marque "done": true.

2. "update_pipedrive_task" - Atualizar atividade existente no CRM (executa imediatamente)
   Params: {{ "activity_id", "subject", "note" }}

3. "send_whatsapp" - Enviar mensagem WhatsApp ao contato (REQUER APROVAÇÃO do usuário)
   Params: {{ "contact_name", "phone", "message" }}
   ⚠️ Use SOMENTE se houver WhatsApp disponível no mapa de contatos.

4. "send_email" - Enviar email ao contato (REQUER APROVAÇÃO do usuário)
   Params: {{ "contact_name", "email", "subject", "body" }}
   ⚠️ Use SOMENTE se houver Email disponível no mapa de contatos.

5. "update_pipedrive_person" - Atualizar dados de um contato (ex: telefone/whatsapp novo)
   Params: {{ "person_id", "phone", "email", "name" }}
   IMPORTANTE: Se você encontrar um WhatsApp por nome que NÃO bate com o número no CRM, use esta ação para sincronizar o Pipedrive.

6. "sync_contact_to_pipedrive" - Criar/Vincular um contato local ao Pipedrive (executa imediatamente). 
   Params: {{ "person_name", "email", "phone", "org_id", "deal_id" }}
   ⚠️ USE ISSO sempre que um contato importante (ex: decisor mencionado ou identificado no Outlook) NÃO estiver no Pipedrive (identificado como 'Inteligência Local' no mapa).

7. "generate_content" - Gerar texto de apoio ou um insight consultivo (sem ação externa). Use para informar ao usuário se algo está faltando.
   Params: {{ "content" }}

DIRETRIZES DE CONSULTORIA SENIOR:
- ⚠️ PRIORIDADE DE PAUTA: Se uma atividade similar já existe em "ATIVIDADES JÁ REGISTRADAS" como 'PENDENTE', NÃO crie uma nova `create_pipedrive_task`. Em vez disso, proponha a AÇÃO (WhatsApp/Email) para resolvê-la.
- ⚠️ PROTOCOLO DE ARQUEOLOGIA: Se encontrou evento concluído no passado SEM registro no CRM, crie com `done: true` na data original.
- ⚠️ PROTOCOLO DE 'GANCHOS TÉCNICOS': Ao sugerir mensagens, você é OBRIGADO a resgatar termos técnicos, dores ou métricas do histórico (Ex: cubagem, amostragem, logística).
- ⚠️ RIGOR DE EVIDÊNCIA: Proibido criar ações ou tarefas sem evidência textual explícita. Sem placeholders.
- Peça permissão para TUDO que for enviado ao cliente (WhatsApp/Email).

FORMATO DE RESPOSTA (JSON APENAS):
{{
  "plan": [
    {{ "action": "create_pipedrive_task", "description": "Razão", "params": {{ ... }} }},
    {{ "action": "send_whatsapp", "description": "Razão", "params": {{ "contact_name": "Bianca Lima", "phone": "5511...", "message": "Oi Bianca, conforme nossa conversa sobre cubagem no dia X..." }} }}
  ]
}}
"""
        return await ask_gemini(prompt, json_mode=True)

    # ═══════════════════════════════════════
    # EXECUTOR DE AÇÕES
    # ═══════════════════════════════════════
    @staticmethod
    async def _execute_real_action(step: dict, context: dict, intent: dict, org_id: int):
        """Executa ações que NÃO requerem aprovação."""
        action = step.get("action")
        params = step.get("params", {})
        
        if action == "create_pipedrive_task":
            target_org_id = context.get("organization", {}).get("pipedrive_id") or org_id
            
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
                selected_emails = [e.get("email") for e in context.get("selected_entities", []) if e.get("type") == "email" and e.get("email")]
                
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
            
            task_data = {
                "org_id": target_org_id,
                "deal_id": target_deal_id,
                "person_id": target_person_id,
                "subject": params.get("subject"),
                "note": params.get("note"),
                "due_date": due_date,
                "type": params.get("type", "task"),
                "done": params.get("done", True) # Default to True for archaeology
            }
            return await pipedrive_service.create_activity(task_data)

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
            target_org_id = params.get("org_id") or context.get("organization", {}).get("pipedrive_id") or org_id
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

        elif action == "generate_content":
            return params.get("note") or params.get("content")

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
                        print(f"[Agent] ✅ WhatsApp enviado para {params.get('contact_name')} ({clean_num})")
                        return {
                            "status": "success",
                            "channel": "WhatsApp",
                            "contact_name": params.get("contact_name"),
                            "message": message
                        }
                    else:
                        return {"status": "error", "message": f"Erro ao enviar WhatsApp: {resp.status_code}"}
            
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
                        print(f"[Agent] ✅ Email enviado para {params.get('contact_name')} ({email_to})")
                        return {
                            "status": "success",
                            "channel": "Email",
                            "contact_name": params.get("contact_name"),
                            "subject": subject
                        }
                    else:
                        return {"status": "error", "message": f"Erro ao enviar Email: {resp.status_code}"}
            
            return {"status": "error", "message": f"Ação '{action}' não reconhecida."}
        
        except Exception as e:
            print(f"[Agent] ❌ Erro ao executar ação aprovada: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def reject_action(action_id: str) -> dict:
        """Remove uma ação pendente (rejeitada pelo usuário)."""
        pending = AgentService._pending_actions.pop(action_id, None)
        if pending:
            print(f"[Agent] ❌ Ação rejeitada pelo usuário: {pending.get('description')}")
            return {"status": "rejected", "description": pending.get("description")}
        return {"status": "not_found"}

    # ═══════════════════════════════════════
    # BRIEFING FINAL
    # ═══════════════════════════════════════
    @staticmethod
    async def _generate_final_briefing(goal: str, results: list, pending_approvals: list):
        """Resumo executivo para o chat."""
        successful_tasks = [r for r in results if r.get("status") == "success" and r.get("action") == "create_pipedrive_task"]
        
        pending_desc = ""
        if pending_approvals:
            pending_desc = f"\n\nAÇÕES AGUARDANDO SUA APROVAÇÃO ({len(pending_approvals)}):\n"
            for pa in pending_approvals:
                pending_desc += f"- {pa['channel']} para {pa['contact_name']}: {pa['description']}\n"
        
        prompt = f"""Você é o Diretor de Vendas. O plano "{goal}" foi processado.
Sua missão é explicar o que foi feito de forma direta e profissional.

DADOS DA EXECUÇÃO:
- Tarefas criadas no CRM: {len(successful_tasks)}
- Ações aguardando aprovação do usuário: {len(pending_approvals)}
{pending_desc}

REGRAS DE FORMATAÇÃO:
1. Use `[[NEW_TASK:1]]`, `[[NEW_TASK:2]]`, etc. para inserir os CARDS das novas tarefas.
2. Se há ações pendentes de aprovação, mencione que elas precisam da confirmação do usuário para serem executadas.
3. NÃO diga que "ações falharam" ou cite termos técnicos como JSON, ID ou 'params'.
4. Seja direto e mostre valor. Máximo 3 parágrafos.
"""
        return await ask_gemini(prompt)
