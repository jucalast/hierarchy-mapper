"""
Orquestração de busca de dados contextuais.
Resolve organização, busca dados do Pipedrive, ContextService e OSINT.
"""
from typing import Optional, Dict, Any, List
import asyncio
import json
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, or_, and_


def sanitize_email_body(body: str) -> str:
    """Limpeza robusta de e-mails para reduzir ruído e tokens."""
    if not body: return ""
    import re
    
    # 1. Remove HTML
    body = re.sub(r'<[^>]+>', ' ', body)
    
    # 2. Corta em delimitadores de resposta (Forward/Reply)
    delimiters = [
        "________________________________", "From:", "De:", "Enviada:", "Subject:", "Assunto:",
        "--- Mensagem Original ---", "Sent from my iPhone", "Enviado do meu iPhone",
        "Obter o Outlook para", "Get Outlook for"
    ]
    for d in delimiters:
        if d in body:
            body = body.split(d)[0]
    
    # 3. Remove Links e Disclaimers
    body = re.sub(r'https?://[^\s]+', '', body)
    disclaimers = ["confidencial", "destinatário", "notify the sender", "error in transmission", "legal notice"]
    lines = body.split('\n')
    clean_lines = [l for l in lines if not any(d in l.lower() for d in disclaimers) and len(l.strip()) > 2]
    
    # 4. Normaliza espaços e limita tamanho
    text = " ".join(clean_lines)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:800]



async def resolve_organization(
    payload_org_id: Optional[Any],
    selected_companies: list,
    extracted_name: Optional[str],
    message: str,
    session: AsyncSession,
    log_queue: Optional[asyncio.Queue] = None
) -> Optional[int]:
    """
    Resolve o org_id a partir das fontes disponíveis:
    1. selectedCompanies da UI
    2. Nome extraído pela IA
    3. Regex fallback
    """
    from modules.context.service.service import ContextService
    
    def log_ev(msg, type="thought"):
        print(f"[AI Chat] {msg}")
        if log_queue:
            try: log_queue.put_nowait({"type": type, "content": msg})
            except: pass

    org_id = payload_org_id
    
    # Se temos uma empresa explícita na UI, usamos ela
    if selected_companies and len(selected_companies) > 0:
        org_id = selected_companies[0].id
        log_ev(f"Usando empresa da UI: {selected_companies[0].name}")
    # Se não temos orgId das props UI, mas a IA extraiu do texto e não havia orgId
    elif not org_id and extracted_name:
        log_ev(f"Buscando empresa inferida pela IA: {extracted_name}")
        org_data_resolved = await ContextService.fetch_organization_by_name(session, extracted_name)
        if org_data_resolved:
            org_id = org_data_resolved.id
        else:
            # NOVIDADE: Se não achou no banco local, tenta buscar direto no Pipedrive
            try:
                from modules.crm.service.pipedrive_service import pipedrive_service
                log_ev(f"Empresa '{extracted_name}' não encontrada localmente. Buscando no Pipedrive...")
                pd_orgs = await pipedrive_service.search_organization(extracted_name)
                if pd_orgs:
                    # Se achou no Pipedrive, o org_id continuará sendo None aqui (pois não está no banco local),
                    # mas o ContextService (ou o fetch posterior) pode usar o nome.
                    # No momento, o fetch_contextual_data trata o target_company se org_id for None.
                    pass
            except Exception as e:
                log_ev(f"Erro ao buscar empresa no Pipedrive: {e}", type="log")
            
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
    session: AsyncSession,
    log_queue: Optional[asyncio.Queue] = None
) -> Optional[Dict[str, Any]]:
    """
    Executa enriquecimento OSINT para um lead específico.
    Retorna o contexto OSINT para injeção no pipeline.
    """
    from modules.context.service.service import ContextService
    from core.external.osint_service import osint_service
    from models.people.employee import Employee
    
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
        
        def log_ev(msg, type="thought"):
            print(f"[AI Chat] {msg}")
            if log_queue:
                try: log_queue.put_nowait({"type": type, "content": msg})
                except: pass

        log_ev(f"Executando Enriquecimento OSINT para {target_person} na {target_company}...")
        osint_data = await osint_service.enrich_lead(target_person, target_company, domain=target_domain, cnpj=target_cnpj)
        if osint_data and "error" not in osint_data:
            osint_context = {
                "osint_result": osint_data,
                "status": "success"
            }
            log_ev(f"Enriquecimento concluído: {osint_data.get('whatsapp', {}).get('numero')}")
            
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
    selected_entities: List[dict] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Busca dados contextuais com base nos escopos definidos pelo classificador de intenção.
    Retorna o internal_context preenchido.
    """
    from modules.context.service.service import ContextService
    from datetime import date, timedelta
    
    internal_context = {
        "selected_entities": selected_entities or [],
        "_org_id": org_id,  # Campo canônico para lookup de cache sem ambiguidade
    }
    query_type = intent_info.get("query_type", "general")
    data_scope = intent_info.get("data_scope", [])
    target_company = intent_info.get("extracted_company_name")
    
    # Fallback: se data_scope veio vazio, inferimos pelo query_type para retrocompatibilidade
    if not data_scope:
        scope_defaults = {
            "contacts": ["employees", "decision_makers", "persons"],
            "pipedrive_info": ["deals", "activities", "notes", "persons"],
            "pipedrive_tasks": ["today_tasks"],
            "company_info": [],
            "general": [],
            "whatsapp": ["whatsapp"],
            "emails": ["emails"],
            "deal_status": ["deals", "activities", "persons", "notes", "emails", "whatsapp"],
            "agent_workflow": ["deals", "activities", "persons", "notes", "emails", "whatsapp"]
        }
        data_scope = scope_defaults.get(query_type, ["deals", "activities", "persons", "notes", "emails", "whatsapp"])

    # GARANTIA: Se for agent_workflow ou deal_status, OBRIGAR e-mails e whatsapp
    if query_type in ("agent_workflow", "deal_status"):
        if "emails" not in data_scope: data_scope.append("emails")
        if "whatsapp" not in data_scope: data_scope.append("whatsapp")
    
    log_queue = kwargs.get("log_queue")
    
    def log_ev(msg, type="thought"):
        if log_queue:
            try:
                # Mapeamento para tipos que o frontend espera (AgentService parity)
                if type == "data_found_deal":
                    log_queue.put_nowait({"type": "data_found", "entity": "deal", "data": msg})
                elif type == "data_found_activity":
                    log_queue.put_nowait({"type": "data_found", "entity": "activity", "data": msg})
                elif type == "data_found_contact":
                    log_queue.put_nowait({"type": "data_found", "entity": "contact", "data": msg})
                elif type == "data_found_whatsapp":
                    log_queue.put_nowait({"type": "data_found", "entity": "whatsapp", "data": msg})
                elif type == "data_found_email":
                    log_queue.put_nowait({"type": "data_found", "entity": "email", "data": msg})
                else:
                    log_queue.put_nowait({"type": type, "content": str(msg)})
            except Exception: pass
        
        # Mantém log no terminal para debug
        if isinstance(msg, (dict, list)):
            print(f"[AI Pipeline] {type}: {str(msg)[:100]}...")
        else:
            print(f"[AI Pipeline] {msg}")

    log_ev(f"Escopos de dados selecionados: {data_scope}")

    # --- BUSCA DE DADOS DA EMPRESA (Se identificada) ---
    pipedrive_org_id = None
    org_data = None
    basic_context = {}
    
    if org_id:
        try:
            basic_context = await ContextService.fetch_organization_overview(session, org_id)
            org_data = basic_context.get("organization", {})
            if org_data:
                # NOVIDADE: Se a organização não tem Pipedrive ID, tentamos descobrir por nome
                if not org_data.get("pipedrive_id"):
                    log_ev(f"Empresa '{org_data.get('name')}' sem Pipedrive ID. Tentando descoberta...")
                    try:
                        from modules.crm.service.pipedrive_service import pipedrive_service
                        pd_orgs = await pipedrive_service.search_organization(org_data.get('name'))
                        if pd_orgs:
                            discovered_id = pd_orgs[0].get("id")
                            org_data["pipedrive_id"] = discovered_id
                            log_ev(f"Pipedrive ID descoberto: {discovered_id}")
                    except Exception as discovery_err:
                        log_ev(f"Falha na descoberta de Pipedrive ID: {discovery_err}", type="log")

                internal_context["organization"] = {
                    "name": org_data.get("name"),
                    "cnpj": org_data.get("cnpj"),
                    "domain": org_data.get("domain"),
                    "pipedrive_id": org_data.get("pipedrive_id"),
                    "address": org_data.get("address"),
                    "logo_url": org_data.get("logo_url") or org_data.get("logo"),
                    "employees_count": org_data.get("employees_count", 0),
                    "employees": org_data.get("employees", [])
                }
                pipedrive_org_id = org_data.get("pipedrive_id")
        except Exception as e:
            print(f"[AI Chat] Erro ao buscar overview da empresa: {e}")
            import traceback
            traceback.print_exc()
    elif target_company and target_company.lower() not in ["null", "none"]:
        # NOVIDADE: Lead que não está no banco local mas foi identificado pelo nome
        log_ev(f"Empresa '{target_company}' não encontrada localmente. Buscando no Pipedrive...")
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            pd_orgs = await pipedrive_service.search_organization(target_company)
            if pd_orgs:
                org_match = pd_orgs[0]
                pipedrive_org_id = org_match.get("id")
                internal_context["organization"] = {
                    "name": org_match.get("name"),
                    "pipedrive_id": pipedrive_org_id,
                    "is_virtual": True  # Indica que não está no banco local ainda
                }
                log_ev(f"Empresa encontrada no Pipedrive: {org_match.get('name')} (ID: {pipedrive_org_id})")
        except Exception as e:
            log_ev(f"Erro na busca direta Pipedrive: {e}", type="log")

    # --- BUSCA POR ETAPA DO PIPELINE (Se identificada) ---
    stage_name = intent_info.get("extracted_deal_stage")
    if stage_name and not org_id:
        log_ev(f"Buscando negócios na etapa: {stage_name}...")
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
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
                        log_ev(f"Etapa encontrada: {target_stage_name} (ID: {stage_id})")
                        
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
                            
                            # --- NOVIDADE: FILTRO DE FOCO (Evita processamento em lote indesejado) ---
                            target_company = intent_info.get("extracted_company_name")
                            if target_company and target_company.lower() not in ["null", "none"]:
                                log_ev(f"Aplicando filtro de foco: {target_company}")
                                # Filtra a lista de deals para manter apenas os que batem com o nome da empresa
                                filtered_deals = [
                                    d for d in deals_in_stage 
                                    if target_company.lower() in str(d.get("org_name", "")).lower()
                                ]
                                if filtered_deals:
                                    deals_in_stage = filtered_deals
                                    log_ev(f"Foco reduzido para {len(deals_in_stage)} negócios da {target_company}.")
                            
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
                            log_ev(f"Total de {len(deals_in_stage)} negócios injetados no contexto.")
        except Exception as e:
            log_ev(f"Erro ao buscar negócios por etapa: {e}", type="log")

    # --- BUSCA DE TAREFAS (Com filtro inteligente de empresa se houver) ---
    if "today_tasks" in data_scope or ("activities" in data_scope and query_type == "pipedrive_tasks"):
        await _fetch_tasks(intent_info, internal_context, pipedrive_org_id, message)

    # --- BUSCA DE DADOS CONTEXTUAIS ADICIONAIS ---
    # 1. Dados do Banco Local (Requer org_id)
    if org_id:
        try:
            # Se qualquer escopo envolve info completa da org (contacts/company_info)
            if any(s in data_scope for s in ["employees", "decision_makers"]):
                if org_data:
                    internal_context["organization"] = org_data
            
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
            
            # Estatísticas (sempre que houver dados de pessoas)
            if any(s in data_scope for s in ["employees", "decision_makers"]):
                internal_context['statistics'] = basic_context.get('statistics', {})

        except Exception as e:
            print(f"[AI Pipeline] ⚠️ Erro ao buscar dados locais adicionais: {e}")

    # 2. Dados do Pipedrive (Requer apenas pipedrive_org_id)
    pipedrive_scopes = [s for s in data_scope if s in ("persons", "deals", "activities", "notes")]
    if pipedrive_scopes and pipedrive_org_id:
        log_ev(f"Buscando Pipedrive [{', '.join(pipedrive_scopes)}]...")
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            # Passa o filtro de 'concluídas' se a IA detectou que o usuário as quer
            done_filter = intent_info.get("activity_done_filter")
            pd_details = await pipedrive_service.get_organization_details(pipedrive_org_id, done=done_filter)
                    
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
                    log_ev(f"Pipedrive: Coletados {len(filtered_pd.get('activities', []))} atividades, {len(filtered_pd.get('deals', []))} negócios e {len(filtered_pd.get('persons', []))} contatos.")
                    internal_context["pipedrive_details"] = filtered_pd
                    
                    # EMISSÃO VISUAL: Deixa o usuário ver os cards enquanto a IA processa
                    for d in filtered_pd.get("deals", []):
                        log_ev(d, type="data_found_deal")
                    for a in filtered_pd.get("activities", []):
                        log_ev(a, type="data_found_activity")
                    
                    def _clean_person(p: dict) -> dict:
                        """Limpa campos de contato (arrays de objetos -> strings) para o frontend."""
                        cp = p.copy()
                        # Pipedrive retorna phone/email como [{value, label, primary}, ...]
                        for field in ["phone", "email"]:
                            val = cp.get(field)
                            if isinstance(val, list) and len(val) > 0:
                                cp[field] = val[0].get("value") if isinstance(val[0], dict) else val[0]
                        return cp

                    for p in filtered_pd.get("persons", []):
                        log_ev(_clean_person(p), type="data_found_contact")

                    # Se for busca de tarefas, garante que fiquem no top-level para o TaskList bypass
                    if "activities" in filtered_pd and query_type == "pipedrive_tasks":
                        internal_context["activities"] = filtered_pd["activities"]
            else:
                internal_context["pipedrive_details"] = pd_details or {"error": "Sem dados"}
        except Exception as e:
            log_ev(f"Erro ao buscar dados do Pipedrive: {e}", type="log")

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
            log_ev("Identificados contatos para busca de comunicações.")
            from modules.triggers.service.action_executor import _execute_get_messages, execute_email_action
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
                                    from models.people.employee import Employee
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
                        from models.people.employee import Employee
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
                
                # 1. WhatsApp (Paralelizado)
                if "whatsapp" in data_scope:
                    wa_history = []
                    wa_tasks = []
                    for p in final_candidates[:5]:
                        phone_list = p.get("phone", [])
                        if isinstance(phone_list, list):
                            for ph_item in phone_list:
                                phone = ph_item.get("value")
                                if phone: 
                                    # Evita duplicar se o mesmo número aparecer em campos diferentes
                                    if not any(t[1] == phone for t in wa_tasks):
                                        wa_tasks.append((p.get("name"), phone))
                    
                    if wa_tasks:
                        log_ev(f"Buscando WhatsApp para {len(wa_tasks)} contatos em paralelo...")
                        def _preprocess_wa_message(msg: dict) -> Optional[dict]:
                            """Processa mensagem: limpa base64 e rotula mídias sem texto."""
                            body = msg.get("body") or msg.get("caption") or ""
                            msg_type = (msg.get("type") or "chat").lower()
                            
                            # Se o corpo for muito grande e sem espaços, provavelmente é lixo binário/base64
                            if len(body) > 120 and " " not in body and not any(c in body for c in [".", "!", "?", ",", "\n", ":"]):
                                msg["body"] = "[Conteúdo Binário Truncado]"
                                return msg
                                
                            # Se for uma mídia/mensagem especial sem texto, injetamos um rótulo para a IA saber o que é
                            if not body or len(body.strip()) < 1:
                                type_labels = {
                                    "image": "[Imagem]",
                                    "video": "[Vídeo]",
                                    "audio": "[Áudio]",
                                    "ptt": "[Mensagem de Voz]",
                                    "sticker": "[Sticker]",
                                    "document": "[Documento/Arquivo]",
                                    "vcard": "[Contato/VCard]",
                                    "location": "[Localização]",
                                    "call_log": "[Registro de Chamada]",
                                    "revoked": "[Mensagem Apagada]",
                                    "e2e_notification": "[Notificação de Criptografia]",
                                    "e2e_encryption": "[Notificação de Criptografia]"
                                }
                                # Se não é um 'chat' normal e está vazio, rotulamos pelo tipo
                                if msg_type != "chat":
                                    msg["body"] = type_labels.get(msg_type, f"[Interação: {msg_type.capitalize()}]")
                                    return msg
                                else:
                                    # Se for um chat normal (texto) e está vazio, descartamos
                                    return None
                                    
                            return msg

                        async def fetch_wa(name, num):
                            try:
                                res = await _execute_get_messages(client, wa_base, {"whatsapp_number": num, "extracted_person_name": name, "limit": 50}, None, None)
                                if res and "resultado" in res:
                                    msgs = res["resultado"].get("messages", [])
                                    if msgs:
                                        from datetime import datetime
                                        processed_msgs = []
                                        for m in msgs:
                                            p = _preprocess_wa_message(m)
                                            if p: processed_msgs.append(p)

                                        # Verifica se as mensagens processadas são válidas (não apenas notificações de sistema)
                                        # Conta apenas mensagens de texto ou mídia, ignora e2e_notification
                                        valid_msgs = [m for m in processed_msgs if not m.get("body", "").startswith("[Notificação")]

                                        if not valid_msgs:
                                            print(f"[AI Pipeline]     ⚠️ WA ({name}): {len(msgs)} msgs recebidas, mas apenas notificações de sistema. Tentando busca por nome...")
                                            # Usa fallback por nome se só encontrou notificações
                                        elif not processed_msgs:
                                            print(f"[AI Pipeline]     ⚠️ WA ({name}): {len(msgs)} msgs recebidas, mas nenhuma processável.")
                                            return None
                                        else:
                                            for m in processed_msgs:
                                                try: m["date_human"] = datetime.fromtimestamp(m.get("timestamp", 0)).strftime("%d/%m/%Y %H:%M")
                                                except: pass
                                            return {"contact": name, "messages": processed_msgs}

                                # FALLBACK: Se não encontrou mensagens ou apenas notificações, tenta buscar por nome
                                print(f"[AI Pipeline]     🔍 Nenhuma mensagem válida por número para {name}, tentando busca por nome...")
                                # Busca todos os chats e filtra por nome no backend
                                all_chats_resp = await client.get(f"{wa_base}/chats")
                                print(f"[AI Pipeline]     📡 GET /chats → status={all_chats_resp.status_code}")
                                if all_chats_resp.status_code == 200:
                                    chats_json = all_chats_resp.json()
                                    # A API pode retornar {"chats": [...]} ou {"result": [...]} ou direto uma lista
                                    if isinstance(chats_json, list):
                                        all_chats = chats_json
                                    else:
                                        all_chats = (chats_json.get("chats")
                                                     or chats_json.get("result")
                                                     or chats_json.get("data")
                                                     or [])
                                    print(f"[AI Pipeline]     📋 Total de chats recebidos: {len(all_chats)}")
                                    if all_chats:
                                        # Mostra amostra dos primeiros chats para diagnóstico
                                        for c in all_chats[:3]:
                                            print(f"[AI Pipeline]       chat amostra: name={c.get('name')!r} id={c.get('id')!r}")
                                    # Filtra chats que contêm o nome do contato
                                    search_term = name.lower()
                                    def _chat_id_str(c) -> str:
                                        cid = c.get("id", "")
                                        if isinstance(cid, dict):
                                            return cid.get("_serialized", "") or cid.get("user", "")
                                        return str(cid) if cid else ""
                                    matching_chats = [c for c in all_chats if search_term in (c.get("name", "") or _chat_id_str(c)).lower()]
                                    print(f"[AI Pipeline]     🔎 Buscando '{search_term}' → {len(matching_chats)} chats encontrados")
                                    if matching_chats:
                                        best_chat = matching_chats[0]
                                        raw_id = best_chat.get("id")
                                        if isinstance(raw_id, dict):
                                            chat_id = raw_id.get("_serialized", "") or raw_id.get("user", "")
                                        else:
                                            chat_id = str(raw_id) if raw_id else ""
                                        print(f"[AI Pipeline]     ✅ Encontrado chat por nome: {best_chat.get('name')} (ID: {chat_id})")
                                        # Busca mensagens pelo chat_id
                                        msg_resp = await client.get(f"{wa_base}/chats/{chat_id}/messages?limit=50")
                                        print(f"[AI Pipeline]     📨 GET /chats/{chat_id}/messages → status={msg_resp.status_code}")
                                        if msg_resp.status_code == 200:
                                            all_msgs = msg_resp.json().get("messages", [])
                                            print(f"[AI Pipeline]     📩 Mensagens brutas recebidas: {len(all_msgs)}")
                                            if all_msgs:
                                                from datetime import datetime
                                                processed_msgs = []
                                                for m in all_msgs:
                                                    p = _preprocess_wa_message(m)
                                                    if p: processed_msgs.append(p)

                                                if processed_msgs:
                                                    for m in processed_msgs:
                                                        try: m["date_human"] = datetime.fromtimestamp(m.get("timestamp", 0)).strftime("%d/%m/%Y %H:%M")
                                                        except: pass
                                                    return {"contact": best_chat.get("name"), "messages": processed_msgs}
                                    else:
                                        print(f"[AI Pipeline]     ⚠️  Nenhum chat com '{search_term}' na lista de {len(all_chats)} chats")
                                else:
                                    print(f"[AI Pipeline]     ❌ /chats retornou erro: {all_chats_resp.text[:200]}")
                            except Exception as e_wa:
                                import traceback
                                print(f"[AI Pipeline]     ❌ Erro Crítico no WhatsApp ({name}):\n{traceback.format_exc()}")
                            return None

                        wa_results = await asyncio.gather(*(fetch_wa(n, p) for n, p in wa_tasks))
                        wa_history = [r for r in wa_results if r]
                        if wa_history:
                            internal_context["whatsapp_result"] = {"resultado": {"messages_by_contact": wa_history}}
                            # EMISSÃO VISUAL: WhatsApp Thread
                            for res in wa_history:
                                log_ev({
                                    "whatsapp_result": {
                                        "resultado": { "messages": res.get("messages", []) },
                                        "contact": { "name": res.get("contact"), "phone": res.get("phone") }
                                    }
                                }, type="data_found_whatsapp")

                # 2. Emails (Paralelizado)
                if "emails" in data_scope:
                    email_history = []
                    email_base = "http://localhost:8002/api/email"
                    email_tasks = []
                    for p in final_candidates[:5]:
                        email_list = p.get("email", [])
                        if isinstance(email_list, list):
                            for em_item in email_list:
                                email_addr = em_item.get("value")
                                if email_addr: 
                                    if not any(t[1] == email_addr for t in email_tasks):
                                        email_tasks.append((p.get("name"), email_addr))
                    
                    if email_tasks:
                        log_ev(f"Buscando Emails para {len(email_tasks)} contatos em paralelo...")
                        async def fetch_email(name, addr):
                            try:
                                # Aumentado para 60s para lidar com varreduras profundas no Outlook via COM (evita ReadTimeout)
                                e_res = await client.get(f"{email_base}/messages?folder=Conversations&limit=30&q={addr}", timeout=60.0)
                                if e_res.status_code == 200:
                                    all_e_msgs = e_res.json().get("messages", [])
                                    h_emails, a_emails = [], []
                                    noise = ["lusha", "webinar", "noreply", "no-reply", "notification", "system", "linkedin", "hunter.io", "zoominfo", "pipedrive.com"]
                                    for e_msg in all_e_msgs:
                                        from_addr, sub = e_msg.get("from", "").lower(), e_msg.get("subject", "").lower()
                                        if any(kw in from_addr or kw in sub for kw in noise): a_emails.append(e_msg)
                                        else:
                                            e_msg["body"] = sanitize_email_body(e_msg.get("body", ""))
                                            h_emails.append(e_msg)
                                    if h_emails or a_emails:
                                        return {"contact": name, "email": addr, "human_threads": h_emails, "automated_threads": a_emails}
                            except Exception as e_em:
                                import traceback
                                print(f"[AI Pipeline]     [ERROR] Erro Critico no Email ({name}):\n{traceback.format_exc()}")
                            return None

                        results = await asyncio.gather(*(fetch_email(n, a) for n, a in email_tasks))
                        email_history = [r for r in results if r]
                        if email_history:
                            internal_context["email_result"] = {"resultado": {"messages_by_contact": email_history}}
                            # EMISSÃO VISUAL: Email Threads
                            for res in email_history:
                                for thread in res.get("human_threads", [])[:3]:
                                    log_ev({
                                        "contact": {"name": res.get("contact"), "email": res.get("email")},
                                        "subject": thread.get("subject", "Sem Assunto"),
                                        "sent_message": thread.get("snippet") or thread.get("body"),
                                        "messages": [thread]
                                    }, type="data_found_email")
                                
    # --- CONSOLIDAÇÃO DE LINHA DO TEMPO (Cálculo de Silêncio Real) ---
    try:
        from datetime import datetime
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
            log_ev(f"Métrica consolidada: {delta_days} dias de silêncio.")
    except Exception as e_metric:
        print(f"[AI Pipeline] ⚠️ Erro ao calcular métricas de silêncio: {e_metric}")

    internal_context["selected_entities"] = selected_entities
    return internal_context


async def _fetch_tasks(intent_info: dict, internal_context: dict, pipedrive_org_id, message: str):
    """Busca tarefas/atividades do Pipedrive com filtros inteligentes."""
    import httpx
    from datetime import date, timedelta
    
    date_f = intent_info.get("activity_date_filter", "today")
    target_company = intent_info.get("extracted_company_name")
    filter_msg = f"para Empresa ID {pipedrive_org_id}" if pipedrive_org_id else (f"para '{target_company}'" if target_company else "Global")
    print(f"[AI Pipeline] 📅 Buscando tarefas ({date_f}) {filter_msg}...")
    
    try:
        from modules.crm.service.pipedrive_service import pipedrive_service
        
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
        # PRIORIDADE 1: Buscar a agenda do PRÓPRIO usuário (Sem limite de 500 escondendo as dele)
        r_agenda = await pipedrive_service.make_request("GET", f"activities?user_id={pipedrive_service.user_id}&done=0&limit=500")
        if r_agenda and r_agenda.status_code == 200:
            all_activities.extend(r_agenda.json().get("data") or [])
            print(f"[AI Pipeline] 📅 Agenda: Coletadas {len(all_activities)} tarefas diretas de João Luccas.")

        # PRIORIDADE 2: Buscar tarefas ligadas aos negócios da etapa (Se houver etapa)
        deals_in_stage = internal_context.get("deals_in_stage", [])
        if deals_in_stage:
            print(f"[AI Pipeline] 🔍 Otimizando busca: Coletando atividades globais para {len(deals_in_stage)} negócios da etapa...")
            # Em vez de fazer 100 requests (uma por deal), fazemos 1 request global e filtramos em memória.
            # Isso evita estouro de Rate Limit (429) do Pipedrive.
            r_global = await pipedrive_service.make_request("GET", f"activities?user_id=0&done=0&limit=500")
            if r_global and r_global.status_code == 200:
                global_activities = r_global.json().get("data") or []
                stage_deal_ids = {d["id"] for d in deals_in_stage}
                
                tasks_found = [a for a in global_activities if (a.get("deal_id").get("value") if isinstance(a.get("deal_id"), dict) else a.get("deal_id")) in stage_deal_ids]
                all_activities.extend(tasks_found)
                print(f"[AI Pipeline] 🎯 Filtro Global: Encontradas {len(tasks_found)} tarefas nos 500 itens mais recentes do Pipedrive.")
                
                # Se encontramos poucas tarefas e temos muitos negócios, talvez valha a pena buscar individualmente os top 5?
                # (Apenas como fallback de segurança para garantir que os principais deals tenham dados)
                if len(tasks_found) < 5 and len(deals_in_stage) > 0:
                    import asyncio
                    async def fetch_deal_acts(deal_id):
                        r = await pipedrive_service.make_request("GET", f"deals/{deal_id}/activities?done=0&limit=10")
                        return r.json().get("data") or [] if r and r.status_code == 200 else []
                    
                    print(f"[AI Pipeline] ⚠️ Poucas tarefas encontradas no global. Buscando individualmente para os top 10 deals da etapa...")
                    fallback_tasks = [fetch_deal_acts(d["id"]) for d in deals_in_stage[:10]]
                    fallback_results = await asyncio.gather(*fallback_tasks)
                    for res in fallback_results:
                        all_activities.extend(res)
            
        # PRIORIDADE 3: Busca por Organização (Se houver empresa específica)
        if pipedrive_org_id:
            r_org = await pipedrive_service.make_request("GET", f"organizations/{pipedrive_org_id}/activities?done=0")
            if r_org and r_org.status_code == 200:
                all_activities.extend(r_org.json().get("data") or [])
        
        # DEDUPLICAÇÃO: Evita duplicar tarefas que aparecem em múltiplas fontes
        if all_activities:
            seen_ids = set()
            unique_activities = []
            for act in all_activities:
                act_id = act.get("id")
                if act_id and act_id not in seen_ids:
                    seen_ids.add(act_id)
                    unique_activities.append(act)
            all_activities = unique_activities
            print(f"[AI Pipeline] 📅 Total de {len(all_activities)} tarefas únicas consolidadas.")

        # --- FILTRAGEM POR ORGANIZAÇÃO (Foco Contextual) ---
        if not is_global_request:
            if pipedrive_org_id:
                print(f"[AI Pipeline] 🛡️ Filtrando por Organização ID: {pipedrive_org_id}")
                all_activities = [
                    a for a in all_activities
                    if str(a.get("org_id").get("value") if isinstance(a.get("org_id"), dict) else a.get("org_id")) == str(pipedrive_org_id)
                ]
            elif target_company and target_company.lower() not in ["null", "none"]:
                print(f"[AI Pipeline] 🛡️ Filtrando por Nome da Organização: {target_company}")
                all_activities = [
                    a for a in all_activities
                    if target_company.lower() in str(a.get("org_name", "")).lower()
                ]
        
        tasks_to_return = []
        
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
                        tasks_to_return.append(act)
        
        internal_context["today_tasks"] = tasks_to_return
        
        filter_msg = f"({date_f})"
        if pipedrive_org_id:
            filter_msg += f" da empresa {pipedrive_org_id}"
        
        print(f"[AI Pipeline] Encontradas {len(tasks_to_return)} tarefas {filter_msg}.")

    except Exception as e_tasks:
        print(f"[AI Pipeline] [WARNING] Erro ao buscar tarefas: {e_tasks}")

    return internal_context
