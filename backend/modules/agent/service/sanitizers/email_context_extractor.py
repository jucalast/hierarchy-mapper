"""
Módulo de Extração de Contexto de Emails.

Complementa as funções existentes em agent.py (_sanitize_email) e tools.py (exec_email_get_contact_history)
fornecendo análise narrativa detalhada de threads de email, identificação de participantes e extração de ações.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Tuple


def extract_email_narrative(emails: List[Dict[str, Any]], contact_name: str = "") -> str:
    """
    Extrai narrativa detalhada de emails no formato: "Em [data], [remetente] disse: [conteúdo]. [destinatário] respondeu: [conteúdo]"
    
    Args:
        emails: Lista de emails retornados por exec_email_get_contact_history (campos: from, to, subject, date, preview, direction)
        contact_name: Nome do contato principal para identificar mensagens enviadas/recebidas
    
    Returns:
        String narrativa com a conversa completa
    """
    if not emails:
        return "Nenhum e-mail encontrado."
    
    # Ordenar por data (mais antigo primeiro para narrativa cronológica)
    sorted_emails = sorted(emails, key=lambda e: e.get("date", ""))
    
    narrative_lines = []
    narrative_lines.append(f"📧 CONVERSA POR E-MAIL ({len(emails)} mensagens):")
    
    for i, email in enumerate(sorted_emails):
        date = email.get("date", "data desconhecida")
        sender = _extract_name_from_email(email.get("from", ""))
        recipient = _extract_name_from_email(email.get("to", ""))
        subject = email.get("subject", "(sem assunto)")
        body = email.get("preview", "").strip()
        direction = email.get("direction", "unknown")
        
        # Resumir corpo para narrativa (mais detalhado que o preview atual)
        body_summary = _summarize_email_body(body, max_length=500)
        
        # Identificar quem falou baseado na direção
        if direction == "sent":
            speaker = "Você"
            other = recipient or contact_name
        elif direction == "received":
            speaker = sender or contact_name or "Contato"
            other = "Você"
        else:
            # Se direction não estiver disponível, inferir pelo remetente
            if sender and contact_name and contact_name.lower() in sender.lower():
                speaker = "Você"
                other = recipient or contact_name
            else:
                speaker = sender or contact_name or "Contato"
                other = recipient or "Você"
        
        # Formatar linha narrativa
        if i == 0:
            # Primeiro email - inicia a conversa
            line = f"  Em {date}, {speaker} iniciou o assunto '{subject}': {body_summary}"
        else:
            # Respostas subsequentes
            prev_subject = sorted_emails[i-1].get("subject", "")
            if subject == prev_subject:
                line = f"  Em {date}, {speaker} respondeu: {body_summary}"
            else:
                line = f"  Em {date}, {speaker} sobre '{subject}': {body_summary}"
        
        narrative_lines.append(line)
    
    # Adicionar resumo de ações encontradas
    actions = _extract_actions_from_emails(emails)
    if actions:
        narrative_lines.append("\n  📋 Ações/Pendências mencionadas:")
        for action in actions[:5]:
            narrative_lines.append(f"    • {action}")
    
    return "\n".join(narrative_lines)


def _extract_name_from_email(email_addr: str) -> str:
    """Extrai o nome de um endereço de email (ex: 'João Silva <joao@email.com>' -> 'João Silva')."""
    if not email_addr:
        return ""
    
    # Se tiver formato "Nome <email@dominio.com>"
    if "<" in email_addr and ">" in email_addr:
        name_part = email_addr.split("<")[0].strip()
        return name_part if name_part else email_addr
    
    # Se for apenas email, extrair nome antes do @
    if "@" in email_addr:
        local_part = email_addr.split("@")[0]
        # Converter email.name para Email Name
        return local_part.replace(".", " ").replace("_", " ").title()
    
    return email_addr


def _summarize_email_body(body: str, max_length: int = 400) -> str:
    """Resume o corpo do email removendo excesso de espaços e mantendo o essencial."""
    if not body:
        return "(sem conteúdo)"
    
    # Remover quebras de linha excessivas
    cleaned = re.sub(r'\n+', ' ', body)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    if len(cleaned) <= max_length:
        return cleaned
    
    # Truncar em limite mas tentar cortar em espaço
    truncated = cleaned[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > max_length * 0.7:  # Se tiver espaço razoável próximo do limite
        truncated = truncated[:last_space]
    
    return truncated + "..."


def _extract_actions_from_emails(emails: List[Dict[str, Any]]) -> List[str]:
    """Extrai ações, decisões e pendências mencionadas nos emails."""
    actions = []
    
    # Padrões de ações comuns
    action_patterns = [
        r'(aguardando|esperando|aguardo)\s+(?:o\s+)?(?:retorno\s+)?(?:de\s+)?(.{5,80})',
        r'(preciso|precisamos|necessário)\s+(.{5,80})',
        r'(vou|vamos|iremos)\s+(.{5,80})',
        r'(aprovar|aprovação|validar|validação)\s+(.{5,80})',
        r'(prazo|deadline|entregar)\s+(.{5,80})',
        r'(reunião|encontro|call)\s+(?:em\s+)?(.{5,80})',
        r'(enviar|mandar)\s+(.{5,80})',
    ]
    
    all_text = " ".join([e.get("preview", "") for e in emails])
    all_text = all_text.lower()
    
    for pattern in action_patterns:
        matches = re.findall(pattern, all_text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                action_text = match[1] if len(match) > 1 else match[0]
            else:
                action_text = match
            
            # Limpar e capitalizar
            action_text = action_text.strip()
            if action_text and len(action_text) > 3:
                # Capitalizar primeira letra
                action_text = action_text[0].upper() + action_text[1:]
                if action_text not in actions:
                    actions.append(action_text)
    
    return actions[:10]  # Limitar para não poluir


def identify_participants(emails: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Identifica todos os participantes únicos da conversa de email.
    
    Returns:
        Lista de dicionários com: name, email, role (sender/recipient)
    """
    participants = {}
    
    for email in emails:
        sender = email.get("from", "")
        recipient = email.get("to", "")
        
        # Processar remetente
        if sender:
            name = _extract_name_from_email(sender)
            email_addr = sender.split("<")[-1].strip(">").strip() if "<" in sender else sender
            key = name.lower() if name else email_addr.lower()
            
            if key not in participants:
                participants[key] = {
                    "name": name,
                    "email": email_addr,
                    "role": "sender",
                    "message_count": 0
                }
            participants[key]["message_count"] += 1
        
        # Processar destinatário
        if recipient:
            name = _extract_name_from_email(recipient)
            email_addr = recipient.split("<")[-1].strip(">").strip() if "<" in recipient else recipient
            key = name.lower() if name else email_addr.lower()
            
            if key not in participants:
                participants[key] = {
                    "name": name,
                    "email": email_addr,
                    "role": "recipient",
                    "message_count": 0
                }
            else:
                # Se já existe como sender, atualizar role para ambos
                if participants[key]["role"] == "sender":
                    participants[key]["role"] = "both"
    
    # Converter para lista ordenada por número de mensagens
    sorted_participants = sorted(
        participants.values(),
        key=lambda p: p["message_count"],
        reverse=True
    )
    
    return sorted_participants


def group_by_thread(emails: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Agrupa emails por thread (assunto similar).
    
    Returns:
        Dicionário onde chave é o assunto normalizado e valor é lista de emails
    """
    threads = {}
    
    for email in emails:
        subject = email.get("subject", "(sem assunto)")
        # Normalizar assunto para agrupar respostas (Re:, Fwd:, etc)
        normalized = re.sub(r'^(Re|Fwd|FW):\s*', '', subject, flags=re.IGNORECASE).strip()
        normalized = normalized.lower()
        
        if normalized not in threads:
            threads[normalized] = []
        threads[normalized].append(email)
    
    return threads


def extract_thread_summary(emails: List[Dict[str, Any]], contact_name: str = "") -> str:
    """
    Extrai um resumo executivo da thread completa, focando no fluxo da conversa.
    
    Returns:
        String narrativa focada no andamento da conversa
    """
    if not emails:
        return "Sem conversa por e-mail."
    
    participants = identify_participants(emails)
    threads = group_by_thread(emails)
    
    summary_lines = []
    
    # Resumo de participantes
    if participants:
        participant_names = [p["name"] for p in participants[:3]]
        summary_lines.append(f"👥 Participantes: {', '.join(participant_names)}")
    
    # Resumo por thread
    if len(threads) > 1:
        summary_lines.append(f"\n📎 {len(threads)} assuntos discutidos:")
        for subject, thread_emails in threads.items():
            summary_lines.append(f"  • '{subject}': {len(thread_emails)} mensagens")
    
    # Narrativa principal
    narrative = extract_email_narrative(emails, contact_name)
    summary_lines.append(f"\n{narrative}")
    
    return "\n".join(summary_lines)
