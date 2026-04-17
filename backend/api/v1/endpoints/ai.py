from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, List, Any, Union
from services.external.groq_service import GroqService
from services.context_service import ContextService
from services.whatsapp_resolver import WhatsAppResolverService
from services.external.osint_service import osint_service
from core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import re
import json

router = APIRouter()

class CompanyInfo(BaseModel):
    id: Union[int, str]
    name: str

class MessageInput(BaseModel):
    role: str
    content: str

class ChatMessage(BaseModel):
    message: str
    orgId: Optional[Union[int, str]] = None
    selectedCompanies: Optional[List[CompanyInfo]] = None
    context: Optional[str] = "hierarchy_analysis"
    history: Optional[List[MessageInput]] = []

class ChatResponse(BaseModel):
    response: str
    ui_module: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    debug: Optional[Dict[str, Any]] = None

def _clean_response(text: str) -> str:
    """
    Remove markdown, code blocks e formata a resposta para exibição limpa.
    """
    if not text:
        return ""
    
    # Remove triple backticks de markdown (```json, ```python, ``` etc)
    text = re.sub(r'```[\w]*\n?', '', text)
    text = re.sub(r'```', '', text)
    
    # Remove backticks simples de código inline
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove markdown headers (#, ##, etc)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    
    # Remove bold markdown (**text**)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    
    # Remove italic markdown (*text* ou _text_)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    # Remove markdown links [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Limpa espaços em branco extras
    text = re.sub(r'\n\n+', '\n\n', text)
    text = text.strip()
    
    return text

def _format_context_for_prompt(context_dict: dict) -> str:
    """
    Formata contexto em texto legível, sem JSON.
    Inclui APENAS dados que estão disponíveis no dict.
    """
    if not context_dict:
        return ""
    
    lines = ["\n--- INÍCIO DOS DADOS INTERNOS MAPEADOS DO SISTEMA ---"]
    
    # Organização (sempre incluir)
    if "organization" in context_dict:
        org = context_dict["organization"]
        if org and isinstance(org, dict):
            if org.get('name'):
                lines.append(f"Empresa: {org.get('name')}")
            if org.get('cnpj'):
                lines.append(f"CNPJ: {org.get('cnpj')}")
            if org.get('domain'):
                lines.append(f"Site/Domínio: {org.get('domain')}")
            if org.get('industry'):
                lines.append(f"Indústria: {org.get('industry')}")
    
    # Decision Makers
    if "decision_makers" in context_dict:
        makers_data = context_dict.get("decision_makers")
        makers = makers_data if isinstance(makers_data, list) else makers_data.get("decision_makers", []) if isinstance(makers_data, dict) else []
        if makers:
            lines.append("\nTOMADORES DE DECISÃO MAPEADOS:")
            for maker in makers[:15]:
                if isinstance(maker, dict):
                    name = maker.get('name', 'Desconhecido')
                    role = maker.get('role', 'Cargo não informado')
                    dept = maker.get('department', 'Departamento não informado')
                    email = maker.get('email', '')
                    linkedin = maker.get('linkedin', '')
                    contact_info = f" | Email: {email}" if email else ""
                    if linkedin: contact_info += f" | LinkedIn: {linkedin}"
                    lines.append(f"- {name} ({role} de {dept}){contact_info}")
    
    # Employees by Department
    if "employees_by_dept" in context_dict:
        emps = context_dict["employees_by_dept"]
        if emps and isinstance(emps, dict) and emps.get("by_department"):
            lines.append("\nFUNCIONÁRIOS MAPEADOS:")
            for dept, emp_list in list(emps.get("by_department", {}).items())[:10]:
                lines.append(f"\nEm {dept}:")
                for emp in emp_list[:5]:
                    if isinstance(emp, dict):
                        email = emp.get('email', '')
                        linkedin = emp.get('linkedin', '')
                        contact_info = f" | Email: {email}" if email else ""
                        if linkedin: contact_info += f" | LinkedIn: {linkedin}"
                        lines.append(f"- {emp.get('name', 'Desconhecido')} ({emp.get('role', 'S/C')}){contact_info}")
    
    # Estatísticas
    if "statistics" in context_dict and ("decision_makers" in context_dict or "employees_by_dept" in context_dict):
        stats = context_dict["statistics"]
        if isinstance(stats, dict):
            total_emp = stats.get('total_employees', stats.get('total_employees_mapped', 0))
            if total_emp > 0:
                lines.append(f"\nTotal de funcionários guardados no banco de dados para esta empresa: {total_emp}")
    
    # Dados do Pipedrive (Deals, Notas, Atividades)
    if "pipedrive_details" in context_dict:
        pd = context_dict["pipedrive_details"]
        if "error" in pd:
            lines.append(f"\n[Atenção]: Não foi possível carregar dados do Pipedrive (Motivo: {pd['error']})")
        else:
            persons = pd.get("persons", [])
            if persons:
                lines.append("\nCONTATOS NO PIPEDRIVE (PERSONS):")
                for p in persons[:10]:
                    nome = p.get('name', '')
                    email = p.get('email', [{'value': ''}])[0].get('value', '') if isinstance(p.get('email'), list) and p.get('email') else ''
                    phone = p.get('phone', [{'value': ''}])[0].get('value', '') if isinstance(p.get('phone'), list) and p.get('phone') else ''
                    cargo = p.get('Title') or p.get('Job Title') or '' # Dependendo do custom field do PD pode variar
                    
                    contact_str = f"- {nome}"
                    if cargo: contact_str += f" ({cargo})"
                    if email: contact_str += f" | Email: {email}"
                    if phone: contact_str += f" | Telefone: {phone}"
                    lines.append(contact_str)
                    
            deals = pd.get("deals", [])
            lines.append("\nNEGÓCIOS (DEALS) NO PIPEDRIVE:")
            if deals:
                for d in deals:
                    status_pt = {"open": "Aberto", "won": "Ganho", "lost": "Perdido"}.get(d.get("status"), d.get("status"))
                    lines.append(f"- [{status_pt}] {d.get('title')} (Valor: {d.get('value')} {d.get('currency')})")
            else:
                lines.append("- Nenhum negócio encontrado.")
                
            activities = pd.get("activities", [])
            lines.append("\nATIVIDADES RECENTES:")
            if activities:
                for a in activities[:5]:
                    lines.append(f"- {a.get('subject')} [{a.get('type')}] - Data: {a.get('due_date')} - Feito: {'Sim' if a.get('done') else 'Não'}")
            else:
                lines.append("- Nenhuma atividade encontrada.")
                
            notes = pd.get("notes", [])
            if notes:
                lines.append("\nANOTAÇÕES:")
                for n in notes[:3]:
                    clean_note = _clean_response(n.get('content', ''))
                    lines.append(f"- {clean_note}")
    
    # Tarefas (Agenda)
    if "today_tasks" in context_dict:
        tasks = context_dict["today_tasks"]
        lines.append("\nTAREFAS/ATIVIDADES AGENDADAS NO PIPEDRIVE:")
        if tasks:
            for t in tasks:
                empresa = f" | Empresa: {t.get('org_name')}" if t.get('org_name') else ""
                negocio = f" | Negócio: {t.get('deal_title')}" if t.get('deal_title') else ""
                vencimento = f" | Vencimento: {t.get('due_date')}" if t.get('due_date') else ""
                lines.append(f"- ID:{t.get('id')} | [{t.get('type', 'tarefa')}] {t.get('subject')}{empresa}{negocio}{vencimento}")
        else:
            lines.append("- Nenhuma tarefa encontrada.")
                    
    # Dados de Retorno do WhatsApp (Se for Ação WhatsApp)
    if "whatsapp_result" in context_dict:
        wa = context_dict["whatsapp_result"]
        lines.append("\n==================================")
        lines.append("HISTÓRICO DE CONVERSA DO WHATSAPP:")
        
        if "error" in wa:
            err_msg = wa['error']
            lines.append(f"Atenção: A ação de WhatsApp não pôde ser concluída. Motivo: {err_msg}")
            # ... (rest of error handling)
        elif wa.get("status") and wa.get("status") >= 400:
            res_data = wa.get("resultado", {})
            detail = res_data.get("detail") or res_data.get("message") or "Erro desconhecido"
            lines.append(f"Atenção: A ação de WhatsApp falhou com status {wa.get('status')}. Detalhe: {detail}")
        else:
            result_data = wa.get('resultado', {})
            messages = result_data.get('messages', [])
            
            if messages:
                for m in messages:
                    sender = "Eu" if m.get("fromMe") else "Contato"
                    body = m.get("body", "(Sem conteúdo de texto)")
                    # Formata timestamp se existir
                    import datetime
                    ts = m.get("timestamp")
                    time_str = ""
                    if ts:
                        time_str = f" [{datetime.datetime.fromtimestamp(ts).strftime('%d/%m %H:%M')}]"
                    
                    lines.append(f"{sender}{time_str}: {body}")
            else:
                res_str = str(result_data)
                if "messages" in res_str and "[]" in res_str:
                    lines.append("Nenhuma mensagem encontrada nesta conversa específica.")
                else:
                    lines.append(f"Dados brutos retornados: {res_str[:500]}")
        lines.append("==================================")
    
    # Dados de Enriquecimento OSINT (Toolkit de Descoberta)
    if "osint_result" in context_dict:
        os_data = context_dict["osint_result"]
        lines.append("\n--- DADOS DE ENRIQUECIMENTO EXTERNO (OSINT) ---")
        lines.append(f"Lead: {os_data.get('lead')}")
        lines.append(f"Empresa: {os_data.get('empresa')}")
        
        wa_info = os_data.get("whatsapp", {})
        if wa_info.get("isMobile"):
            lines.append(f"WHATSAPP ENCONTRADO: {wa_info.get('numero')}")
            lines.append(f"LINK WHATSAPP: {wa_info.get('waLink')}")
        else:
            lines.append(f"Telefone Oficial Sede: {os_data.get('contatosSede')}")
            
        lines.append(f"E-mail Corporativo Provável: {os_data.get('emailProvavel')}")
        
        dorks = os_data.get("estrategiaDorks", [])
        if dorks:
            lines.append("Links de Pesquisa:")
            for d in dorks[:3]:
                lines.append(f"- {d.get('objetivo')}: {d.get('link')}")
        lines.append("-----------------------------------------------")
    
    # Dados de Email (Outlook / SMTP)
    if "email_result" in context_dict:
        em = context_dict["email_result"]
        lines.append("\n==================================")
        lines.append("DADOS DO EMAIL (MICROSOFT OUTLOOK / SMTP):")
        
        if "error" in em:
            lines.append(f"Atenção: A ação de e-mail falhou. Motivo: {em['error']}")
        elif em.get("status") and em.get("status") >= 400:
            res_data = em.get("resultado", {})
            detail = res_data.get("detail", "Erro desconhecido")
            lines.append(f"Atenção: A ação de e-mail falhou com status {em.get('status')}. Detalhe: {detail}")
        else:
            action = em.get("email_action")
            if action == "list_folders":
                lines.append("\nPASTAS ENCONTRADAS:")
                for f in em.get("folders", []):
                    lines.append(f"- {f}")
            elif action == "get_messages" or action == "get_unread":
                lines.append(f"\nMENSAGENS NA PASTA '{em.get('folder', 'Inbox')}':")
                for m in em.get("messages", []):
                    sender = m.get("sender") or "Desconhecido"
                    subject = m.get("subject") or "(Sem assunto)"
                    date = m.get("date") or ""
                    body = m.get("body", "")[:200]
                    lines.append(f"- De: {sender} | Assunto: {subject} | Data: {date}")
                    lines.append(f"  Snippet: {body}...")
            elif action == "send_email":
                lines.append(f"Email enviado com sucesso para {em.get('to')}!")
        lines.append("==================================")

    if len(lines) == 1:
        return ""
        
    lines.append("--- FIM DOS DADOS INTERNOS MAPEADOS ---")
    return "\n".join(lines)


async def _classify_user_intent_with_llm(message: str, history: Optional[List[MessageInput]] = None) -> dict:
    """
    Estágio 1 da arquitetura de Pipeline: 
    Usa a IA para classificar a intenção, os parâmetros da busca e o ESCOPO GRANULAR de dados
    antes de dar a resposta. O data_scope define quais fatias de dados buscar.
    """
    from services.external.base_gemini_service import ask_gemini
    
    history_str = ""
    if history and len(history) > 0:
        history_lines = []
        # Pega as últimas 6 mensagens de contexto para capturar referências a nomes
        for msg in history[-6:]:
            role_br = "Usuário" if msg.role == "user" else "Assistente"
            history_lines.append(f"{role_br}: {msg.content}")
        history_str = "Histórico Recente da Conversa:\n" + "\n".join(history_lines)
    
    prompt = f"""Você é o Roteador de Intenções de um sistema corporativo B2B integrado ao Pipedrive e WhatsApp.
Sua função é analisar o comando do usuário e determinar a intenção e extrair entidades, considerando o histórico para resolver pronomes ou referências vagas.

{history_str}

Mensagem atual do usuário: "{message}"

REGRAS DE RESOLUÇÃO DE CONTEXTO:
1. Se o usuário diz "dela", "dele", "com ele", "a conversa", olhe no HISTÓRICO acima para ver qual pessoa ou empresa foi mencionada por último.
2. Se o usuário perguntou "o que tem na conversa dela?" e o histórico menciona "Momo", você deve extrair "Momo" como extracted_person_name e definir query_type como "whatsapp" e whatsapp_action como "get_messages".

Categorias (query_type):
- "contacts": O usuário focou em PESSOAS (funcionários, diretoria, equipe, contatos, "quem trabalha lá")
- "company_info": O usuário focou na EMPRESA (o que faz, cnpj, site, resumo)
- "pipedrive_info": O usuário focou em VENDAS/CRM (prospecção, deals, atividades, anotações, funil)
- "pipedrive_tasks": O usuário quer saber das TAREFAS/ATIVIDADES pendentes (o que fazer hoje, tarefas de uma empresa, agenda geral, próximos passos)
- "whatsapp": O usuário quer interagir com o WHATSAPP (enviar mensagem, ler histórico, buscar chats)
- "email": O usuário quer interagir com o EMAIL (enviar email, ler emails, ver pastas, buscar mensagens do Outlook)
- "enrichment": O usuário quer ENCONTRAR O CONTATO, WHATSAPP ou EMAIL de uma pessoa ("fala com ela", "encontre o zap", "pesquise os dados dela", "fale com o fulano")
- "general": Conversa fiada ou assuntos que não encaixam

AÇÕES WHATSAPP (whatsapp_action):
- "send_message": Enviar uma nova mensagem
- "get_chats": Listar conversas recentes
- "get_messages": Ler histórico de mensagens de um chat/contato
- "search_contacts": Buscar um contato específico

AÇÕES EMAIL (email_action):
- "send_email": Enviar um novo e-mail
- "get_unread": Buscar e-mails não lidos
- "get_messages": Listar mensagens de uma pasta específica
- "list_folders": Listar pastas da conta

Retorne APENAS um JSON válido neste formato (sem backticks):
{{
    "query_type": "contacts" | "company_info" | "pipedrive_info" | "pipedrive_tasks" | "whatsapp" | "email" | "enrichment" | "general",
    "data_scope": ["employees", "deals", "activities", "today_tasks", "emails", ...],
    "activity_done_filter": 0 | 1 | null, 
    "activity_date_filter": "today" | "tomorrow" | "overdue" | "future" | "all" | null,
    "extracted_company_name": "Nome da empresa identificado ou inferido ou null",
    "extracted_person_name": "Nome da pessoa identificado ou inferido ou null",
    "extracted_person_hint": "Dica sobre a pessoa ou null",
    "whatsapp_action": "send_message" | "get_chats" | "get_messages" | "search_contacts" | null,
    "whatsapp_message": "Mensagem para enviar ou null",
    "whatsapp_chat_id": "ID do chat ou null",
    "email_action": "send_email" | "get_unread" | "get_messages" | "list_folders" | null,
    "email_to": "Email do destinatário ou null",
    "email_subject": "Assunto do e-mail ou null",
    "email_body": "Corpo do e-mail ou null",
    "email_folder": "Pasta (ex: Inbox, Sent, Leads) ou null"
}}

REGRAS PARA activity_done_filter:
- Use 0 para "a fazer", "pendentes", "próximas", "agendadas". (Padrão)
- Use 1 para "concluídas", "feitas", "realizadas", "histórico de tarefas".
- Use null para "todas", "tudo o que foi feito e o que falta", "completo".

REGRAS PARA activity_date_filter:
- "today": apenas de hoje.
- "tomorrow": apenas de amanhã.
- "overdue": apenas as atrasadas.
- "future": próximas tarefas (hoje e futuro).
- "all": sem filtro de data (todo o histórico).
"""
    try:
        response = await ask_gemini(prompt, json_mode=True)
        
        def _extract_intent(data: dict) -> dict:
            """Extrai e normaliza o intent de um dict."""
            raw_scope = data.get("data_scope", [])
            # Garante que data_scope é sempre uma lista válida
            if not isinstance(raw_scope, list):
                raw_scope = []
            valid_scopes = {"employees", "decision_makers", "persons", "deals", "activities", "notes", "today_tasks"}
            data_scope = [s for s in raw_scope if s in valid_scopes]
            
            # Normalização do filtro de atividades
            done_filter = data.get("activity_done_filter")
            if done_filter not in [0, 1, None]:
                done_filter = 0 # Default para segurança/produtividade
            
            # Normalização do filtro de data
            date_filter = data.get("activity_date_filter") or "today"
            if date_filter not in ["today", "tomorrow", "overdue", "future", "all"]:
                date_filter = "today"
            
            return {
                "query_type": data.get("query_type", "general"),
                "data_scope": data_scope,
                "activity_done_filter": done_filter,
                "activity_date_filter": date_filter,
                "extracted_company_name": data.get("extracted_company_name"),
                "extracted_person_name": data.get("extracted_person_name"),
                "extracted_person_hint": data.get("extracted_person_hint"),
                "whatsapp_action": data.get("whatsapp_action"),
                "whatsapp_number": data.get("whatsapp_number"),
                "whatsapp_message": data.get("whatsapp_message"),
                "whatsapp_chat_id": data.get("whatsapp_chat_id"),
                "email_action": data.get("email_action"),
                "email_to": data.get("email_to"),
                "email_subject": data.get("email_subject"),
                "email_body": data.get("email_body"),
                "email_folder": data.get("email_folder")
            }
        
        if isinstance(response, dict):
            return _extract_intent(response)
        elif isinstance(response, str):
            try:
                parsed = json.loads(response)
                return _extract_intent(parsed)
            except:
                pass
    except Exception as e:
        print(f"[AI Pipeline] Erro na classificação de intenção via Gemini: {e}")
        
    return {"query_type": "general", "data_scope": [], "activity_done_filter": 0, "extracted_company_name": None, "whatsapp_action": None, "whatsapp_number": None, "whatsapp_message": None, "whatsapp_chat_id": None}

@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    payload: ChatMessage,
    session: AsyncSession = Depends(get_db)
):
    """
    Endpoint para chat com IA usando Gemini com RAG (Retrieval Augmented Generation).
    Arquitetura de Pipeline LLM em dois estágios:
    1. Classificação de Intenção (Qual o contexto necessário?)
    2. Geração da Resposta (Com base nos dados precisos fornecidos)
    """
    try:
        if not payload.message or not payload.message.strip():
            raise HTTPException(status_code=400, detail="Mensagem vazia")
            
        import os
        from services.external.base_gemini_service import ask_gemini
        
        # --- ESTÁGIO 1: Classificação de Intenção (Pipeline Routing) ---
        print(f"[AI Pipeline] Estágio 1 - Analisando intenção do usuário com histórico de {len(payload.history or [])} mensagens...")
        intent_info = await _classify_user_intent_with_llm(payload.message, payload.history)
        query_type = intent_info.get("query_type", "general")
        extracted_name = intent_info.get("extracted_company_name")
        print(f"[AI Pipeline] Intenção detectada: {query_type}")
        
        # --- AÇÃO WHATSAPP (Se for detectado query_type="whatsapp") ---
        whatsapp_result_context = None
        if query_type == "whatsapp":
            action = intent_info.get("whatsapp_action")
            print(f"[AI Chat] Executando Ação WhatsApp Automática: {action}")
            
            try:
                import httpx
                wa_base = "http://localhost:8001/api/whatsapp"
                async with httpx.AsyncClient(timeout=20.0) as client:
                    
                    # RESOLUÇÃO INTELIGENTE DE CONTATO
                    chat_id = intent_info.get("whatsapp_chat_id")
                    target_number = intent_info.get("whatsapp_number")
                    
                    # Se não tem ID nem número, mas tem dicas de nome/empresa/hint -> RESOLVER
                    if not chat_id and not target_number and (intent_info.get("extracted_company_name") or intent_info.get("extracted_person_name") or intent_info.get("extracted_person_hint")):
                        print(f"[AI Chat] Tentando resolução inteligente de contato...")
                        resolution = await WhatsAppResolverService.resolve_contact(
                            session,
                            company_name=intent_info.get("extracted_company_name"),
                            person_name=intent_info.get("extracted_person_name"),
                            person_hint=intent_info.get("extracted_person_hint")
                        )
                        if resolution.get("success"):
                            chat_id = resolution.get("chat_id")
                            best_match = resolution.get("best_match", {})
                            chat_id = resolution.get("chat_id")
                            print(f"[AI Chat] Contato resolvido: {best_match.get('name')} ({chat_id})")
                            
                            # Tentar buscar Foto Real do WhatsApp (prioridade)
                            wa_picture = None
                            try:
                                clean_num = chat_id.split('@')[0]
                                if not clean_num.startswith('55') and len(clean_num) >= 10:
                                    clean_num = f"55{clean_num}"
                                    
                                async with httpx.AsyncClient(timeout=3.0) as wa_pic_client:
                                    wa_pic_url = f"http://localhost:8001/api/whatsapp/contacts/by-number/{clean_num}/profile-pic"
                                    wa_resp = await wa_pic_client.get(wa_pic_url)
                                    if wa_resp.status_code == 200:
                                        wa_picture = wa_resp.json().get("profilePicUrl")
                                        print(f"[WA Pic] Foto real encontrada: {wa_picture[:50]}...")
                            except Exception as wa_pic_err:
                                print(f"[WA Pic] Erro ao buscar foto real: {wa_pic_err}")

                            # DETECÇÃO DE AMBIGUIDADE
                            all_matches = resolution.get("all_matches", [])
                            is_ambiguous = False
                            if len(all_matches) > 1:
                                # Se o segundo match tem confiança muito próxima do primeiro
                                if all_matches[0]["confidence"] - all_matches[1]["confidence"] < 10:
                                    is_ambiguous = True
                            
                            if is_ambiguous:
                                print(f"[AI Chat] ⚠️ Ambiguidade detectada: {len(all_matches)} contatos similares.")
                                whatsapp_result_context = {
                                    "error": "AMBIGUOUS_CONTACT",
                                    "status": 400,
                                    "matches": all_matches[:3],
                                    "extracted_name": intent_info.get("extracted_person_name")
                                }
                                # Forçamos chat_id para None para não tentar o envio às cegas
                                chat_id = None
                            else:
                                whatsapp_result_context = {
                                    "whatsapp_action": action,
                                    "resolved_contact": best_match,
                                    "contact_picture": wa_picture or best_match.get("profilePicture") or best_match.get("picture_url")
                                }
                    
                    if action == "send_message":
                        # Se já temos um chat_id (ID completo com @c.us ou @lid), usamos ele integralmente
                        # para evitar que o Node.js service tente reformatar erroneamente.
                        if chat_id and ("@" in str(chat_id)):
                            number_to_send = chat_id
                            number_str = chat_id
                        else:
                            number_to_send = target_number or (chat_id.split('@')[0] if chat_id else None)
                            number_str = str(number_to_send).strip().replace("+", "").replace(" ", "").replace("-", "")
                            if len(number_str) <= 11 and not number_str.startswith("55"):
                                number_str = f"55{number_str}"
                        
                        if number_to_send:
                            msg_text = intent_info.get("whatsapp_message")
                            if msg_text and len(msg_text.strip()) > 0:
                                resp = await client.post(f"{wa_base}/send", json={"number": number_str, "message": msg_text})
                                res_data = resp.json()
                                # Prepara dados para o preview no front
                                send_ctx = {
                                    "whatsapp_action": action, 
                                    "status": resp.status_code, 
                                    "resultado": res_data,
                                    "sent_message": msg_text,
                                    "contact": whatsapp_result_context.get("resolved_contact") if whatsapp_result_context else {"id": number_str, "name": intent_info.get("extracted_person_name") or "Contato"}
                                }
                                if whatsapp_result_context:
                                    whatsapp_result_context.update(send_ctx)
                                else:
                                    whatsapp_result_context = send_ctx
                                print(f"[AI Chat] ✅ Mensagem enviada para {number_str}")
                            else:
                                print(f"[AI Chat] ⚠️ Mensagem vazia. Solicitando conteúdo ao usuário.")
                                whatsapp_result_context = {
                                    "error": "MISSING_MESSAGE_BODY", 
                                    "contact_name": intent_info.get("extracted_person_name") or "o contato",
                                    "target_number": number_str
                                }
                        elif not whatsapp_result_context or "error" not in whatsapp_result_context:
                            # Só entra aqui se NÃO houve erro prévio (como AMBIGUIDADE)
                            print(f"[AI Chat] ❌ Falha: número não identificado para '{intent_info.get('extracted_person_name')}'")
                            whatsapp_result_context = {
                                "error": "CONTACT_NOT_FOUND", 
                                "contact_name": intent_info.get("extracted_person_name") or "o contato",
                                "whatsapp_action": action
                            }
                            
                    elif action == "get_chats":
                        resp = await client.get(f"{wa_base}/chats")
                        whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": resp.json()}
                        
                    elif action == "get_messages":
                        # PRIORIDADE 1: Se já temos um chat_id resolvido (ID formatado como @c.us ou @lid), usa ele direto
                        resolved_chat_id = chat_id
                        if not resolved_chat_id and whatsapp_result_context and "resolved_contact" in whatsapp_result_context:
                            rc = whatsapp_result_context["resolved_contact"]
                            # Se o ID já vem com o sufixo do WhatsApp, é o caminho mais seguro
                            resolved_chat_id = rc.get("id") or rc.get("id", {}).get("_serialized")
                        
                        if resolved_chat_id and ("@" in str(resolved_chat_id)):
                            print(f"[AI Chat] Buscando mensagens pelo ID Resolvido: {resolved_chat_id}")
                            resp = await client.get(f"{wa_base}/chats/{resolved_chat_id}/messages?limit=30")
                            res_data = resp.json()
                            if whatsapp_result_context:
                                whatsapp_result_context.update({"whatsapp_action": action, "status": resp.status_code, "resultado": res_data})
                            else:
                                whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": res_data}
                        
                        # PRIORIDADE 2: Se temos um número de telefone puro
                        else:
                            target_number = intent_info.get("whatsapp_number")
                            if not target_number and whatsapp_result_context and "resolved_contact" in whatsapp_result_context:
                                rc = whatsapp_result_context["resolved_contact"]
                                target_number = rc.get("number") or rc.get("phone")
                            
                            if target_number:
                                # Limpa o número
                                num_str = str(target_number).split('@')[0].replace("+", "").replace(" ", "").replace("-", "")
                                print(f"[AI Chat] Buscando mensagens pelo número de telefone: {num_str}")
                                resp = await client.get(f"{wa_base}/chats/by-number/{num_str}/messages?limit=30")
                                res_data = resp.json()
                                if whatsapp_result_context:
                                    whatsapp_result_context.update({"whatsapp_action": action, "status": resp.status_code, "resultado": res_data})
                                else:
                                    whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": res_data}
                            elif chat_id:
                                # Fallback para qualquer chat_id que sobrou
                                resp = await client.get(f"{wa_base}/chats/{chat_id}/messages?limit=30")
                                res_data = resp.json()
                                if whatsapp_result_context:
                                    whatsapp_result_context.update({"whatsapp_action": action, "status": resp.status_code, "resultado": res_data})
                                else:
                                    whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": res_data}
                            else:
                                whatsapp_result_context = {"error": "Não consegui identificar de qual conversa você está falando."}
                            
                    elif action == "search_contacts":
                        search_name = intent_info.get("extracted_person_name") or intent_info.get("extracted_company_name")
                        if search_name:
                            resp = await client.get(f"{wa_base}/contacts/search?name={search_name}")
                        else:
                            resp = await client.get(f"{wa_base}/contacts/all")
                        whatsapp_result_context = {"whatsapp_action": action, "status": resp.status_code, "resultado": resp.json()}
                    else:
                        whatsapp_result_context = {"error": f"Ação {action} desconhecida"}
            except Exception as e:
                print(f"[AI Chat] Erro ao conectar com WhatsApp Service: {e}")
                whatsapp_result_context = {"error": f"WhatsApp Service offline ou erro de conexão: {str(e)}"}
        
        # --- AÇÃO EMAIL (Se for detectado query_type="email") ---
        email_result_context = None
        if query_type == "email":
            action = intent_info.get("email_action")
            print(f"[AI Chat] Executando Ação Email Automática: {action}")
            
            try:
                import httpx
                email_base = "http://localhost:8002/api/email"
                async with httpx.AsyncClient(timeout=30.0) as client_http:
                    
                    if action == "send_email":
                        to = intent_info.get("email_to")
                        subject = intent_info.get("email_subject") or "Mensagem de Contato"
                        body = intent_info.get("email_body")
                        
                        # Resolução de email se não houver destinatário
                        if not to and (intent_info.get("extracted_person_name") or intent_info.get("extracted_company_name")):
                             # Aqui poderíamos chamar um resolvedor similar ao de WhatsApp
                             # Mas por simplificação agora, vamos assumir que o sistema tenta encontrar no banco
                             pass

                        if to and body:
                            resp = await client_http.post(f"{email_base}/send", json={
                                "to": to, "subject": subject, "body": body
                            })
                            email_result_context = {
                                "email_action": action, 
                                "status": resp.status_code, 
                                "to": to, 
                                "subject": subject,
                                "sent_message": body,
                                "contact": {"email": to, "name": intent_info.get("extracted_person_name") or to},
                                "resultado": resp.json()
                            }
                        else:
                            email_result_context = {"error": "Destinatário ou corpo do email ausente.", "email_action": action}
                    
                    elif action == "list_folders":
                        resp = await client_http.get(f"{email_base}/folders")
                        email_result_context = {"email_action": action, "status": resp.status_code, "folders": resp.json().get("folders", [])}
                        
                    elif action == "get_messages":
                        folder = intent_info.get("email_folder") or "Inbox"
                        resp = await client_http.get(f"{email_base}/messages?folder={folder}&limit=10")
                        email_result_context = {"email_action": action, "status": resp.status_code, "folder": folder, "messages": resp.json().get("messages", [])}
                        
                    elif action == "get_unread":
                        folder = intent_info.get("email_folder") or "Inbox"
                        resp = await client_http.get(f"{email_base}/unread?folder={folder}&limit=10")
                        email_result_context = {"email_action": action, "status": resp.status_code, "folder": folder, "messages": resp.json().get("messages", [])}

            except Exception as e:
                print(f"[AI Chat] Erro ao conectar com Email Service: {e}")
                email_result_context = {"error": f"Email Service offline: {str(e)}"}
        
        # --- BUSCA E RESOLUÇÃO DE ORGANIZAÇÃO ---
        org_id = payload.orgId
        extracted_name = intent_info.get("extracted_company_name")
        
        # Se temos uma empresa explícita na UI, usamos ela
        if payload.selectedCompanies and len(payload.selectedCompanies) > 0:
            org_id = payload.selectedCompanies[0].id
            print(f"[AI Chat] Usando empresa da UI: {payload.selectedCompanies[0].name} (ID: {org_id})")
        # Se não temos orgId das props UI, mas a IA extraiu do texto e não havia orgId
        elif not org_id and extracted_name:
            print(f"[AI Chat] Buscando empresa inferida pela IA: {extracted_name}")
            org_data_resolved = await ContextService.fetch_organization_by_name(session, extracted_name)
            if org_data_resolved:
                org_id = org_data_resolved.id
                
        # Se ainda não temos org_id, tentamos último recurso (Regex antigo)
        if not org_id:
            org_name_regex = await ContextService.extract_organization_name(payload.message)
            if org_name_regex:
                org_data_regex = await ContextService.fetch_organization_by_name(session, org_name_regex)
                if org_data_regex:
                    org_id = org_data_regex.id

        # Agora buscamos as informações precisas dependendo da intenção classificada
        internal_context = {}
        
        # --- AÇÃO DE ENRIQUECIMENTO OSINT ---
        osint_context = None
        if query_type == "enrichment":
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
                        from sqlalchemy import select
                        from models.employee import Employee
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
                        
                else:
                    osint_context = {"error": osint_data.get("error", "Falha na pesquisa externa.")}
            else:
                osint_context = {"error": "Não consegui identificar o nome da pessoa ou da empresa para pesquisar."}

        if osint_context:
            internal_context.update(osint_context)

        # --- BUSCA DE DADOS CONTEXTUAIS ---
        
        # Agora buscamos as informações precisas dependendo da intenção classificada
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
        if "today_tasks" in data_scope:
            filter_msg = f"para Empresa ID {pipedrive_org_id}" if pipedrive_org_id else "Global"
            print(f"[AI Pipeline] 📅 Buscando tarefas de hoje ({filter_msg})...")
            try:
                from services.pipedrive.pipedrive_service import pipedrive_service
                from datetime import date, timedelta
                import httpx
                
                today = date.today().isoformat()
                
                # Detecção de Escopo: Padrão é sempre o usuário logado (Eu).
                # Só abre visão global se houver um comando explícito de gestão/equipe.
                global_triggers = [
                    "todo o pipedrive", "da equipe", "do time", "geral da empresa", 
                    "de todos os usuários", "dos vendedores", "empresa inteira",
                    "visão global", "visão geral"
                ]
                msg_lower = payload.message.lower()
                is_global_request = any(trigger in msg_lower for trigger in global_triggers)
                
                # REFORÇO: Se o usuário escreveu "meu", "minha", "pra mim", "comigo", força o filtro de usuário
                has_my_filter = any(me in msg_lower for me in ["meu", "minha", "pra mim", "comigo", "meus", "minhas"])
                if has_my_filter:
                    is_global_request = False
                
                # Filtro de status de atividade (detectado pela IA no Estágio 1)
                done_filter = intent_info.get("activity_done_filter")
                params = [f"api_token={pipedrive_service.api_token}"]
                
                if not is_global_request:
                    params.append(f"user_id={pipedrive_service.user_id}")
                if done_filter is not None:
                    params.append(f"done={done_filter}")
                
                query_string = "&".join(params)

                # 1. Se temos empresa específica, usamos o endpoint de ORGANIZATIONS 
                if pipedrive_org_id:
                    url_fetch = f"{pipedrive_service.base_url}/organizations/{pipedrive_org_id}/activities?{query_string}"
                # 2. Caso contrário, buscador global (Agenda)
                else:
                    url_fetch = f"{pipedrive_service.base_url}/activities?{query_string}"
                
                async with httpx.AsyncClient() as pd_client:
                    resp = await pd_client.get(url_fetch)
                    data = resp.json()
                    if data and data.get("success"):
                        all_activities = data.get("data") or []
                        
                        # 3. Filtragem Manual de Segurança (Python-side) e Filtro de Negócios Perdidos
                        if not is_global_request:
                            all_activities = [
                                act for act in all_activities 
                                if str(act.get("user_id")) == str(pipedrive_service.user_id) or 
                                   str(act.get("assigned_to_user_id")) == str(pipedrive_service.user_id)
                            ]

                        # --- FILTRAGEM DE NEGÓCIOS PERDIDOS ---
                        # Buscamos os IDs de negócios que NÃO estão perdidos (open ou won)
                        try:
                            # Coletar IDs de deals presentes nas atividades
                            deal_ids_in_tasks = {act.get("deal_id") for act in all_activities if act.get("deal_id")}
                            
                            if deal_ids_in_tasks:
                                # Busca deals abertos e ganhos para o usuário (ou geral se global)
                                deals_status_filter = f"&user_id={pipedrive_service.user_id}" if not is_global_request else ""
                                
                                # Para ser mais robusto e performático: buscamos apenas os deals que estão nas atividades
                                # mas o Pipedrive API não permite filtro por lista de IDs facilmente em um GET.
                                # Vamos buscar todos os deals não-perdidos e cruzar.
                                
                                # Decidimos buscar os "open" e "won" deals.
                                valid_deal_ids = set()
                                for status in ["open", "won"]:
                                    d_url = f"{pipedrive_service.base_url}/deals?status={status}{deals_status_filter}&limit=500&api_token={pipedrive_service.api_token}"
                                    d_resp = await pd_client.get(d_url)
                                    d_data = d_resp.json()
                                    if d_data.get("success") and d_data.get("data"):
                                        for d in d_data["data"]:
                                            valid_deal_ids.add(d["id"])
                                
                                # Filtra: Mantém tarefas sem deal_id OU tarefas com deal_id que esteja no set de válidos
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
                            # Em caso de erro no filtro, mantemos a lista original para não quebrar a UI
                        
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
                                internal_context["pipedrive_details"] = filtered_pd
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
                
            except Exception as e:
                print(f"[AI Chat] Erro ao buscar contexto: {e}")
                internal_context = {}
        
        # Injeta resultado do WhatsApp no contexto mesmo se não tiver org_id
        if whatsapp_result_context:
            internal_context["whatsapp_result"] = whatsapp_result_context
            
        if email_result_context:
            internal_context["email_result"] = email_result_context
            
        print(f"[AI Pipeline] Estágio 2 - Alimentando o modelo final com dados da query do tipo: {query_type} | scopes: {data_scope}...")
        
        # ==========================================
        # 🔥 OTIMIZAÇÃO: BYPASS PARA TAREFAS E CONTATOS
        # Se a intenção é tarefas ou contatos, não precisamos da IA para resumir.
        # Entregamos os dados brutos imediatamente para o front com mapeamento de labels.
        # ==========================================
        query_t = intent_info.get("query_type")
        if query_t in ["pipedrive_tasks", "contacts"]:
            org_name = internal_context.get("organization", {}).get("name")
            
            if query_t == "pipedrive_tasks":
                target_text = f" da {org_name}" if org_name else " agendadas"
                response_msg = f"Aqui estão as tarefas{target_text} no Pipedrive:"
                u_mod = "TaskList"
            else:
                target_text = f" da {org_name}" if org_name else ""
                stats = internal_context.get("statistics", {})
                count = stats.get("total_employees_mapped") or stats.get("total_employees") or 0
                
                # PREPARAÇÃO DE DADOS PARA CONTACTGRID (ACHATAR LISTA E MAPEAR SENIORIDADE)
                all_persons = []
                if "decision_makers" in internal_context:
                    dm_data = internal_context["decision_makers"]
                    dms = dm_data if isinstance(dm_data, list) else dm_data.get("decision_makers", [])
                    all_persons.extend(dms)
                
                if "employees_by_dept" in internal_context:
                    by_dept = internal_context["employees_by_dept"].get("by_department", {})
                    for dept_name, emps in by_dept.items():
                        for e in emps:
                            if isinstance(e, dict):
                                e["department"] = dept_name
                                # Mapeamento de Senioridade Fixa para evitar erro de nível 5 em todos
                                s_val = e.get("seniority", 3)
                                try: s_num = int(s_val)
                                except: s_num = 3
                                
                                labels = {
                                    6: ("Board / Sócio", "Tier 6"),
                                    5: ("Director / Regional Head", "Tier 5"),
                                    4: ("Manager / Head", "Tier 4"),
                                    3: ("Especialista / Senior", "Tier 3"),
                                    2: ("Analista / Operacional", "Tier 2"),
                                    1: ("Junior / Estagiário", "Tier 1")
                                }
                                label_text, tier_text = labels.get(s_num, ("Profissional", "Tier 3"))
                                e["seniority_label"] = label_text
                                e["tier"] = tier_text
                        all_persons.extend(emps)
                
                # Injeta a lista flat no contexto para o front-end
                # FILTRAGEM: Remove Sócios (Tier 6) e a própria Empresa (Tier 0)
                filtered_list = []
                for p in all_persons:
                    if not isinstance(p, dict): continue
                    
                    role = str(p.get("role", "")).lower()
                    dept = str(p.get("department", "")).lower()
                    seniority = p.get("seniority")
                    
                    # Filtra Tier 6 (Sócio/Board) e Tier 0 (Root/Empresa)
                    if seniority in [0, 6, "0", "6"]:
                        continue
                    
                    # Filtra por palavras-chave se o seniority for inconclusivo ou for Holding
                    is_excluded = any(kw in role or kw in dept for kw in ["sócio", "socio", "holding", "administrador judicial", "aktieselskab", "aktiengesellschaft"])
                    if is_excluded:
                        continue
                        
                    filtered_list.append(p)

                internal_context["persons"] = filtered_list
                all_persons = filtered_list  # Atualiza para o loop de enriquecimento abaixo
                
                # --- ENRIQUECIMENTO DE DADOS PARA O CARD ---
                # Completa e-mails parciais e injeta dados extras do OSINT
                org_info = internal_context.get("organization", {})
                org_domain = org_info.get("domain") or org_info.get("domain_url")
                
                # Fallback: Se não tem domínio, mas tem nome da empresa, tenta construir um
                if not org_domain and org_info.get("name"):
                    # Remove espaços e bota .com (tentativa desesperada)
                    clean_name = org_info.get("name").lower().replace(" ", "")
                    org_domain = f"{clean_name}.com"

                print(f"[AI Bypass] 🔍 Enriquecendo {len(all_persons)} funcionários. Domínio alvo: {org_domain}")

                for p in all_persons:
                    if not isinstance(p, dict): continue
                    
                    # 1. Ajuste de E-mail (Completar se terminar em @)
                    email = p.get("email") or p.get("emailProvavel")
                    if email and email.endswith("@") and org_domain:
                        p["email"] = f"{email}{org_domain}"
                        print(f"[AI Bypass] ✅ E-mail completado: {p['email']}")
                    
                    # 2. Injeção de dados extras (OSINT fallback)
                    if "osint_result" in internal_context:
                        osint = internal_context["osint_result"]
                        p_name = p.get("name", "").strip()
                        
                        # Busca no OSINT (tenta match exato ou parcial)
                        p_osint = osint.get(p_name)
                        if not p_osint:
                            # Busca por primeiro nome se não achar exato
                            first_name = p_name.split(" ")[0]
                            for key in osint:
                                if first_name in key:
                                    p_osint = osint[key]
                                    break

                        if p_osint:
                            if not p.get("location") or p.get("location") == "Localização não identificada": 
                                p["location"] = p_osint.get("location") or p_osint.get("cidade")
                            
                            if not p.get("observations") or "Nenhuma informação" in p.get("observations", ""):
                                p["observations"] = p_osint.get("summary") or p_osint.get("headline") or p_osint.get("description")
                            
                            if not p.get("phone"):
                                p["phone"] = p_osint.get("pabx") or p_osint.get("phone") or p_osint.get("whatsapp")

                            if not p.get("email"):
                                raw_email = p_osint.get("emailProvavel") or p_osint.get("email")
                                if raw_email:
                                    if raw_email.endswith("@") and org_domain:
                                        p["email"] = f"{raw_email}{org_domain}"
                                    else:
                                        p["email"] = raw_email

                response_msg = f"Localizei {count} funcionários mapeados{target_text}:" if count > 0 else f"Não encontrei funcionários mapeados{target_text}."
                u_mod = "ContactGrid"

            print(f"[AI Pipeline] ⚡ Bypass de IA ativado para {query_t}. Retornando dados brutos.")
            return ChatResponse(
                response=response_msg,
                ui_module=u_mod,
                data=internal_context,
                debug={"intent": intent_info, "bypass": True}
            )

        # 🔥 BYPASS PARA WHATSAPP (Ações de Envio de Mensagem)
        is_wa_send = intent_info.get("query_type") == "whatsapp" and intent_info.get("whatsapp_action") in ["send_message", "send"]
        wa_ctx = internal_context.get("whatsapp_result", {})
        
        if is_wa_send:
            # Só faz bypass se o status foi 200 (sucesso real no envio)
            if wa_ctx.get("status") == 200:
                print("[AI Pipeline] ⚡ Bypass WhatsApp acionado (Sucesso).")
                return ChatResponse(
                    response=f"Sua mensagem para {wa_ctx.get('contact', {}).get('name', 'o contato')} foi enviada!",
                    ui_module="WhatsAppThread",
                    data=internal_context,
                    debug={"intent": intent_info, "bypass": True}
                )

        # 🔥 BYPASS PARA EMAIL (Ações de Envio de Email)
        is_email_send = intent_info.get("query_type") == "email" and intent_info.get("email_action") == "send_email"
        email_ctx = internal_context.get("email_result", {})
        
        if is_email_send:
            if email_ctx.get("status") == 200:
                print("[AI Pipeline] ⚡ Bypass Email acionado (Sucesso).")
                return ChatResponse(
                    response=f"Seu e-mail para {email_ctx.get('to')} foi enviado com sucesso via Outlook!",
                    ui_module="EmailThread",
                    data=internal_context,
                    debug={"intent": intent_info, "bypass": True}
                )
            else:
                # Se deu erro, deixa seguir para o Estágio 2 onde a IA vai explicar o erro.
                print(f"[AI Pipeline] ⚠️ Falha no envio de e-mail detectada (Status {email_ctx.get('status')}). Seguindo para explicação da IA.")

        # --- ESTÁGIO 2: Geração da Resposta com IA ---
        system_context_type = query_type
        if query_type == "general" and payload.context and payload.context != "general":
             system_context_type = payload.context
             
        system_context = _get_system_context(system_context_type)
        json_instruction = """
Retorne obrigatoriamente um JSON com a seguinte estrutura:
{
  "response": "Sua resposta textual aqui",
  "ui_module": "TaskList" | "ContactGrid" | "CompanyCard" | "WhatsAppThread" | "EmailThread" | null,
  "data_module": { ... }
}
"""
        context_prompt = f"\n\n{_format_context_for_prompt(internal_context)}" if internal_context else ""
        history_prompt = ""
        if payload.history:
            hist_lines = [f"{('Você' if m.role == 'user' else 'Eu')} disse: {m.content}" for m in payload.history[-5:]]
            history_prompt = "\n\nHistórico Recente:\n" + "\n".join(hist_lines)
        
        full_prompt = f"{system_context}\n{json_instruction}{context_prompt}{history_prompt}\n\nPergunta: {payload.message}"
        
        from services.external.base_gemini_service import ask_gemini
        response = await ask_gemini(full_prompt, json_mode=True)
        
        if not response:
            return ChatResponse(response="Erro ao processar mensagem.")
        
        response_data = response if isinstance(response, dict) else json.loads(str(response))
        cleaned_response = _clean_response(response_data.get("response", ""))
        
        final_data = internal_context.copy()
        ai_data_module = response_data.get("data_module")
        if isinstance(ai_data_module, dict):
            final_data.update(ai_data_module)

        return ChatResponse(
            response=cleaned_response,
            ui_module=response_data.get("ui_module"),
            data=final_data,
            debug={"intent": intent_info}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback_msg = traceback.format_exc()
        print(f"[AI Chat] Erro ao processar mensagem: {error_msg}")
        print(f"[AI Chat] Traceback:\n{traceback_msg}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {error_msg}")

def _get_system_context(context: str) -> str:
    """Retorna o contexto do sistema baseado no tipo de conversa, forçando objetividade absoluta."""
    
    contexts = {
        "whatsapp": """Você é um assistente técnico de WhatsApp. 
REGRAS CRÍTICAS:
1. Responda APENAS o que foi perguntado. Proibido dar conselhos, sugerir estratégias ou fazer comentários sociais/emocionais.
2. Se o usuário perguntar o que tem na conversa, resuma as mensagens de forma estritamente factual.
3. Se não houver dados, diga apenas: "Não há registros encontrados".
4. Use tom profissional, curto e direto. Não "encha linguiça".
5. Se o campo "error" for "MISSING_MESSAGE_BODY", você DEVE perguntar ao usuário o que ele deseja escrever para o contato em questão. Não reporte que enviou a mensagem se esse erro aparecer.
6. Se o campo "error" for "CONTACT_NOT_FOUND", explique que não encontrou o número dessa pessoa nos seus registros nem nos contatos do WhatsApp. Peça o número para prosseguir.
7. Se o campo "error" for "AMBIGUOUS_CONTACT", você DEVE listar os nomes dos contatos encontrados (campo "matches") e perguntar ao usuário qual deles é o correto.""",

        "pipedrive_info": """Você é um analista de CRM focado estritamente em dados.
REGRAS CRÍTICAS:
1. Responda APENAS o que foi perguntado sobre o Pipedrive (Deals, Activities, Notes).
2. Proibido avaliar a estratégia de vendas ou sugerir "próximos passos" a menos que seja explicitamente solicitado.
3. Liste os dados de forma objetiva em texto fluido.
4. Se um dado for 0 ou inexistente, reporte o fato sem interpretar se isso é bom ou ruim.""",

        "pipedrive_tasks": """Você é um assistente de produtividade pessoal integrado ao Pipedrive.
REGRAS CRÍTICAS:
1. Analise cuidadosamente a seção "TAREFAS/ATIVIDADES AGENDADAS NO PIPEDRIVE" nos dados internos.
2. Se houver itens listados com ID, Tipo e Assunto, você DEVE reportá-los. NUNCA diga que não encontrou tarefas se houver dados ali.
3. Organize as tarefas por data (Vencimento). Atividades com datas passadas devem ser indicadas como "Atrasadas".
4. Se o usuário especificar uma empresa (ex: @Empresa), mostre apenas as tarefas dessa empresa.
5. Se não houver ABSOLUTAMENTE NADA no contexto para a empresa ou globalmente, aí sim responda que não encontrou.
6. Use o módulo 'TaskList' e preencha o 'data_module' com a lista de tarefas encontrada.
7. Nunca dê conselhos sobre gestão de tempo.""",

        "contacts": """Você é um especialista em mapeamento de contatos B2B.
REGRAS CRÍTICAS:
1. Liste apenas os nomes, cargos e departamentos encontrados nos DADOS INTERNOS.
2. Não faça suposições sobre pessoas que não estão na lista.
3. Se não houver contatos mapeados, diga apenas: "Não há contatos mapeados para esta empresa".""",
        
        "general": """Você é um assistente corporativo B2B de alta precisão.
REGRAS:
1. Responda APENAS à pergunta do usuário com base nos dados fornecidos.
2. Proibido parágrafos de encerramento com dicas, encorajamentos ou sugestões proativas.
3. Seja o mais direto possível. Se a resposta for "Sim" ou "Não" baseada nos dados, responda de forma curta.""",

        "email": """Você é um assistente técnico de E-mail (Outlook).
REGRAS CRÍTICAS:
1. Responda de forma factual sobre o status do envio ou lista de e-mails.
2. Se listar pastas, organize-as de forma clara.
3. Se listar e-mails (get_messages), resuma quem enviou e o assunto.
4. Se o envio falhar por falta de dados, pergunte claramente o que falta (destinatário, assunto ou corpo).
5. Nunca invente que um e-mail foi enviado se houver erro no contexto."""
    }
    
    return contexts.get(context, contexts["general"])

