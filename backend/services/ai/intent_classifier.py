"""
Estágio 1 do Pipeline: Classificação de Intenção via LLM.
Analisa a mensagem do usuário e determina o tipo de query, ações e escopos de dados.
"""
import json
from typing import Optional, List
from services.ai.helpers import MessageInput


async def classify_user_intent(message: str, history: Optional[List[MessageInput]] = None) -> dict:
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
- "email": O usuário quer interagir com o EMAIL (enviar email, escrever um email, mandar um email, ler emails, ver pastas, buscar mensagens do Outlook).
- "contacts": O usuário focou em PESSOAS para obter informações (quem são, cargos, quem trabalha lá, listagem de equipe). 
- "enrichment": O usuário quer ENCONTRAR O CONTATO (OSINT/LinkedIn).
- "pipedrive_tasks": O usuário quer apenas LISTAR as tarefas (o que tem para fazer, o que já foi feito, ver a agenda).
- "agent_workflow": O usuário quer uma ANALISE seguida de uma AÇÃO ou SUGESTÃO de próximo passo ("analise o histórico e crie o próximo passo", "o que eu devo fazer agora com essa empresa?", "cuida disso para mim", "realize o fluxo"). Se houver verbos como "analisar", "criar próximo passo", "gerar sugestão", use este tipo.
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
    "query_type": "contacts" | "company_info" | "pipedrive_info" | "pipedrive_tasks" | "whatsapp" | "email" | "enrichment" | "agent_workflow" | "general",
    "data_scope": ["employees", "deals", "activities", "today_tasks", "emails", ...],
    "activity_done_filter": 0 | 1 | null, 
    "activity_date_filter": "today" | "tomorrow" | "overdue" | "future" | "all" | null,
    "extracted_company_name": "Nome da empresa identificado ou inferido ou null",
    "extracted_person_name": "Nome da pessoa identificado ou inferido ou null",
    "extracted_person_hint": "Dica sobre a pessoa ou null",
    "whatsapp_action": "send_message" | "get_chats" | "get_messages" | "search_contacts" | null,
    "whatsapp_message": "Mensagem para enviar ou null",
    "whatsapp_chat_id": "ID técnico real (ex: '5511... @c.us' ou '... @lid'). NUNCA use o nome da pessoa/empresa aqui. Se não souber o ID técnico, deixe null.",
    "email_action": "send_email" | "get_unread" | "get_messages" | "list_folders" | null,
    "email_to": "Email do destinatário ou null",
    "email_subject": "Assunto do e-mail ou null",
    "email_body": "Corpo do e-mail ou null",
    "email_folder": "Pasta (ex: Inbox, Sent, Leads) ou null"
}}

REGRAS PARA activity_done_filter:
- Use 0 para "a fazer", "pendentes", "próximas", "agendadas", "em aberto".
- Use 1 para "concluídas", "feitas", "realizadas", "terminadas".
- Use null para "todas", "feitas e não feitas", "tudo o que tem", "histórico completo", "tudo da empresa", "geral".

REGRAS PARA activity_date_filter:
- "today": apenas de hoje.
- "tomorrow": apenas de amanhã.
- "overdue": apenas as atrasadas.
- "future": próximas tarefas (hoje e futuro).
- "all": sem filtro de data (todo o histórico). Use "all" se o usuário pedir "todas", "tudo", "do começo ao fim".
"""
    try:
        response = await ask_gemini(prompt, json_mode=True)
        
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
        
    return {
        "query_type": "general", "data_scope": [], "activity_done_filter": 0,
        "extracted_company_name": None, "whatsapp_action": None,
        "whatsapp_number": None, "whatsapp_message": None, "whatsapp_chat_id": None
    }


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
        done_filter = 0  # Default para segurança/produtividade
    
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
