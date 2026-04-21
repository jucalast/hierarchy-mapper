"""
Helpers e modelos Pydantic para o pipeline de IA.
Funções utilitárias de limpeza e formatação de contexto.
"""
import re
import datetime
from typing import Optional, Dict, List, Any, Union
from pydantic import BaseModel


# ==========================================
# MODELOS PYDANTIC
# ==========================================

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


# ==========================================
# FUNÇÕES UTILITÁRIAS
# ==========================================

def clean_response(text: str) -> str:
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


def format_context_for_prompt(context_dict: dict) -> str:
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
                    clean_note = clean_response(n.get('content', ''))
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
        elif wa.get("status") and wa.get("status") >= 400:
            res_data = wa.get("resultado", {})
            detail = res_data.get("detail") or res_data.get("message") or "Erro desconhecido"
            lines.append(f"Atenção: A ação de WhatsApp falhou com status {wa.get('status')}. Detalhe: {detail}")
        else:
            result_data = wa.get('resultado', {})
            
            # --- MODALIDADE 1: Mensagens por Contato (Automático do Agent) ---
            by_contact = result_data.get('messages_by_contact', [])
            if by_contact:
                for contact_group in by_contact:
                    lines.append(f"\nConversa com {contact_group.get('contact')}:")
                    for m in contact_group.get('messages', [])[:15]:
                        sender = "Eu" if m.get("fromMe") else "Contato"
                        body = m.get("body", "(Sem conteúdo de texto)")
                        ts = m.get("timestamp")
                        time_str = f" [{datetime.datetime.fromtimestamp(ts).strftime('%d/%m %H:%M')}]" if ts else ""
                        lines.append(f"  {sender}{time_str}: {body}")
            
            # --- MODALIDADE 2: Mensagens de um chat específico ---
            else:
                messages = result_data.get('messages', [])
                if messages:
                    for m in messages:
                        sender = "Eu" if m.get("fromMe") else "Contato"
                        body = m.get("body", "(Sem conteúdo de texto)")
                        ts = m.get("timestamp")
                        time_str = f" [{datetime.datetime.fromtimestamp(ts).strftime('%d/%m %H:%M')}]" if ts else ""
                        lines.append(f"{sender}{time_str}: {body}")
                else:
                    lines.append("Nenhuma mensagem encontrada.")
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
            result_data = em.get("resultado", {})
            
            # --- MODALIDADE 1: Emails por Contato ---
            by_contact = result_data.get('messages_by_contact', [])
            if by_contact:
                for contact_group in by_contact:
                    lines.append(f"\nEmails trocados com {contact_group.get('contact')} ({contact_group.get('email')}):")
                    for m in contact_group.get('messages', [])[:5]:
                        subject = m.get("subject") or "(Sem assunto)"
                        date = m.get("date") or ""
                        body = m.get("body", "")[:300]
                        lines.append(f"  - Assunto: {subject} | Data: {date}")
                        lines.append(f"    Snippet: {body}...")
            
            # --- MODALIDADE 2: Emails genéricos de pasta ---
            else:
                action = em.get("email_action")
                if action == "list_folders":
                    lines.append("\nPASTAS ENCONTRADAS:")
                    for f in em.get("folders", []):
                        lines.append(f"- {f}")
                elif action == "get_messages" or action == "get_unread":
                    lines.append(f"\nMENSAGENS NA PASTA '{em.get('folder', 'Inbox')}':")
                    for m in (result_data.get("messages") or []):
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
