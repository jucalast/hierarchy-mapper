"""
Orquestração de busca de dados contextuais.
Resolve organização, busca dados do Pipedrive, ContextService e OSINT.
"""
from typing import Optional, Dict, Any, List
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
    session: AsyncSession,
    selected_entities: List[dict] = None
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
            "whatsapp": [],
            "agent_workflow": ["deals", "activities", "today_tasks", "persons", "notes"]
        }
        data_scope = scope_defaults.get(query_type, ["deals", "activities", "today_tasks", "persons", "notes"])
    
    # Adiciona whatsapp/emails se o usuário mencionou palavras chave ou entidades
    if any(k in message.lower() for k in ["whats", "conversa", "histórico", "email"]):
        if "whatsapp" not in data_scope: data_scope.append("whatsapp")
        if "emails" not in data_scope: data_scope.append("emails")
    
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

    # --- BUSCA POR ETAPA DO PIPELINE (Se identificada) ---
    stage_name = intent_info.get("extracted_deal_stage")
    if stage_name and not org_id:
        print(f"[AI Pipeline] 📊 Buscando negócios na etapa: {stage_name}...")
        try:
            from services.pipedrive.pipedrive_service import pipedrive_service
            import httpx
            async with httpx.AsyncClient() as client:
                    # 1. Busca todos os estágios do pipeline (Com Cache)
                    all_stages_map = await pipedrive_service.get_all_stages()
                    
                    # Converte o mapa {id: name} para o formato de busca se necessário, ou busca direto
                    target_stage_id = None
                    target_stage_name = None
                    
                    for s_id, s_name in all_stages_map.items():
                        if stage_name.lower() in s_name.lower():
                            target_stage_id = s_id
                            target_stage_name = s_name
                            break
                    
                    if target_stage_id:
                        stage_id = target_stage_id
                        print(f"[AI Pipeline]   ✅ Etapa encontrada: {target_stage_name} (ID: {stage_id})")
                        
                        # Se o usuário NÃO especificou data (está 'today' por padrão do classificador), 
                        # mas pediu uma etapa, mudamos para 'all' para ser mais útil (vê a pauta toda).
                        # Se ele disse "hoje", "dia", etc., nós respeitamos o filtro de data.
                        msg_lower = message.lower()
                        time_keywords = ["hoje", "amanhã", "atrasada", "proxima", "próxima", "dia", "do dia", "atual"]
                        has_time_mention = any(kw in msg_lower for kw in time_keywords)

                        if intent_info.get("activity_date_filter") == "today" and not has_time_mention:
                            # Se pediu etapa mas não citou tempo, expandimos para 'all' (visão do pipeline)
                            intent_info["activity_date_filter"] = "all"
                        elif intent_info.get("activity_date_filter") == "all" and has_time_mention:
                            # Reforço dinâmico: se a IA mandou 'all' mas o usuário citou tempo na mensagem:
                            if any(k in msg_lower for k in ["hoje", "dia", "atual"]):
                                intent_info["activity_date_filter"] = "today"
                            elif any(k in msg_lower for k in ["amanhã", "amanha"]):
                                intent_info["activity_date_filter"] = "tomorrow"
                            elif any(k in msg_lower for k in ["atrasada", "vencida"]):
                                intent_info["activity_date_filter"] = "overdue"
                            elif any(k in msg_lower for k in ["proxima", "próxima", "futura"]):
                                intent_info["activity_date_filter"] = "future"
                        
                        # 2. Busca deals naquele estágio
                        deals_resp = await client.get(f"{pipedrive_service.base_url}/deals?stage_id={stage_id}&status=open&limit=500&api_token={pipedrive_service.api_token}")
                        if deals_resp.status_code == 200:
                            deals_in_stage = deals_resp.json().get("data") or []
                            internal_context["deals_in_stage"] = [
                                {
                                    "id": d.get("id"),
                                    "title": d.get("title"),
                                    "org_name": d.get("org_name"),
                                    "org_id": d.get("org_id"),
                                    "person_name": d.get("person_name"),
                                    "value": d.get("formatted_value")
                                } for d in deals_in_stage[:500] 
                            ]
                            print(f"[AI Pipeline]   🎯 Encontrados {len(deals_in_stage)} negócios nesta etapa.")
        except Exception as e:
            print(f"[AI Pipeline] ⚠️ Erro ao buscar negócios por etapa: {e}")

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

            # --- HIGIENIZAÇÃO DE CONTEÚDO (Módulo de Limpeza de E-mails) ---
            def sanitize_email_body(body: str) -> str:
                if not body: return ""
                # 1. Remove assinaturas e históricos redundantes (delimitadores comuns)
                delimiters = [
                    "________________________________",
                    "From:", "De:", "Enviada:", "Subject:", "Assunto:",
                    "--- Mensagem Original ---",
                    "Sent from my iPhone", "Enviado do meu iPhone"
                ]
                for d in delimiters:
                    if d in body:
                        body = body.split(d)[0]
                
                # 2. Limpeza de ruído (Links Sociais e Disclaimer Legal)
                import re
                # Remove links de redes sociais e ícones comuns em assinaturas
                body = re.sub(r'https?://[^\s]*(linkedin|facebook|instagram|twitter|youtube)[^\s]*', '', body, flags=re.IGNORECASE)
                # Remove avisos legais padrão (disclaimers)
                disclaimers = [
                    "esta mensagem pode conter informações confidenciais",
                    "this message contains confidential information",
                    "se você não for o destinatário",
                    "please notify the sender"
                ]
                for ds in disclaimers:
                    if ds in body.lower():
                        body = re.sub(rf'.*{ds}.*', '', body, flags=re.IGNORECASE | re.DOTALL)
                
                # 3. Normalização de espaços
                body = re.sub(r'\n\s*\n', '\n', body) # Remove linhas vazias excessivas
                return body.strip()

            # ============================
            # SCOPE: Communications (WhatsApp & Email)
            # ============================
            # Se temos os contatos do Pipedrive, podemos buscar o histórico de conversas real
            if any(s in data_scope for s in ["whatsapp", "emails"]):
                p_details = internal_context.get("pipedrive_details", {})
                persons = p_details.get("persons", []) if isinstance(p_details, dict) else []
                
                import re
                mentioned_names = re.findall(r"@([\w\s,]+)", message)
                mentioned_names = [n.strip().lower() for n in mentioned_names]
                
                if persons or selected_entities or mentioned_names:
                    print(f"[AI Pipeline] 💬 Identificados contatos para busca de comunicações.")
                    from services.ai.action_executor import _execute_get_messages, execute_email_action
                    import httpx
                    
                    wa_base = "http://localhost:8001/api/whatsapp"
                    email_base = "http://localhost:8002/api/email"
                    
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        # --- UNIFICAÇÃO DE CANDIDATOS (Pipedrive + Selecionados + Menções) ---
                        # 1. Começamos com a lista (se o usuário escolheu pessoas específicas na UI, ignoramos o barulho geral da empresa)
                        explicit_selected = [e for e in (selected_entities or []) if (e.get("type") if isinstance(e, dict) else getattr(e, "type", None)) in ["email", "whatsapp", "person", "employee"]]
                        final_candidates = [] if explicit_selected else list(persons)
                        
                        # 2. Adicionamos as empresas/pessoas selecionadas na UI (Prioridade Máxima)
                        if selected_entities:
                            for ent in selected_entities:
                                e_type = ent.get("type", "company")
                                e_name = ent.get("name", "Entidade")
                                
                                # Se a entidade já tem os dados (veio do dropdown), ela é nossa fonte primária
                                if not any(e_name.lower() == c.get("name", "").lower() for c in final_candidates):
                                    candidate = {
                                        "name": e_name,
                                        "email": [],
                                        "phone": [],
                                        "source": f"Seleção Direta ({e_type.capitalize()})",
                                        "locked_channel": e_type if e_type in ["email", "whatsapp"] else None
                                    }
                                    
                                    # Mapeamento dinâmico baseado no tipo do dropdown
                                    if e_type == "email":
                                        val = ent.get("value") or ent.get("email")
                                        if val: candidate["email"] = [{"value": val, "primary": True}]
                                    elif e_type == "whatsapp":
                                        val = ent.get("value") or ent.get("phone")
                                        if val: candidate["phone"] = [{"value": val, "primary": True}]
                                    else:
                                        # Tipo Company ou Person genérico
                                        if ent.get("email"): 
                                            v = ent.get("email")
                                            candidate["email"] = v if isinstance(v, list) else [{"value": v}]
                                        if ent.get("phone"):
                                            v = ent.get("phone")
                                            candidate["phone"] = v if isinstance(v, list) else [{"value": v}]

                                    # RESGATE DE METADADOS: Se ainda estiver vazio, busca no banco local pelo nome
                                    if not candidate["email"] and not candidate["phone"]:
                                        try:
                                            from models.employee import Employee
                                            from sqlalchemy import select, func, or_
                                            # Tenta achar por nome exato ou aproximação (Matheus Muniz vs Muniz, Matheus)
                                            search_name = e_name.replace(",", " ").strip()
                                            frags = [f.strip() for f in search_name.split() if len(f.strip()) > 2]
                                            if frags:
                                                stmt = select(Employee).where(and_(*[func.lower(Employee.name).like(f"%{f.lower()}%") for f in frags]))
                                                res = await session.execute(stmt)
                                                emp = res.scalars().first()
                                                if emp:
                                                    if emp.email: candidate["email"] = [{"value": emp.email, "primary": True}]
                                                    if emp.whatsapp_number: candidate["phone"] = [{"value": emp.whatsapp_number, "primary": True}]
                                                    print(f"[AI Pipeline]   🔐 Metadados resgatados do Banco para: {emp.name}")
                                        except: pass

                                    final_candidates.insert(0, candidate)
                                    print(f"[AI Pipeline]   🎯 Usando {e_type} selecionado: {e_name} (Email: {bool(candidate['email'])}, Phone: {bool(candidate['phone'])})")
                        
                        # 3. Buscamos no banco local (Employees) por pessoas mencionadas que não estão no Pipedrive
                        if mentioned_names:
                            try:
                                from models.employee import Employee
                                from sqlalchemy import select, or_, and_
                                for name in mentioned_names:
                                    # Limpeza: remove vírgulas e tenta fragmentos
                                    fragments = [f.strip() for f in name.replace(",", " ").split() if len(f.strip()) > 2]
                                    if not fragments: continue
                                    
                                    # Busca que contenha TODOS os fragmentos grandes (ex: Matheus + Muniz)
                                    filters = [func.lower(Employee.name).like(f"%{frag}%") for frag in fragments]
                                    emp_q = select(Employee).where(and_(*filters))
                                    emp_res = await session.execute(emp_q)
                                    for emp in emp_res.scalars().all():
                                        if not any(emp.name.lower() == c.get("name", "").lower() for c in final_candidates):
                                            print(f"[AI Pipeline]   📍 Adicionando candidato via menção: {emp.name}")
                                            final_candidates.insert(0, {
                                                "name": emp.name,
                                                "email": [{"value": emp.email}] if emp.email else [],
                                                "phone": [{"value": emp.whatsapp_number}] if emp.whatsapp_number else []
                                            })
                            except Exception as e:
                                print(f"[AI Pipeline] Erro ao buscar menções no banco local: {e}")

                        # Reordena para colocar os mencionados com @ no topo absoluto
                        def sort_priority(p):
                            name_low = p.get("name", "").lower()
                            if any(mn in name_low for mn in mentioned_names): return 0
                            return 1
                        
                        final_candidates.sort(key=sort_priority)
                        
                        # 1. WhatsApp (Com os top 5 candidatos unificados)
                        if "whatsapp" in data_scope:
                            wa_history = []
                            for p in final_candidates[:5]:
                                phone_list = p.get("phone", [])
                                phone = None
                                if isinstance(phone_list, list) and len(phone_list) > 0:
                                    phone = phone_list[0].get("value")
                                
                                if phone:
                                    print(f"[AI Pipeline]   - Buscando WhatsApp para {p.get('name')} ({phone})...")
                                    res = await _execute_get_messages(client, wa_base, {"whatsapp_number": phone, "extracted_person_name": p.get("name")}, None, None)
                                    if res and "resultado" in res:
                                        msgs = res["resultado"].get("messages", [])
                                        if msgs:
                                            from datetime import datetime
                                            formatted_msgs = []
                                            for m in msgs:
                                                dt_obj = datetime.fromtimestamp(m.get("timestamp", 0))
                                                m["date_human"] = dt_obj.strftime("%d/%m/%Y %H:%M")
                                                formatted_msgs.append(m)
                                            print(f"[AI Pipeline]     ✅ Encontradas {len(msgs)} mensagens.")
                                            wa_history.append({"contact": p.get("name"), "messages": formatted_msgs})
                            if wa_history:
                                internal_context["whatsapp_result"] = {"resultado": {"messages_by_contact": wa_history}}

                        # 2. Emails
                        if "emails" in data_scope:
                            email_history = []
                            email_base = "http://localhost:8002/api/email"
                            
                            for p in final_candidates[:5]:
                                email_list = p.get("email", [])
                                email = None
                                if isinstance(email_list, list) and len(email_list) > 0:
                                    email = email_list[0].get("value")
                                if email:
                                    print(f"[AI Pipeline]   - Buscando Emails para {p.get('name')} ({email})...")
                                    try:
                                        e_res = await client.get(f"{email_base}/messages?folder=Conversations&limit=30&q={email}")
                                        if e_res.status_code == 200:
                                            all_e_msgs = e_res.json().get("messages", [])
                                            human_emails = []
                                            automated_emails = []
                                            noise_keywords = ["lusha", "webinar", "noreply", "no-reply", "notification", "system", "linkedin", "hunter.io", "zoominfo", "pipedrive.com"]
                                            for e_msg in all_e_msgs:
                                                from_addr = e_msg.get("from", "").lower()
                                                subject = e_msg.get("subject", "").lower()
                                                is_noise = any(kw in from_addr or kw in subject for kw in noise_keywords)
                                                if is_noise:
                                                    automated_emails.append(e_msg)
                                                else:
                                                    clean_body = sanitize_email_body(e_msg.get("body", ""))
                                                    e_msg["body"] = clean_body
                                                    human_emails.append(e_msg)
                                            if human_emails or automated_emails:
                                                print(f"[AI Pipeline]     ✅ Analisados {len(all_e_msgs)} emails ({len(human_emails)} humanos, {len(automated_emails)} automações).")
                                                email_history.append({
                                                    "contact": p.get("name"), 
                                                    "email": email, 
                                                    "human_threads": human_emails,
                                                    "automated_count": len(automated_emails)
                                                })
                                    except Exception as e:
                                        print(f"[AI Pipeline]     ⚠️ Erro ao buscar e-mails: {e}")
                            if email_history:
                                internal_context["email_result"] = {"resultado": {"messages_by_contact": email_history}}
                                
            # --- CONSOLIDAÇÃO DE LINHA DO TEMPO (Cálculo de Silêncio Real) ---
            try:
                all_interaction_dates = []
                p_details = internal_context.get("pipedrive_details", {})
                
                # 1. Datas do Pipedrive (Atividades Concluídas)
                activities_pd = (p_details.get("activities", []) if isinstance(p_details, dict) else [])
                for act in activities_pd:
                    if act.get("done") and act.get("due_date"):
                        try:
                            # Tenta YYYY-MM-DD (Padrão Pipedrive)
                            all_interaction_dates.append(datetime.strptime(act.get("due_date"), "%Y-%m-%d"))
                        except: pass
                
                # 2. Datas de WhatsApp
                wa_res = internal_context.get("whatsapp_result", {}).get("resultado", {}).get("messages_by_contact", [])
                for group in wa_res:
                    for m in group.get("messages", []):
                        ts = m.get("timestamp")
                        if ts:
                            try: all_interaction_dates.append(datetime.fromtimestamp(ts))
                            except: pass
                
                # 3. Datas de Email (Apenas Humanos)
                email_res = internal_context.get("email_result", {}).get("resultado", {}).get("messages_by_contact", [])
                for contact_emails in email_res:
                    for thread in contact_emails.get("human_threads", []):
                        date_str = thread.get("date")
                        if date_str:
                            try:
                                # Limpa fuso horário e milissegundos para o strptime
                                clean_date = str(date_str).split(".")[0].replace("+00:00", "").replace("Z", "").strip()
                                # Testa formatos comuns
                                formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]
                                for f in formats:
                                    try:
                                        all_interaction_dates.append(datetime.strptime(clean_date, f))
                                        break
                                    except: continue
                            except: pass
                
                if all_interaction_dates:
                    last_human_interaction = max(all_interaction_dates)
                    delta_days = (datetime.now() - last_human_interaction).days
                    internal_context["calculated_status"] = {
                        "last_interaction_date": last_human_interaction.strftime("%d/%m/%Y %H:%M"),
                        "silence_days": delta_days,
                        "is_critical": delta_days > 10,
                        "summary": f"O último contato humano REAL foi em {last_human_interaction.strftime('%d/%m/%Y')} ({delta_days} dias atrás)."
                    }
                    print(f"[AI Pipeline] 📊 Métrica consolidada: {delta_days} dias de silêncio.")
            except Exception as e_metric:
                print(f"[AI Pipeline] ⚠️ Erro ao calcular métricas de silêncio: {e_metric}")

            
        except Exception as e:
            print(f"[AI Chat] Erro crítico ao buscar contexto: {e}")
            
    internal_context["selected_entities"] = selected_entities
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
        
        all_activities = []
        async with httpx.AsyncClient() as pd_client:
            # PRIORIDADE 1: Buscar a agenda do PRÓPRIO usuário (Sem limite de 500 escondendo as dele)
            # Isso garante que a Trimplas apareça se estiver no nome dele.
            user_agenda_url = f"{pipedrive_service.base_url}/activities?user_id={pipedrive_service.user_id}&done=0&limit=500&api_token={pipedrive_service.api_token}"
            r_agenda = await pd_client.get(user_agenda_url)
            if r_agenda.status_code == 200:
                all_activities.extend(r_agenda.json().get("data") or [])
                print(f"[AI Pipeline] 📅 Agenda: Coletadas {len(all_activities)} tarefas diretas de João Luccas.")

            # PRIORIDADE 2: Buscar tarefas ligadas aos negócios da etapa (Se houver etapa)
            deals_in_stage = internal_context.get("deals_in_stage", [])
            if deals_in_stage:
                import asyncio
                async def fetch_deal_acts(deal_id):
                    # Usamos user_id=0 aqui para pegar tarefas de outros se estiverem no negócio da etapa
                    d_url = f"{pipedrive_service.base_url}/deals/{deal_id}/activities?done=0&limit=50&api_token={pipedrive_service.api_token}"
                    r = await pd_client.get(d_url)
                    return r.json().get("data") or [] if r.status_code == 200 else []
                
                # Pegamos os primeiros 100 negócios da etapa para não estourar rate limit
                tasks = [fetch_deal_acts(d["id"]) for d in deals_in_stage[:100]]
                results = await asyncio.gather(*tasks)
                for res in results:
                    all_activities.extend(res)
                
            # PRIORIDADE 3: Busca por Organização (Se houver empresa específica)
            elif pipedrive_org_id:
                org_url = f"{pipedrive_service.base_url}/organizations/{pipedrive_org_id}/activities?done=0&api_token={pipedrive_service.api_token}"
                r_org = await pd_client.get(org_url)
                if r_org.status_code == 200:
                    all_activities.extend(r_org.json().get("data") or [])
        
            if all_activities:
                # --- FILTRAGEM GLOBAL: Somente tarefas vinculadas a NEGÓCIOS (Deals) ---
                initial_count = len(all_activities)
                deal_only_activities = []
                for act in all_activities:
                    d_id_raw = act.get("deal_id")
                    if d_id_raw:
                        d_val = d_id_raw.get("value") if isinstance(d_id_raw, dict) else d_id_raw
                        if d_val:
                            deal_only_activities.append(act)
                
                all_activities = deal_only_activities
                if len(all_activities) < initial_count:
                    print(f"[AI Pipeline] 🛡️ Filtro Global: Removidas {initial_count - len(all_activities)} tarefas que não estavam vinculadas a nenhum negócio.")
                # 2.5 Filtragem por ETAPA (Se solicitada)
                deals_in_stage = internal_context.get("deals_in_stage", [])
                if deals_in_stage:
                    stage_deal_ids = {d.get("id") for d in deals_in_stage}
                    
                    # Extração segura de Org IDs (Pipedrive pode retornar int ou dict)
                    stage_org_ids = set()
                    for d in deals_in_stage:
                        oid = d.get("org_id")
                        if isinstance(oid, dict):
                            stage_org_ids.add(oid.get("value"))
                        elif oid:
                            stage_org_ids.add(oid)
                    
                    safe_activities = []
                    for act in all_activities:
                        a_deal = act.get("deal_id")
                        a_deal_id = a_deal.get("value") if isinstance(a_deal, dict) else a_deal
                        
                        # FILTRO CRÍTICO: Só queremos tarefas ligadas a NEGÓCIOS (Deals)
                        if a_deal_id and a_deal_id in stage_deal_ids:
                            safe_activities.append(act)
                            
                    all_activities = safe_activities
                    print(f"[AI Pipeline] 📊 Filtro de Etapa: Mantive {len(all_activities)} tarefas vinculadas a NEGÓCIOS da etapa solicitada.")

                # 3. Filtragem Manual de Segurança (Python-side) e Filtro de Negócios Perdidos
                if not is_global_request:
                    user_filtered = []
                    target_id = str(pipedrive_service.user_id)
                    for act in all_activities:
                        u1 = act.get("user_id") or {}
                        u1_id = str(u1.get("value") if isinstance(u1, dict) else u1)
                        u1_name = str(u1.get("name", "")).lower() if isinstance(u1, dict) else ""
                        
                        u2 = act.get("assigned_to_user_id") or {}
                        u2_id = str(u2.get("value") if isinstance(u2, dict) else u2)
                        u2_name = str(u2.get("name", "")).lower() if isinstance(u2, dict) else ""
                        
                        # Debug logging
                        if "trimplas" in str(act.get("deal_id", "")).lower():
                             print(f"[DEBUG] Trimplas task found. ids: {u1_id}, {u2_id} | names: {u1_name}, {u2_name} | target: {target_id}")
                        
                        # Verifica por ID ou por Nome (Backup de segurança)
                        is_me = (u1_id == target_id or u2_id == target_id or 
                                 "joao" in u1_name or "luccas" in u1_name or
                                 "joao" in u2_name or "luccas" in u2_name)
                        
                        if is_me:
                            user_filtered.append(act)
                        else:
                            # Log para entender quem está furando o filtro
                            pass
                    
                    if len(all_activities) != len(user_filtered):
                        # --- FILTRAGEM DE NEGÓCIOS (Perdidos ou de Terceiros) ---
                        # Removido filtro redundante que re-validava o status 'open' individualmente.
                        # Já garantimos que são negócios abertos no filtro de ETAPA inicial.
                        pass
                    
                    all_activities = user_filtered
                    
                # --- FINALIZAÇÃO: Limpeza e Formato Final ---
                tasks_to_return = []
                date_filter = intent_info.get("activity_date_filter", "today")
                
                if all_activities:
                    today_date = date.today()
                    tomorrow_date = today_date + timedelta(days=1)
                    
                    for act in all_activities:
                        due = act.get("due_date")
                        if not due:
                            if date_filter == "all": tasks_to_return.append(act)
                            continue
                        
                        due_date = date.fromisoformat(due)
                        
                        # DEBUG PROOF
                        print(f"[DEBUG] Processing Task SUBJECT: {act.get('subject')} | DUE: {due_date} | TODAY: {today_date} | TYPE: {type(due_date)} vs {type(today_date)}")
                        
                        # FILTRO RÍGIDO: Apenas hoje
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
                        elif not date_filter: 
                            # Se não houver filtro, mas houver etapa, retornamos tudo daquela etapa
                            tasks_to_return.append(act)
                
                filter_msg = f"({date_filter})"
                if pipedrive_org_id:
                    filter_msg += f" da empresa {pipedrive_org_id}"
                
                internal_context["today_tasks"] = tasks_to_return
                print(f"[AI Pipeline] Encontradas {len(tasks_to_return)} tarefas {filter_msg}.")

    except Exception as e:
        print(f"[AI Chat] Erro ao buscar tarefas: {e}")
