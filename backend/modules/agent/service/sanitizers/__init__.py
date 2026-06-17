"""
modules.agent.service.sanitizers
=================================
Limpeza e compactacao de resultados de ferramentas para consumo por LLM.

Converte respostas brutas (Pipedrive, WhatsApp, Email) em narrativas compactas,
reduzindo tokens sem perder informacao relevante para o raciocinio do agente.

Funcao publica: _sanitize_result(tool_name, result) -> Any
"""
from __future__ import annotations
from typing import Any
from core.observability.logging_config import get_logger
from modules.agent.service.sanitizers.email_context_extractor import extract_thread_summary, extract_email_narrative

log = get_logger(__name__)


def _sanitize_email(data: dict) -> str:
    """Compacta e-mails em formato narrativo denso com extração de decisores.
    Usa sempre o módulo email_context_extractor para narrativa detalhada."""
    if not data or not isinstance(data, dict): return str(data)
    emails = data.get("emails", [])
    if not emails: return "📧 Nenhum e-mail encontrado."

    contact_name = data.get("contact", "")

    try:
        narrative = extract_thread_summary(emails, contact_name)
        header = f"📧 E-mails com {contact_name or 'o contato'} ({len(emails)} e-mails):\n"
        narrative = header + narrative
        entry_ids = [e.get("entryId", "") for e in emails[:5] if e.get("entryId")]
        if entry_ids:
            narrative += f"\n[EntryIDs para email_reply: {', '.join(entry_ids[:3])}]"
        return narrative
    except Exception as e:
        # Fallback para formato original apenas em caso de erro real
        lines = [f"📧 HISTÓRICO EMAIL ({data.get('count', 0)} msgs):"]
        for e in emails[:8]:
            body = e.get("preview", "").replace("\n", " ").strip()
            from_addr = e.get("from", "")
            # Extrai nome e domínio para fuzzy search
            name_part = from_addr.split("<")[0].strip() if "<" in from_addr else from_addr
            domain = from_addr.split("@")[-1].split(">")[0] if "@" in from_addr else ""

            subject = e.get("subject", "(sem assunto)")
            date = e.get("date", "")
            body_summary = body[:180] if body else ""

            lines.append(f"  [{date}] {name_part}: '{subject}' | {body_summary}")
            if domain and domain not in ["gmail.com", "hotmail.com", "outlook.com"]:
                lines.append(f"    → Domínio empresarial: {domain}")

        # Detecta pessoas mencionadas para name radar
        all_text = " ".join([e.get("preview", "") for e in emails[:5]])
        mentioned = _extract_names_from_text(all_text)
        if mentioned:
            lines.append(f"  👤 Decisores mencionados: {', '.join(mentioned[:5])}")

        return "\n".join(lines)


def _extract_names_from_text(text: str) -> list:
    """Extrai nomes próprios mencionados no texto (simples heurística)."""
    import re
    if not text: return []

    # Padrões comuns: "O [Nome] vai", "Fale com [Nome]", "[Nome] disse"
    patterns = [
        r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+',  # Nome próprio (2+ palavras capitalizadas)
        r'(?:o|a|com|para)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',  # "o João", "com a Kamila"
    ]

    found = set()
    for p in patterns:
        matches = re.findall(p, text, re.IGNORECASE)
        for m in matches:
            name = m[0] if isinstance(m, tuple) else m
            name = name.strip()
            # Filtra palavras comuns que não são nomes
            if name and len(name) > 3 and name.lower() not in ['para', 'como', 'esta', 'esse', 'essa', 'quem', 'onde', 'quando', 'porque']:
                found.add(name)

    return list(found)[:10]  # Limita para não poluir

def _sanitize_pipedrive(data: dict) -> str:
    """Converte dados do Pipedrive em dossiê executivo compacto."""
    if not data or not isinstance(data, dict): return str(data)

    # Caso seja lista de organizações
    if "organizations" in data:
        orgs = data["organizations"][:10]
        if not orgs: return "📊 Nenhuma empresa encontrada."
        return "📊 Empresas: " + " | ".join([f"{o['name']} (ID:{o['id']})" for o in orgs])

    # Caso seja detalhe de uma organização/deal/contatos
    sections = []

    # Se houver sumário (ex: resultado de pipedrive_get_persons com análise ICP),
    # incluímos no topo para que o Agent Loop possa interceptar regras de banco local.
    if "summary" in data and isinstance(data["summary"], str):
        sections.append(f"📝 RESUMO: {data['summary']}")

    _org_field = data.get("org")
    org_name = data.get("name", "") or (
        _org_field.get("name", "") if isinstance(_org_field, dict) else str(_org_field or "")
    )
    if org_name:
        sections.append(f"🏢 ORG: {org_name}")

    # Deals estruturados
    if "deals" in data and data["deals"]:
        deals_lines = ["💼 DEALS:"]
        for d in data["deals"][:5]:
            title = d.get('title', 'Sem título')
            status = d.get('status', 'N/A')
            value = d.get('value', 0)
            currency = d.get('currency', 'BRL')
            stage = d.get('stage', 'Desconhecido')
            deals_lines.append(f"   • [ID:{d.get('id','?')}] {title} | {status} | R${value:,.0f} | Funil: {stage}")
        sections.append("\n".join(deals_lines))

    # Contatos estruturados
    if "persons" in data and data["persons"]:
        persons_lines = ["👥 CONTATOS:"]
        for p in data["persons"][:15]:
            name = p.get('name', 'N/A')
            email = p.get('email', '')
            phone = p.get('phone', '')
            contact = phone or email or 'sem contato'
            
            role = p.get('role', '')
            source = p.get('source', 'Pipedrive')
            local_id = p.get('local_id', '')
            
            role_str = f" - Cargo: {role}" if role else ""
            source_str = f" [{source}]"

            p_id = p.get('id') or 'LocalDB'
            persons_lines.append(f"   • [ID:{p_id}] {name} ({contact}){role_str}{source_str}")
        sections.append("\n".join(persons_lines))

    # Atividades pendentes
    if "activities" in data and data["activities"]:
        acts_lines = ["📋 ATIVIDADES:"]
        pending_count = 0
        for a in data["activities"][:8]:
            subject = a.get('subject', 'Sem assunto')
            due = a.get('due_date', 'sem data')
            done = a.get('done', False)
            note = (a.get('note') or '')[:80]
            status = "✓" if done else "◯"
            if not done:
                pending_count += 1
            acts_lines.append(f"   {status} [ID:{a.get('id','?')}] {subject} (venc: {due}){f' | {note}' if note else ''}")
        if pending_count > 0:
            acts_lines.append(f"   ⚠️ {pending_count} pendente(s)")
        sections.append("\n".join(acts_lines))

    # Notas
    if "notes" in data and data["notes"]:
        notes_lines = ["📝 NOTAS RECENTES:"]
        for n in data["notes"][:3]:
            note_text = str(n)[:200]
            notes_lines.append(f"   • {note_text}")
        sections.append("\n".join(notes_lines))

    # Atividades vindas de exec_pipedrive_get_activities (chave "pending")
    if "pending" in data and data["pending"]:
        acts_lines = ["📋 ATIVIDADES PENDENTES:"]
        for a in data["pending"][:8]:
            act_id = a.get('id', '?')
            subject = a.get('subject', 'Sem assunto')
            due = a.get('due_date', 'sem data')
            note = (a.get('note') or '')[:80]
            acts_lines.append(f"   ◯ [ID:{act_id}] {subject} (venc: {due}){f' | {note}' if note else ''}")
        sections.append("\n".join(acts_lines))

    # Atividades vindas de exec_pipedrive_get_all_activities (chaves "today"/"overdue"/"all")
    if "today" in data or "overdue" in data or "all" in data:
        today_acts = data.get("today", [])
        overdue_acts = data.get("overdue", [])
        count_today = data.get("count_today", len(today_acts))
        count_overdue = data.get("count_overdue", len(overdue_acts))

        if overdue_acts:
            ov_lines = [f"🔴 ATRASADAS ({count_overdue}):"]
            for a in overdue_acts[:30]:
                org = a.get('org', 'Sem empresa')
                subject = a.get('subject', 'Sem assunto')
                due = a.get('due_date', '?')
                note = (a.get('note') or '')[:60]
                ov_lines.append(f"   ◯ [{org}] {subject} (venc: {due}){f' — {note}' if note else ''}")
            sections.append("\n".join(ov_lines))

        if today_acts:
            td_lines = [f"📋 HOJE ({count_today}):"]
            for a in today_acts[:40]:
                org = a.get('org', 'Sem empresa')
                subject = a.get('subject', 'Sem assunto')
                note = (a.get('note') or '')[:60]
                td_lines.append(f"   ◯ [{org}] {subject}{f' — {note}' if note else ''}")
            sections.append("\n".join(td_lines))

        if not today_acts and not overdue_acts:
            sections.append("✅ Nenhuma atividade pendente para hoje ou atrasada.")

    return "\n\n".join(sections) if sections else "📊 Sem dados relevantes no Pipedrive."

def _sanitize_whatsapp(data: dict) -> str:
    """Compacta histórico de WhatsApp em log narrativo denso com tom da conversa."""
    if not data or not isinstance(data, dict): return str(data)
    msgs = data.get("messages", [])
    contact = data.get('contact', 'o contato')
    if not msgs: return f"💬 WhatsApp: Nenhuma mensagem com {contact}."

    # O sistema agora confia no Agente para identificar se o sufixo (ex: " - Empresa")
    # é relevante ou se é um homônimo, conforme as regras de inteligência de nomes.
    _company_suffix_warning = ""

    phone = data.get("phone", "")
    header = f"💬 WHATSAPP ({contact}) - {len(msgs)} mensagens:"
    if phone:
        header += f" | 📱 TELEFONE PARA ENVIO: {phone}"
    else:
        header += " | ⚠️ ID interno detectado — use o telefone do Pipedrive para enviar"
    lines = [header]

    # Últimas mensagens (mais recentes primeiro)
    recent_msgs = msgs[-12:]
    has_response_from_contact = False
    last_msg_time = None

    for m in recent_msgs:
        if isinstance(m, str):
            # Se for string formatada, usa direto
            lines.append(f"  {m}")
            if f"[{contact}]" in m or f"[{contact.lower()}]" in m.lower():
                has_response_from_contact = True
            elif "[Você]" not in m and "[joao.moura" not in m:
                has_response_from_contact = True
            continue

        if not isinstance(m, dict):
            continue

        sender_raw = m.get('sender') or m.get('from') or ''
        is_me = m.get('from_me') or m.get('fromMe') or 'EU' in str(sender_raw)
        sender = 'EU' if is_me else contact
        if not is_me:
            has_response_from_contact = True

        body = (m.get('body') or m.get('text') or '').replace("\n", " ").strip()
        timestamp = m.get('timestamp', '') or m.get('date', '')
        if timestamp and not last_msg_time:
            last_msg_time = str(timestamp)[:10]

        lines.append(f"  [{sender}]: {body[:200]}")

    # Detecta tom da conversa
    all_text = ""
    for m in recent_msgs:
        if isinstance(m, str):
            all_text += " " + m
        elif isinstance(m, dict):
            all_text += " " + (m.get('body') or m.get('text') or '')
    all_text = all_text.lower()

    if "obrigado" in all_text or "perfeito" in all_text or "ok" in all_text:
        sentiment = "✅ positivo"
    elif "urgente" in all_text or "preciso" in all_text or "hoje" in all_text:
        sentiment = "⚠️ urgente"
    elif "aguardo" in all_text or "quando" in all_text or "falta" in all_text:
        sentiment = "⏳ aguardando"
    elif not has_response_from_contact:
        sentiment = "🔇 sem resposta"
    else:
        sentiment = "🔄 em andamento"

    lines.append(f"  📊 Status: {sentiment} | Última: {last_msg_time or 'desconhecida'}")

    result_text = "\n".join(lines)
    # Prepend o aviso de empresa errada se detectado — o modelo deve ver isso antes das mensagens
    if _company_suffix_warning:
        result_text = _company_suffix_warning + result_text
    return result_text

def _sanitize_evaluate_prospects(data: dict) -> str:
    """Compacta o ranking de prospects em uma narrativa densa para o LLM."""
    if not data or not isinstance(data, dict): return str(data)
    prospects = data.get("best_prospects", [])
    if not prospects: return "🔍 Nenhum prospect avaliado como adequado."

    lines = [f"🔍 RANKING DE PROSPECTING PARA {data.get('org_name', 'a empresa')}:"]
    for p in prospects[:10]:
        score = p.get("suitability_score", 0)
        tier = p.get("suitability_tier", "C")
        role = p.get("role") or p.get("department") or "Contato"
        reason = p.get("key_reason", "")
        angle = p.get("angle_of_approach", "")
        
        lines.append(f"  • {p.get('name')} ({role}) | SCORE: {score} | TIER: {tier}")
        if reason:
            lines.append(f"    → Motivo: {reason[:200]}")
        if angle:
            lines.append(f"    → Abordagem: {angle[:200]}")
    
    strategy = data.get("overall_strategy", "")
    if strategy:
        lines.append(f"\n💡 ESTRATÉGIA GERAL: {strategy[:500]}")
        
    return "\n".join(lines)

def _sanitize_result(tool_name: str, result: Any) -> Any:
    """Orquestra a limpeza retornando strings otimizadas para o LLM."""
    try:
        if not result: return "Sem resultados."
        if tool_name == "suggest_next_actions": return "Tarefas sugeridas criadas na interface para o usuário aprovar."
        if tool_name == "evaluate_prospects": return _sanitize_evaluate_prospects(result)
        if tool_name == "discover_and_validate_email": return result
        if "email" in tool_name: return _sanitize_email(result)
        if "pipedrive" in tool_name: return _sanitize_pipedrive(result)
        if "whatsapp" in tool_name: return _sanitize_whatsapp(result)
        return result
    except Exception as e:
        return f"Erro na sanitização: {e} | Dados brutos: {str(result)[:500]}"
