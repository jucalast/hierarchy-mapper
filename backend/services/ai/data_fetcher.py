"""
Orquestração de busca de dados contextuais.
Resolve organização, busca dados do Pipedrive, ContextService e OSINT.
"""
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func


async def resolve_organization(
    payload_org_id: Optional[Any],
    selected_companies: list,
    extracted_name: Optional[str],
    message: str,
    session: AsyncSession
) -> Optional[int]:
    """
    Resolve o org_id a partir das fontes disponíveis:
    1. selectedCompanies da UI
    2. Nome extraído pela IA
    3. Regex fallback
    """
    from services.context_service import ContextService
    
    org_id = payload_org_id
    
    # Se temos uma empresa explícita na UI, usamos ela
    if selected_companies and len(selected_companies) > 0:
        org_id = selected_companies[0].id
        print(f"[AI Chat] Usando empresa da UI: {selected_companies[0].name} (ID: {org_id})")
    # Se não temos orgId das props UI, mas a IA extraiu do texto e não havia orgId
    elif not org_id and extracted_name:
        print(f"[AI Chat] Buscando empresa inferida pela IA: {extracted_name}")
        org_data_resolved = await ContextService.fetch_organization_by_name(session, extracted_name)
        if org_data_resolved:
            org_id = org_data_resolved.id
            
    # Se ainda não temos org_id, tentamos último recurso (Regex antigo)
    if not org_id:
        org_name_regex = await ContextService.extract_organization_name(message)
        if org_name_regex:
            org_data_regex = await ContextService.fetch_organization_by_name(session, org_name_regex)
            if org_data_regex:
                org_id = org_data_regex.id

    return org_id


async def execute_osint_enrichment(
    intent_info: dict,
    org_id: Optional[int],
    session: AsyncSession
) -> Optional[Dict[str, Any]]:
    """
    Executa enriquecimento OSINT para um lead específico.
    Retorna o contexto OSINT para injeção no pipeline.
    """
    from services.context_service import ContextService
    from services.external.osint_service import osint_service
    from sqlalchemy import select
    from models.employee import Employee
    
    target_person = intent_info.get("extracted_person_name")
    target_company = intent_info.get("extracted_company_name")
    
    # Se não extraiu a empresa, mas temos um org_id resolvido, tentamos pegar o nome real
    if not target_company and org_id:
        org_data_overview = await ContextService.fetch_organization_overview(session, org_id)
        target_company = org_data_overview.get("organization", {}).get("name")
    
    if target_person and target_company:
        # Tenta pegar o domínio e CNPJ oficiais da empresa se estiver no banco
        target_domain = None
        target_cnpj = None
        if org_id:
            org_data_overview = await ContextService.fetch_organization_overview(session, org_id)
            org_obj = org_data_overview.get("organization", {})
            target_domain = org_obj.get("domain")
            target_cnpj = org_obj.get("cnpj")
        
        print(f"[AI Chat] Executando Enriquecimento OSINT para {target_person} na {target_company} (Domain: {target_domain}, CNPJ: {target_cnpj})...")
        osint_data = await osint_service.enrich_lead(target_person, target_company, domain=target_domain, cnpj=target_cnpj)
        if osint_data and "error" not in osint_data:
            osint_context = {
                "osint_result": osint_data,
                "status": "success"
            }
            print(f"[AI Chat] ✅ Enriquecimento concluído: {osint_data.get('whatsapp', {}).get('numero')}")
            
            # Salva os dados enriquecidos localmente para consultas futuras
            try:
                emp_q = select(Employee).where(
                    Employee.company_id == org_id,
                    func.lower(Employee.name).like(f"%{target_person.lower()}%")
                )
                emp_res = await session.execute(emp_q)
                emp = emp_res.scalars().first()
                if emp:
                    # Atualiza email se não existir ou se OSINT for melhor
                    if osint_data.get("emailProvavel"):
                        emp.email = osint_data.get("emailProvavel")
                    
                    # Atualiza telefones
                    wp = osint_data.get("whatsapp", {}).get("numero")
                    if wp: emp.whatsapp_number = wp
                    
                    pabx = osint_data.get("pabx")
                    if pabx: emp.phone = pabx
                    
                    session.add(emp)
                    await session.commit()
                    print(f"[AI Chat] 💾 Contato {emp.name} atualizado no banco local com OSINT.")
            except Exception as e:
                print(f"[AI Chat] ⚠️ Aviso: Não foi possível salvar OSINT no banco local: {e}")
                
            return osint_context
        else:
            return {"error": osint_data.get("error", "Falha na pesquisa externa.")}
    else:
        return {"error": "Não consegui identificar o nome da pessoa ou da empresa para pesquisar."}


async def fetch_contextual_data(
    intent_info: dict,
    org_id: Optional[int],
    message: str,
    session: AsyncSession
) -> Dict[str, Any]:
    """
    Busca dados contextuais com base nos escopos definidos pelo classificador de intenção.
    Retorna o internal_context preenchido.
    """
    from services.context_service import ContextService
    from datetime import date, timedelta
    
    internal_context = {}
    query_type = intent_info.get("query_type", "general")
    data_scope = intent_info.get("data_scope", [])
    
    # Fallback: se data_scope veio vazio, inferimos pelo query_type para retrocompatibilidade
    if not data_scope:
        scope_defaults = {
            "contacts": ["employees", "decision_makers", "persons"],
            "pipedrive_info": ["deals", "activities", "notes", "persons"],
            "pipedrive_tasks": ["today_tasks"],
            "company_info": [],
            "general": [],
            "whatsapp": []
        }
        data_scope = scope_defaults.get(query_type, [])
    
    print(f"[AI Pipeline] Escopos de dados selecionados: {data_scope}")

    # --- BUSCA DE DADOS DA EMPRESA (Se identificada) ---
    pipedrive_org_id = None
    org_data = None
    basic_context = {}
    
    if org_id:
        try:
            basic_context = await ContextService.fetch_organization_overview(session, org_id)
            org_data = basic_context.get("organization", {})
            if org_data:
                internal_context["organization"] = {
                    "name": org_data.get("name"),
                    "cnpj": org_data.get("cnpj"),
                    "domain": org_data.get("domain"),
                    "pipedrive_id": org_data.get("pipedrive_id")
                }
                pipedrive_org_id = org_data.get("pipedrive_id")
        except Exception as e:
            print(f"[AI Chat] Erro ao buscar overview da empresa: {e}")

    # --- BUSCA DE TAREFAS (Com filtro inteligente de empresa se houver) ---
    if "today_tasks" in data_scope or ("activities" in data_scope and query_type == "pipedrive_tasks"):
        await _fetch_tasks(intent_info, internal_context, pipedrive_org_id, message)

    # --- BUSCA DE DADOS CONTEXTUAIS ADICIONAIS ---
    if org_id:
        try:
            # Se qualquer escopo envolve info completa da org (contacts/company_info)
            if any(s in data_scope for s in ["employees", "decision_makers"]):
                if org_data:
                    internal_context["organization"] = org_data
            
            # ============================
            # FETCH GRANULAR POR ESCOPO
            # ============================
            
            # Escopo: decision_makers (tomadores de decisão do banco interno)
            if "decision_makers" in data_scope:
                print(f"[AI Pipeline] 📋 Buscando decision_makers...")
                try:
                    decision_makers_context = await ContextService.fetch_decision_makers(session, org_id)
                    internal_context.update(decision_makers_context)
                except Exception as e:
                    print(f"[AI Chat] Erro ao buscar decision makers: {e}")
            
            # Escopo: employees (funcionários mapeados do banco interno)
            if "employees" in data_scope:
                print(f"[AI Pipeline] 👥 Buscando employees...")
                try:
                    employees_context = await ContextService.fetch_employees_by_department(session, org_id)
                    internal_context['employees_by_dept'] = employees_context
                except Exception as e:
                    print(f"[AI Chat] Erro ao buscar employees: {e}")
            
            # Escopos do Pipedrive: persons, deals, activities, notes
            pipedrive_scopes = [s for s in data_scope if s in ("persons", "deals", "activities", "notes")]
            if pipedrive_scopes and org_data and org_data.get("pipedrive_id"):
                print(f"[AI Pipeline] 🔗 Buscando Pipedrive [{', '.join(pipedrive_scopes)}]...")
                try:
                    from services.pipedrive.pipedrive_service import pipedrive_service
                    # Passa o filtro de 'concluídas' se a IA detectou que o usuário as quer
                    done_filter = intent_info.get("activity_done_filter")
                    pd_details = await pipedrive_service.get_organization_details(org_data["pipedrive_id"], done=done_filter)
                    
                    if pd_details and "error" not in pd_details:
                        # Filtra para injetar SOMENTE os escopos solicitados
                        filtered_pd = {}
                        if "persons" in pipedrive_scopes:
                            persons = pd_details.get("persons", [])
                            if persons: filtered_pd["persons"] = persons
                        if "deals" in pipedrive_scopes:
                            deals = pd_details.get("deals", [])
                            filtered_pd["deals"] = deals  # inclui mesmo vazio pra informar "nenhum deal"
                        if "activities" in pipedrive_scopes:
                            activities = pd_details.get("activities", [])
                            filtered_pd["activities"] = activities
                        if "notes" in pipedrive_scopes:
                            notes = pd_details.get("notes", [])
                            if notes: filtered_pd["notes"] = notes
                        
                        if filtered_pd:
                            print(f"[AI Pipeline] ✅ Pipedrive: Coletados {len(filtered_pd.get('activities', []))} atividades, {len(filtered_pd.get('deals', []))} negócios e {len(filtered_pd.get('persons', []))} contatos.")
                            internal_context["pipedrive_details"] = filtered_pd
                            # Se for busca de tarefas, garante que fiquem no top-level para o TaskList bypass
                            if "activities" in filtered_pd and query_type == "pipedrive_tasks":
                                internal_context["activities"] = filtered_pd["activities"]
                    else:
                        internal_context["pipedrive_details"] = pd_details or {"error": "Sem dados"}
                except Exception as e:
                    print(f"[AI Chat] Erro ao buscar dados do Pipedrive: {e}")
                    internal_context["pipedrive_details"] = {"error": str(e)}
            elif pipedrive_scopes and org_data and not org_data.get("pipedrive_id"):
                print(f"[AI Chat] Organização não possui pipedrive_id vinculado!")
                internal_context["pipedrive_details"] = {"error": "Pipedrive ID não vinculado"}
            
            # Estatísticas (sempre que houver dados de pessoas)
            if any(s in data_scope for s in ["employees", "decision_makers"]):
                internal_context['statistics'] = basic_context.get('statistics', {})

            # ============================
            # SCOPE: Communications (WhatsApp & Email)
            # ============================
            # Se temos os contatos do Pipedrive, podemos buscar o histórico de conversas real
            if any(s in data_scope for s in ["whatsapp", "emails"]):
                p_details = internal_context.get("pipedrive_details", {})
                persons = p_details.get("persons", []) if isinstance(p_details, dict) else []
                
                if persons:
                    print(f"[AI Pipeline] 💬 Identificados {len(persons)} contatos para busca de comunicações.")
                    from services.ai.action_executor import _execute_get_messages, execute_email_action
                    import httpx
                    
                    wa_base = "http://localhost:8001/api/whatsapp"
                    email_base = "http://localhost:8002/api/email"
                    
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        # WhatsApp
                        if "whatsapp" in data_scope:
                            wa_history = []
                            for p in persons[:3]:
                                phone_list = p.get("phone", [])
                                phone = None
                                if isinstance(phone_list, list) and len(phone_list) > 0:
                                    phone = phone_list[0].get("value")
                                
                                if phone:
                                    print(f"[AI Pipeline]   - Buscando WhatsApp para {p.get('name')} ({phone})...")
                                    res = await _execute_get_messages(client, wa_base, {"whatsapp_number": phone}, None, None)
                                    if res and "resultado" in res:
                                        msgs = res["resultado"].get("messages", [])
                                        if msgs:
                                            print(f"[AI Pipeline]     ✅ Encontradas {len(msgs)} mensagens.")
                                            wa_history.append({"contact": p.get("name"), "messages": msgs})
                            if wa_history:
                                internal_context["whatsapp_result"] = {"resultado": {"messages_by_contact": wa_history}}

                        # Emails
                        if "emails" in data_scope:
                            email_history = []
                            for p in persons[:3]:
                                email_list = p.get("email", [])
                                email = None
                                if isinstance(email_list, list) and len(email_list) > 0:
                                    email = email_list[0].get("value")

                                if email:
                                    print(f"[AI Pipeline]   - Buscando Emails para {p.get('name')} ({email})...")
                                    # Busca e-mails específicos para este contato (Inbox)
                                    # O endpoint get_messages do communication.py é genérico, mas aqui usamos o do proxy de email-service
                                    try:
                                        e_res = await client.get(f"{email_base}/messages?folder=Inbox&limit=5&q={email}")
                                        if e_res.status_code == 200:
                                            e_msgs = e_res.json().get("messages", [])
                                            if e_msgs:
                                                print(f"[AI Pipeline]     ✅ Encontrados {len(e_msgs)} emails.")
                                                email_history.append({"contact": p.get("name"), "email": email, "messages": e_msgs})
                                    except: pass
                            if email_history:
                                internal_context["email_result"] = {"resultado": {"messages_by_contact": email_history}}
            
        except Exception as e:
            print(f"[AI Chat] Erro ao buscar contexto: {e}")
            internal_context = {}
    
    return internal_context


async def _fetch_tasks(intent_info: dict, internal_context: dict, pipedrive_org_id, message: str):
    """Busca tarefas/atividades do Pipedrive com filtros inteligentes."""
    import httpx
    from datetime import date, timedelta
    
    date_f = intent_info.get("activity_date_filter", "today")
    filter_msg = f"para Empresa ID {pipedrive_org_id}" if pipedrive_org_id else "Global"
    print(f"[AI Pipeline] 📅 Buscando tarefas ({date_f}) {filter_msg}...")
    
    try:
        from services.pipedrive.pipedrive_service import pipedrive_service
        
        today = date.today().isoformat()
        
        # Detecção de Escopo: Padrão é sempre o usuário logado (Eu).
        # Só abre visão global se houver um comando explícito de gestão/equipe.
        global_triggers = [
            "todo o pipedrive", "da equipe", "do time", "geral da empresa", 
            "de todos os usuários", "dos vendedores", "empresa inteira",
            "visão global", "visão geral"
        ]
        msg_lower = message.lower()
        is_global_request = any(trigger in msg_lower for trigger in global_triggers)
        
        # REFORÇO: Se o usuário escreveu "meu", "minha", "pra mim", "comigo", força o filtro de usuário
        has_my_filter = any(me in msg_lower for me in ["meu", "minha", "pra mim", "comigo", "meus", "minhas"])
        if has_my_filter:
            is_global_request = False
        
        # Filtro de status de atividade (detectado pela IA no Estágio 1)
        done_filter = intent_info.get("activity_done_filter")
        done_values = [0, 1] if done_filter is None else [done_filter]
        
        all_activities = []
        async with httpx.AsyncClient() as pd_client:
            for dv in done_values:
                params = [f"api_token={pipedrive_service.api_token}"]
                if not is_global_request:
                    params.append(f"user_id={pipedrive_service.user_id}")
                params.append(f"done={dv}")
                
                query_string = "&".join(params)

                # 1. Se temos empresa específica, usamos o endpoint de ORGANIZATIONS 
                if pipedrive_org_id:
                    url_fetch = f"{pipedrive_service.base_url}/organizations/{pipedrive_org_id}/activities?{query_string}"
                # 2. Caso contrário, buscador global (Agenda)
                else:
                    url_fetch = f"{pipedrive_service.base_url}/activities?{query_string}"
                
                resp = await pd_client.get(url_fetch)
                data = resp.json()
                if data and data.get("success"):
                    all_activities.extend(data.get("data") or [])
        
        if all_activities:
                
                # 3. Filtragem Manual de Segurança (Python-side) e Filtro de Negócios Perdidos
                if not is_global_request:
                    all_activities = [
                        act for act in all_activities 
                        if str(act.get("user_id")) == str(pipedrive_service.user_id) or 
                           str(act.get("assigned_to_user_id")) == str(pipedrive_service.user_id)
                    ]

                # --- FILTRAGEM DE NEGÓCIOS PERDIDOS ---
                try:
                    deal_ids_in_tasks = {act.get("deal_id") for act in all_activities if act.get("deal_id")}
                    
                    if deal_ids_in_tasks:
                        deals_status_filter = f"&user_id={pipedrive_service.user_id}" if not is_global_request else ""
                        
                        valid_deal_ids = set()
                        for status in ["open", "won"]:
                            d_url = f"{pipedrive_service.base_url}/deals?status={status}{deals_status_filter}&limit=500&api_token={pipedrive_service.api_token}"
                            d_resp = await pd_client.get(d_url)
                            d_data = d_resp.json()
                            if d_data.get("success") and d_data.get("data"):
                                for d in d_data["data"]:
                                    valid_deal_ids.add(d["id"])
                        
                        prev_count = len(all_activities)
                        all_activities = [
                            act for act in all_activities 
                            if not act.get("deal_id") or act.get("deal_id") in valid_deal_ids
                        ]
                        removed = prev_count - len(all_activities)
                        if removed > 0:
                            print(f"[AI Pipeline] 🛡️ Filtro Pipedrive: Removidas {removed} tarefas de negócios PERDIDOS.")
                except Exception as e:
                    print(f"[AI Pipeline] ⚠️ Erro ao filtrar negócios perdidos: {e}")
                
                # 4. Filtragem por Data (Python-side)
                date_filter = intent_info.get("activity_date_filter", "today")
                
                # Se temos empresa específica, o padrão de data é 'all' se não especificado
                if pipedrive_org_id and not any(kw in msg_lower for kw in ["hoje", "amanhã", "atrasada", "proxima", "próxima"]):
                    date_filter = "all"
                
                tasks_to_return = []
                today_date = date.today()
                tomorrow_date = today_date + timedelta(days=1)
                
                for act in all_activities:
                    due = act.get("due_date")
                    if not due:
                        if date_filter == "all": tasks_to_return.append(act)
                        continue
                    
                    due_date = date.fromisoformat(due)
                    
                    if date_filter == "today" and due_date == today_date:
                        tasks_to_return.append(act)
                    elif date_filter == "tomorrow" and due_date == tomorrow_date:
                        tasks_to_return.append(act)
                    elif date_filter == "overdue" and due_date < today_date:
                        tasks_to_return.append(act)
                    elif date_filter == "future" and due_date >= today_date:
                        tasks_to_return.append(act)
                    elif date_filter == "all":
                        tasks_to_return.append(act)
                
                filter_msg = f"({date_filter})"
                if pipedrive_org_id:
                    filter_msg += f" da empresa {pipedrive_org_id}"
                
                internal_context["today_tasks"] = tasks_to_return
                print(f"[AI Pipeline] Encontradas {len(tasks_to_return)} tarefas {filter_msg}.")

    except Exception as e:
        print(f"[AI Chat] Erro ao buscar tarefas: {e}")
