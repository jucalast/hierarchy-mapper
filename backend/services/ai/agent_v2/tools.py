"""
Ferramentas do Agente V2 — paridade total com V1 + capacidades extras.

Tipos:
  "read"  → executa automaticamente (leitura segura)
  "write" → pausa para confirmação do usuário antes de executar
"""
from __future__ import annotations

import json
from typing import Any, Dict

import httpx

WA_BASE = "http://localhost:8001/api/whatsapp"
EMAIL_SERVICE_BASE = "http://localhost:8002/api/email"
JFERRES_DOMAIN = "jferres.com.br"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _chat_id_str(chat: dict) -> str:
    cid = chat.get("id", "")
    if isinstance(cid, dict):
        return cid.get("_serialized", "") or cid.get("user", "")
    return str(cid) if cid else ""


async def _resolve_wa_chat(client: httpx.AsyncClient, contact: str) -> tuple[str | None, str]:
    """Retorna (chat_id, nome_encontrado). Busca pelo nome mais recente com fallback em busca de contatos."""
    try:
        r = await client.get(f"{WA_BASE}/chats", timeout=10.0)
        if r.status_code == 200:
            body = r.json()
            all_chats = body if isinstance(body, list) else (body.get("chats") or body.get("data") or [])
            term = contact.lower()
            matches = [c for c in all_chats if term in (c.get("name") or "").lower()]
            if matches:
                best = max(
                    matches,
                    key=lambda c: (c.get("lastMessage", {}) or {}).get("timestamp", 0)
                    if isinstance(c.get("lastMessage"), dict) else 0,
                )
                return _chat_id_str(best), best.get("name", contact)
        
        # 🔍 Fallback: Se não achou nos chats ativos/recentes, busca nos CONTATOS cadastrados por nome!
        try:
            c_resp = await client.get(f"{WA_BASE}/contacts/search", params={"name": contact, "minSimilarity": 0.75}, timeout=5.0)
            if c_resp.status_code == 200:
                c_data = c_resp.json()
                contacts_list = c_data if isinstance(c_data, list) else c_data.get("contacts") or []
                if contacts_list:
                    best_contact = contacts_list[0]
                    chat_id = _chat_id_str(best_contact)
                    found_name = best_contact.get("name") or contact
                    return chat_id, found_name
        except Exception:
            pass

        return None, ""
    except Exception:
        return None, ""


async def _log_activity_bg(activity_type: str, payload: dict, org_id=None, status: str = "completed") -> None:
    """Registra atividade no banco de dados (best-effort — nunca lança exceção)."""
    try:
        from core.database import async_session
        from api.v1.endpoints.conversations import log_activity
        async with async_session() as session:
            await log_activity(
                session=session,
                org_id=org_id,
                activity_type=activity_type,
                payload=payload,
                status=status,
            )
    except Exception:
        pass


def _normalize_org_name(name: str) -> str:
    """Remove espaços e normaliza para comparação: 'Gmb H' == 'GmbH'."""
    import re
    return re.sub(r'\s+', '', name).lower()


def _remove_diacritics(s: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


async def _pipedrive_find_org(org_name: str):
    """Busca organização por nome no Pipedrive com matching fuzzy e tie-breaker inteligente. 
    Retorna (match_dict, org_id) ou (None, None).
    """
    from services.pipedrive.pipedrive_service import pipedrive_service
    import unicodedata
    
    orgs = await pipedrive_service.list_organizations()
    if not orgs:
        return None, None
        
    term = org_name.lower().strip()
    term_clean = _remove_diacritics(org_name)
    term_norm = _normalize_org_name(org_name)
    term_norm_clean = _remove_diacritics(term_norm)

    matches = []
    for o in orgs:
        name_raw = o.get("name") or ""
        name_lower = name_raw.lower()
        name_clean = _remove_diacritics(name_raw)
        name_norm = _normalize_org_name(name_raw)
        name_norm_clean = _remove_diacritics(name_norm)
        
        score = 0
        is_match = False
        
        # 1. Matching por substring (com e sem acento)
        if term in name_lower:
            score += 100
            is_match = True
        elif term_clean in name_clean:
            score += 80
            is_match = True
            
        # 2. Matching normalizado sem espaços
        if not is_match:
            if term_norm in name_norm:
                score += 60
                is_match = True
            elif term_norm_clean in name_norm_clean:
                score += 50
                is_match = True
                
        # 3. Matching por palavras-chave
        if not is_match:
            keywords = [w for w in term_clean.split() if len(w) > 3][:2]
            if keywords and all(k in name_clean for k in keywords):
                score += 30
                is_match = True
                
        if is_match:
            # Critérios de desempate (tie-breakers):
            # A. Se o termo original bate exatamente com acentos (case-insensitive)
            exact_accent = 1 if term in name_lower else 0
            
            # B. Quantidade de acentos (caracteres com marca de diacrítico 'Mn') na string original
            accent_count = sum(1 for c in unicodedata.normalize("NFD", name_raw) if unicodedata.category(c) == "Mn")
            
            # C. Presença de "LTDA", "S.A." etc (nomes oficiais costumam ser os reais)
            has_corp_suffix = 1 if any(suf in name_lower for suf in ["ltda", "s.a", "sa", "corp", "holding"]) else 0
            
            matches.append({
                "org": o,
                "score": score,
                "exact_accent": exact_accent,
                "accent_count": accent_count,
                "has_corp_suffix": has_corp_suffix,
                "id": o.get("id")
            })

    if not matches:
        return None, None
        
    # Ordena por:
    # 1. Pontuação de matching descrescente
    # 2. Match exato de acento decrescente
    # 3. Presença de sufixo corporativo decrescente
    # 4. Quantidade de acentuação decrescente (revela nome real e bem cadastrado)
    # 5. ID menor (geralmente registros mais antigos e com histórico)
    matches.sort(key=lambda x: (
        -x["score"],
        -x["exact_accent"],
        -x["has_corp_suffix"],
        -x["accent_count"],
        x["id"] if isinstance(x["id"], int) else 999999
    ))
    
    best = matches[0]["org"]
    return best, best.get("id")


async def _pipedrive_get_org_by_id(org_id: int):
    """Retorna o match_dict de uma organização do Pipedrive pelo ID exato."""
    from services.pipedrive.pipedrive_service import pipedrive_service
    orgs = await pipedrive_service.list_organizations()
    match = next((o for o in (orgs or []) if o.get("id") == org_id), None)
    return match



# ─── Executores: READ ─────────────────────────────────────────────────────────

async def exec_whatsapp_get_messages(args: Dict[str, Any]) -> Dict[str, Any]:
    contact = args.get("contact", "")
    limit = int(args.get("limit", 35))
    async with httpx.AsyncClient() as client:
        try:
            st = await client.get(f"{WA_BASE}/status", timeout=5.0)
            st_data = st.json() if st.status_code == 200 else {}
            if not (st_data.get("isReady") or st_data.get("authenticated")):
                return {"ok": False, "error": "WhatsApp desconectado"}
        except Exception:
            return {"ok": False, "error": "WhatsApp inacessível"}

        chat_id, found_name = await _resolve_wa_chat(client, contact)
        if not chat_id:
            return {"ok": False, "error": f"Contato '{contact}' não encontrado no WhatsApp"}

        r = await client.get(f"{WA_BASE}/chats/{chat_id}/messages", params={"limit": limit}, timeout=10.0)
        if r.status_code != 200:
            return {"ok": False, "error": f"Erro ao buscar mensagens (HTTP {r.status_code})"}

        msgs_raw = r.json()
        if isinstance(msgs_raw, dict):
            msgs_raw = msgs_raw.get("messages") or msgs_raw.get("data") or []

        formatted = []
        for m in (msgs_raw or []):
            body = m.get("body") or m.get("text") or m.get("content") or ""
            if not body or len(body) > 100 and " " not in body:
                continue  # filtra blobs base64
            sender = "Você" if m.get("fromMe") else (found_name or contact)
            formatted.append(f"[{sender}]: {body[:300]}")

        return {
            "ok": True,
            "contact": found_name or contact,
            "chat_id": chat_id,
            "messages": formatted,
            "count": len(formatted),
            "summary": f"{len(formatted)} mensagens com {found_name or contact}",
        }


async def exec_whatsapp_list_chats(args: Dict[str, Any]) -> Dict[str, Any]:
    name_filter = (args.get("name") or "").lower()
    limit = int(args.get("limit", 20))
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{WA_BASE}/chats", timeout=10.0)
            if r.status_code != 200:
                return {"ok": False, "error": f"Erro ao listar chats (HTTP {r.status_code})"}
            body = r.json()
            chats = body if isinstance(body, list) else (body.get("chats") or body.get("data") or [])
            if name_filter:
                # Busca flexível: aceita match se o filtro estiver no nome ou vice-versa
                # Também lida com variações comuns (removendo acentos/espaços extras se necessário)
                chats = [
                    c for c in chats 
                    if name_filter in (c.get("name") or "").lower() or (c.get("name") or "").lower() in name_filter
                ]
            result = [
                {"id": _chat_id_str(c), "name": c.get("name", ""), "unread": c.get("unreadCount", 0)}
                for c in chats[:limit]
            ]
            return {
                "ok": True,
                "chats": result,
                "count": len(result),
                "summary": f"{len(result)} chats" + (f" com '{name_filter}'" if name_filter else ""),
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def exec_pipedrive_get_org(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    org_name = args.get("org_name", "")
    try:
        from services.pipedrive.pipedrive_service import pipedrive_service
        match = None
        if org_id:
            match = await _pipedrive_get_org_by_id(org_id)
            
        if not match and org_name:
            match, resolved_id = await _pipedrive_find_org(org_name)
            if resolved_id:
                org_id = resolved_id
                
        if not match:
            return {"ok": False, "error": f"Organização '{org_name or org_id}' não encontrada"}

        details = await pipedrive_service.get_organization_details(org_id)
        deals, persons = [], []
        if isinstance(details, dict):
            for d in (details.get("deals") or [])[:5]:
                deals.append({
                    "id": d.get("id"),
                    "title": d.get("title", ""),
                    "status": d.get("status", ""),
                    "stage_id": d.get("stage_id"),
                    "value": d.get("value", 0),
                    "currency": d.get("currency", "BRL"),
                    "updated": (d.get("update_time") or "")[:10],
                })
            for p in (details.get("persons") or [])[:20]:
                phone_list = p.get("phone", [])
                email_list = p.get("email", [])
                phone = next((x.get("value") for x in phone_list if x.get("value")), None) if isinstance(phone_list, list) else None
                email = next((x.get("value") for x in email_list if x.get("value")), None) if isinstance(email_list, list) else None
                persons.append({"id": p.get("id"), "name": p.get("name", ""), "phone": phone, "email": email})

        deals_summary = (
            f"{len(deals)} deal(s): " + ", ".join(f"{d['title']} ({d['status']})" for d in deals)
            if deals else "Nenhum deal encontrado"
        )
        return {
            "ok": True,
            "org": match,
            "org_id": org_id,
            "deals": deals,
            "persons": persons,
            "summary": f"{match.get('name')} | {deals_summary} | {len(persons)} contato(s)",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def exec_pipedrive_get_persons(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    org_name = args.get("org_name", "")
    try:
        from services.pipedrive.pipedrive_service import pipedrive_service
        match = None
        if org_id:
            match = await _pipedrive_get_org_by_id(org_id)
            
        if not match and org_name:
            match, resolved_id = await _pipedrive_find_org(org_name)
            if resolved_id:
                org_id = resolved_id
                
        if not match:
            return {"ok": False, "error": f"Organização '{org_name or org_id}' não encontrada"}

        details = await pipedrive_service.get_organization_details(org_id)
        persons = details.get("persons", []) if isinstance(details, dict) else []
        result = []
        for p in persons[:30]:
            phone_list = p.get("phone", [])
            email_list = p.get("email", [])
            phone = next((x.get("value") for x in phone_list if x.get("value")), None) if isinstance(phone_list, list) else None
            email = next((x.get("value") for x in email_list if x.get("value")), None) if isinstance(email_list, list) else None
            channels = [c for c, v in [("WhatsApp", phone), ("Email", email)] if v]
            result.append({
                "id": p.get("id"),
                "name": p.get("name", ""),
                "phone": phone,
                "email": email,
                "role": p.get("job_title", ""),
                "channels": channels,
                "source": "Pipedrive"
            })

        # 🚀 INTEGRATION: Busca no banco local (Hierarchy Mapper) por funcionários vinculados à organização
        try:
            from core.database import async_session
            from models.organization import Organization
            from models.employee import Employee
            from sqlalchemy import select
            
            async with async_session() as session:
                stmt = select(Organization).where((Organization.id == org_id) | (Organization.pipedrive_id == org_id))
                res = await session.execute(stmt)
                local_org = res.scalar_one_or_none()
                
                if local_org:
                    stmt_emp = select(Employee).where(Employee.company_id == local_org.id)
                    res_emp = await session.execute(stmt_emp)
                    local_employees = res_emp.scalars().all()
                    
                    internal_noise = ["pcp", "rh", "financeiro", "comercial", "adm", "nfe", "qualidade", "faturamento", "fabrica", "processos", "allcompany", "intranet"]
                    internal_domains = ["jferres.com.br"]
                    personal_domains = ["gmail.com", "hotmail.com", "yahoo.com", "yahoo.com.br", "outlook.com", "live.com", "icloud.com", "uol.com.br", "bol.com.br"]
                    own_emails = ["joaoluccas637@gmail.com", "clicheval@hotmail.com", "joao.moura@jferres.com.br"]
                    
                    for emp in local_employees:
                        emp_email = (emp.email or "").lower()
                        is_noise = any(noise in emp_email or noise in emp.name.lower() for noise in internal_noise)
                        is_internal_domain = any(dom in emp_email for dom in internal_domains)
                        is_personal_domain = any(dom in emp_email for dom in personal_domains)
                        is_own_email = emp_email in own_emails
                        
                        if is_noise or is_internal_domain or is_personal_domain or is_own_email:
                            continue
                            
                        if not any((p.get("name") or "").lower() == emp.name.lower() for p in result):
                            phone = emp.whatsapp_number or emp.phone
                            channels = [c for c, v in [("WhatsApp", phone), ("Email", emp.email)] if v]
                            result.append({
                                "id": None,
                                "name": emp.name,
                                "phone": phone,
                                "email": emp.email,
                                "role": emp.department or "Contato Banco Local",
                                "channels": channels,
                                "source": "Banco Local"
                            })
        except Exception as db_err:
            pass

        # 🚀 INTEGRATION: Busca no WhatsApp por contatos que combinem com o nome da organização
        org_real_name = match.get("name", org_name)
        if org_real_name and len(org_real_name) > 2:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    # 1. Tenta buscar nos chats ativos (mais resiliente, funciona mesmo com isReady=false)
                    chats_resp = await client.get(f"http://localhost:8001/api/whatsapp/chats")
                    if chats_resp.status_code == 200:
                        body = chats_resp.json()
                        all_chats = body if isinstance(body, list) else (body.get("chats") or body.get("data") or [])
                        term = org_real_name.lower()
                        for c in all_chats:
                            c_name = c.get("name")
                            if c_name and term in c_name.lower():
                                if not any((p.get("name") or "").lower() == c_name.lower() for p in result):
                                    phone = c.get("id", "").split("@")[0] or c.get("number")
                                    result.append({
                                        "id": None,
                                        "name": c_name,
                                        "phone": phone,
                                        "email": None,
                                        "role": "Contato WhatsApp",
                                        "channels": ["WhatsApp"],
                                        "source": "WhatsApp (Chat Ativo)"
                                    })

                    # 2. Tenta buscar via busca geral de contatos (se disponível)
                    wa_url = f"http://localhost:8001/api/whatsapp/contacts/search?name={org_real_name}"
                    search_resp = await client.get(wa_url)
                    if search_resp.status_code == 200:
                        wa_contacts = search_resp.json()
                        wa_list = wa_contacts if isinstance(wa_contacts, list) else wa_contacts.get("contacts") or []
                        for wc in wa_list[:5]:
                            wc_name = wc.get("name")
                            if wc_name:
                                if not any((p.get("name") or "").lower() == wc_name.lower() for p in result):
                                    phone = wc.get("id", "").split("@")[0] or wc.get("number")
                                    result.append({
                                        "id": None,
                                        "name": wc_name,
                                        "phone": phone,
                                        "email": None,
                                        "role": "Contato WhatsApp",
                                        "channels": ["WhatsApp"],
                                        "source": "WhatsApp (Não vinculado)"
                                    })
            except Exception as wa_err:
                pass

        return {
            "ok": True,
            "org": match.get("name"),
            "persons": result,
            "count": len(result),
            "summary": (
                f"{len(result)} contatos em {match.get('name')}: "
                + ", ".join(f"{p['name']} ({', '.join(p['channels']) or 'sem canal'})" for p in result[:4])
            ),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def exec_pipedrive_get_activities(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    org_name = args.get("org_name", "")
    try:
        from services.pipedrive.pipedrive_service import pipedrive_service
        match = None
        if org_id:
            match = await _pipedrive_get_org_by_id(org_id)
            
        if not match and org_name:
            match, resolved_id = await _pipedrive_find_org(org_name)
            if resolved_id:
                org_id = resolved_id
                
        if not match:
            return {"ok": False, "error": f"Organização '{org_name or org_id}' não encontrada"}
        details = await pipedrive_service.get_organization_details(org_id)
        activities = details.get("activities", []) if isinstance(details, dict) else []
        pending = [
            {"id": a.get("id"), "subject": a.get("subject"), "type": a.get("type"),
             "due_date": a.get("due_date"), "note": (a.get("note") or "")[:100]}
            for a in activities if not a.get("done")
        ]
        done = [a for a in activities if a.get("done")]
        return {
            "ok": True,
            "org": match.get("name"),
            "pending": pending[:10],
            "done_count": len(done),
            "count": len(pending),
            "summary": f"{len(pending)} atividades pendentes para {match.get('name')}",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def exec_pipedrive_get_deals(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    org_name = args.get("org_name", "")
    try:
        from services.pipedrive.pipedrive_service import pipedrive_service
        match = None
        if org_id:
            match = await _pipedrive_get_org_by_id(org_id)
            
        if not match and org_name:
            match, resolved_id = await _pipedrive_find_org(org_name)
            if resolved_id:
                org_id = resolved_id
                
        if not match:
            return {"ok": False, "error": f"Organização '{org_name or org_id}' não encontrada"}
        details = await pipedrive_service.get_organization_details(org_id)
        deals = details.get("deals", []) if isinstance(details, dict) else []
        formatted = [
            {
                "id": d.get("id"),
                "title": d.get("title", ""),
                "status": d.get("status", ""),
                "stage_id": d.get("stage_id"),
                "value": d.get("value", 0),
                "currency": d.get("currency", "BRL"),
                "updated": (d.get("update_time") or "")[:10],
                "notes": [n.get("content", "")[:500] for n in (details.get("notes") or [])[:5]],
            }
            for d in deals[:10]
        ]
        if not formatted:
            return {"ok": True, "deals": [], "count": 0, "summary": f"Nenhum deal encontrado para {match.get('name')}"}
        summary = f"{len(formatted)} deal(s) em {match.get('name')}: " + ", ".join(
            f"{d['title']} ({d['status']})" for d in formatted[:3]
        )
        return {"ok": True, "org": match.get("name"), "org_id": org_id, "deals": formatted, "count": len(formatted), "summary": summary}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def exec_pipedrive_get_all_activities(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from services.pipedrive.pipedrive_service import pipedrive_service
        from datetime import date
        today = date.today().isoformat()
        r = await pipedrive_service.make_request("GET", f"activities?user_id={pipedrive_service.user_id}&done=0&limit=500")
        if not r or r.status_code != 200:
            return {"ok": False, "error": "Erro ao buscar atividades do Pipedrive"}
        activities = r.json().get("data") or []
        today_acts, overdue_acts = [], []
        for act in activities:
            due = act.get("due_date", "")
            if not due:
                continue
            raw_org = act.get("org_id")
            org_name = raw_org.get("name", "") if isinstance(raw_org, dict) else ""
            entry = {
                "id": act.get("id"),
                "subject": act.get("subject", ""),
                "type": act.get("type", ""),
                "org": org_name,
                "due_date": due,
                "note": (act.get("note") or "")[:80],
            }
            if due == today:
                today_acts.append(entry)
            elif due < today:
                overdue_acts.append(entry)
        return {
            "ok": True,
            "today": today_acts,
            "overdue": overdue_acts,
            "all": (overdue_acts + today_acts)[:20],
            "count_today": len(today_acts),
            "count_overdue": len(overdue_acts),
            "summary": f"{len(today_acts)} atividades para hoje, {len(overdue_acts)} atrasadas",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def exec_email_get_inbox(args: Dict[str, Any]) -> Dict[str, Any]:
    limit = int(args.get("limit", 15))
    from_name = (args.get("from_name") or "").lower()
    max_retries = 2
    
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(f"{EMAIL_SERVICE_BASE}/messages", params={"folder": "Inbox", "limit": limit * 3})
                if r.status_code != 200:
                    return {"ok": False, "error": f"Serviço de e-mail indisponível (HTTP {r.status_code})"}
                messages = r.json().get("messages", [])
                if from_name:
                    messages = [m for m in messages if from_name in (m.get("sender", "") + m.get("to", "")).lower()]
                results = [
                    {
                        "from": m.get("sender", ""),
                        "to": m.get("to", ""),
                        "subject": m.get("subject", ""),
                        "date": (m.get("date") or "")[:10],
                        "preview": (m.get("body") or "")[:300].strip(),
                        "entryId": m.get("entryId", ""),
                    }
                    for m in messages[:limit]
                ]
                return {"ok": True, "emails": results, "count": len(results), "summary": f"{len(results)} e-mails encontrados"}
        except httpx.TimeoutException as e:
            if attempt < max_retries:
                import asyncio
                await asyncio.sleep(1)  # Backoff rápido: 1s
                continue
            return {"ok": False, "error": f"Timeout ao acessar serviço de e-mail (tentativa {attempt}/{max_retries}): {e}"}
        except Exception as e:
            if attempt < max_retries:
                import asyncio
                await asyncio.sleep(1)
                continue
            return {"ok": False, "error": f"Erro ao acessar e-mail (tentativa {attempt}/{max_retries}): {e}"}


async def _extract_org_domain(org_name: str, org_id: int | None = None) -> str | None:
    """Busca o domínio de e-mail de uma empresa no banco local ou no Pipedrive."""
    try:
        from core.database import async_session
        from models.organization import Organization
        from sqlalchemy import select

        match = None
        if not org_id and org_name:
            match, org_id = await _pipedrive_find_org(org_name)

        if not org_id:
            return None

        # 1. Tenta buscar o domínio salvo localmente na tabela organizations pelo Pipedrive ID
        async with async_session() as session:
            stmt = select(Organization.domain).where(Organization.pipedrive_id == org_id)
            result = await session.execute(stmt)
            domain = result.scalar()
            if domain:
                return domain.lower().replace("www.", "").strip()

        # 2. Verifica o campo domain do próprio org no Pipedrive (ex: "apice.com.br")
        if match is None:
            match = await _pipedrive_get_org_by_id(org_id)
        if match:
            pd_domain = (match.get("domain") or "").lower().replace("www.", "").strip()
            if pd_domain and not pd_domain.endswith(JFERRES_DOMAIN):
                return pd_domain

        # 3. Fallback: Busca via contatos no Pipedrive
        from services.pipedrive.pipedrive_service import pipedrive_service
        details = await pipedrive_service.get_organization_details(org_id)
        for p in (details.get("persons") or []):
            for em in (p.get("email") or []):
                val = (em.get("value") or "").strip()
                if val and "@" in val and not val.endswith(JFERRES_DOMAIN):
                    return val.split("@")[1].lower()
    except Exception:
        pass
    return None


async def exec_email_get_contact_history(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    contact_name = (args.get("contact_name") or "").lower()
    contact_email = (args.get("contact_email") or "").lower()
    org_name = (args.get("org_name") or "").strip()
    explicit_domain = (args.get("domain") or "").strip().lower().replace("www.", "").replace("http://", "").replace("https://", "")
    limit = int(args.get("limit", 25))
    term = contact_name or contact_email or explicit_domain
    if not term and not org_name and not org_id:
        return {"ok": False, "error": "Informe contact_name, contact_email, domain, org_name ou org_id"}
    
    max_retries = 2
    
    for attempt in range(1, max_retries + 1):
        try:
            # 1. Determinar o domínio se não houver email
            domain = explicit_domain
            if not domain:
                if contact_email and "@" in contact_email:
                    domain = contact_email.split("@")[1].lower()
                elif org_name or org_id:
                    domain = await _extract_org_domain(org_name, org_id=org_id)
                elif contact_name:
                    domain = await _extract_org_domain(contact_name, org_id=org_id)

            search_query = contact_email or contact_name
            if not search_query:
                if domain and domain != JFERRES_DOMAIN:
                    search_query = f"@{domain}"
                else:
                    import unicodedata
                    import re
                    # Remove acentos
                    clean_org = ''.join(c for c in unicodedata.normalize('NFD', org_name) if unicodedata.category(c) != 'Mn').lower()
                    words = re.findall(r'\b\w+\b', clean_org)
                    stopwords = {"grupo", "cia", "ltda", "sistemas", "comercio", "industria", "servicos"}
                    first_word = next((w for w in words if len(w) > 2 and w not in stopwords), words[0] if words else org_name)
                    search_query = first_word

            if not search_query:
                return {"ok": False, "error": "Não foi possível determinar um termo de busca válido"}

            # Calcula fallback por primeira palavra do org_name (usado se busca por domínio retornar 0)
            _fallback_query = None
            if org_name and search_query.startswith("@"):
                import unicodedata as _uc_fb
                import re as _re_fb
                _clean = "".join(c for c in _uc_fb.normalize("NFD", org_name) if _uc_fb.category(c) != "Mn").lower()
                _words = _re_fb.findall(r"\b\w+\b", _clean)
                _sw = {"grupo", "cia", "ltda", "sistemas", "comercio", "industria", "servicos", "energia", "eletrica"}
                _fallback_query = next((w for w in _words if len(w) > 3 and w not in _sw), _words[0] if _words else None)

            async with httpx.AsyncClient(timeout=30.0) as client:
                # Fazemos a busca direto na API passando a query para não carregar emails velhos à toa
                inbox_r = await client.get(f"{EMAIL_SERVICE_BASE}/messages", params={"folder": "Inbox", "limit": limit * 2, "q": search_query})
                sent_r  = await client.get(f"{EMAIL_SERVICE_BASE}/messages", params={"folder": "Itens Enviados", "limit": limit * 2, "q": search_query})

                all_messages = []
                for resp in [inbox_r, sent_r]:
                    if resp.status_code == 200:
                        all_messages.extend(resp.json().get("messages", []))

                # Retry com primeira palavra do nome da empresa se busca por domínio não achou nada
                if not all_messages and _fallback_query and _fallback_query != search_query:
                    inbox_fb = await client.get(f"{EMAIL_SERVICE_BASE}/messages", params={"folder": "Inbox", "limit": limit * 2, "q": _fallback_query})
                    sent_fb  = await client.get(f"{EMAIL_SERVICE_BASE}/messages", params={"folder": "Itens Enviados", "limit": limit * 2, "q": _fallback_query})
                    for resp in [inbox_fb, sent_fb]:
                        if resp.status_code == 200:
                            all_messages.extend(resp.json().get("messages", []))
                    if all_messages:
                        search_query = _fallback_query  # atualiza para o summary refletir a busca que achou

                        # Descobre domínio real pelos remetentes encontrados e salva no banco
                        discovered_domain = None
                        for _m in all_messages[:10]:
                            _sender = (_m.get("sender") or "").lower()
                            if "@" in _sender and not _sender.endswith(JFERRES_DOMAIN):
                                _d = _sender.split("@")[-1].split(">")[0].strip()
                                if _d and "." in _d:
                                    discovered_domain = _d
                                    break

                        if discovered_domain and org_id:
                            try:
                                from core.database import async_session
                                from models.organization import Organization
                                from models.employee import Employee
                                from sqlalchemy import select, update
                                old_domain = search_query.lstrip("@")  # domínio que falhou
                                async with async_session() as session:
                                    # 1. Atualiza o domínio da organização
                                    await session.execute(
                                        update(Organization)
                                        .where(Organization.pipedrive_id == org_id)
                                        .values(domain=discovered_domain)
                                    )
                                    # 2. Descobre o id local da organização
                                    result = await session.execute(
                                        select(Organization.id).where(Organization.pipedrive_id == org_id)
                                    )
                                    local_org_id = result.scalar()
                                    # 3. Atualiza emails dos employees com o domínio antigo
                                    if local_org_id and old_domain and old_domain != discovered_domain:
                                        emps = await session.execute(
                                            select(Employee.id, Employee.email)
                                            .where(Employee.company_id == local_org_id)
                                            .where(Employee.email.ilike(f"%@{old_domain}"))
                                        )
                                        for emp_id, emp_email in emps.all():
                                            new_email = emp_email.replace(f"@{old_domain}", f"@{discovered_domain}")
                                            await session.execute(
                                                update(Employee)
                                                .where(Employee.id == emp_id)
                                                .values(email=new_email)
                                            )
                                    await session.commit()
                            except Exception:
                                pass

            if not all_messages:
                label = contact_name or contact_email or org_name
                return {
                    "ok": True,
                    "contact": label,
                    "emails": [],
                    "count": 0,
                    "summary": f"0 e-mails encontrados para {label} (busca: {search_query})",
                }

            # Ordenar e formatar (removendo duplicados por segurança)
            seen_ids = set()
            unique_messages = []
            for m in all_messages:
                eid = m.get("entryId", "")
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    unique_messages.append(m)

            unique_messages.sort(key=lambda m: m.get("date") or "", reverse=True)
            results = [
                {
                    "from": m.get("sender", ""),
                    "to": m.get("to", ""),
                    "subject": m.get("subject", ""),
                    "date": (m.get("date") or "")[:10],
                    "preview": (m.get("body") or "")[:200].strip(),
                    "entryId": m.get("entryId", ""),
                    "direction": "sent" if JFERRES_DOMAIN in (m.get("sender") or "").lower() else "received",
                }
                for m in unique_messages[:10]
            ]

            label = contact_name or contact_email or org_name
            return {
                "ok": True,
                "contact": label,
                "domain": domain,
                "emails": results,
                "count": len(results),
                "summary": f"{len(results)} e-mails encontrados para {label}",
            }
        except httpx.TimeoutException as e:
            if attempt < max_retries:
                import asyncio
                await asyncio.sleep(1)  # Backoff rápido: 1s
                continue
            # Fallback: tentar email_get_inbox com filtro
            if contact_name:
                return await exec_email_get_inbox({"from_name": contact_name, "limit": limit})
            return {"ok": False, "error": f"Timeout ao acessar serviço de e-mail (tentativa {attempt}/{max_retries}): {e}"}
        except Exception as e:
            if attempt < max_retries:
                import asyncio
                await asyncio.sleep(1)
                continue
            # Fallback: tentar email_get_inbox com filtro
            if contact_name:
                return await exec_email_get_inbox({"from_name": contact_name, "limit": limit})
            return {"ok": False, "error": f"Erro ao acessar e-mail (tentativa {attempt}/{max_retries}): {e}"}


async def exec_web_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query", "")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                timeout=10.0,
                follow_redirects=True,
            )
            data = r.json()
            abstract = data.get("AbstractText", "")
            related = [t.get("Text", "") for t in data.get("RelatedTopics", [])[:3] if t.get("Text")]
            result_text = abstract or " | ".join(related) or "Nenhum resultado encontrado"
            return {"ok": True, "result": result_text, "summary": result_text[:150]}
    except Exception as e:
        return {"ok": False, "error": f"Erro na busca: {e}"}


async def exec_generate_dossier(args: dict) -> dict:
    """Sinaliza a fase de consolidação. Não faz chamada externa — apenas libera o agente para gerar o dossiê."""
    return {
        "ok": True,
        "summary": "Consolidação iniciada. Gere o dossiê final agora.",
    }


async def exec_suggest_next_actions(args: dict, messages: list | None = None, org_id: int | None = None) -> dict:
    if messages:
        try:
            from services.ai.sales_strategy_service import sales_strategy_service
            strategy_res = await sales_strategy_service.analyze_and_suggest_actions(messages, org_id)
            if strategy_res and strategy_res.get("ok"):
                return {
                    "ok": True,
                    "actions": strategy_res.get("actions", []),
                    "summary": strategy_res.get("summary", "")
                }
        except Exception as e:
            # Fallback to default raw actions if service fails
            pass

    raw_actions = args.get("actions", [])
    normalized = []
    for act in raw_actions:
        if isinstance(act, str):
            normalized.append({"label": act, "prompt": act})
        elif isinstance(act, dict):
            label = act.get("label") or act.get("text") or act.get("title") or act.get("titulo") or act.get("name") or ""
            prompt = act.get("prompt") or act.get("instruction") or act.get("message") or act.get("cmd") or act.get("comando") or ""
            label = str(label).strip()
            prompt = str(prompt).strip()
            if not label and prompt:
                label = prompt
            if not prompt and label:
                prompt = label
            if label or prompt:
                normalized.append({"label": label, "prompt": prompt})
    return {"ok": True, "actions": normalized, "summary": f"{len(normalized)} ações sugeridas para aprovação do usuário."}

# ─── Registry ─────────────────────────────────────────────────────────────────

TOOLS: Dict[str, Dict[str, Any]] = {
    # ── WhatsApp ──────────────────────────────────────────────────────────────
    "whatsapp_get_messages": {
        "description": "Busca mensagens recentes do WhatsApp de um contato. Pode ser usado com o nome da PESSOA FÍSICA ou com o nome da EMPRESA (organização). É a ferramenta principal para histórico de conversa no WhatsApp.",
        "args_schema": {"contact": "string (nome da pessoa ou da empresa)", "limit": "int (padrão 35)"},
        "type": "read",
        "executor": exec_whatsapp_get_messages,
    },
    "whatsapp_list_chats": {
        "description": "Lista chats do WhatsApp por nome. Use APENAS quando não souber o nome exato do contato. NÃO use para buscar histórico de um contato já identificado — para isso use whatsapp_get_messages.",
        "args_schema": {"name": "string opcional (filtrar por nome)", "limit": "int (padrão 20)"},
        "type": "read",
        "executor": exec_whatsapp_list_chats,
    },
    "whatsapp_send_message": {
        "description": "Envia uma mensagem WhatsApp para um contato. Requer confirmação. Escreva mensagens profissionais e contextualizadas.",
        "args_schema": {
            "contact": "string (nome do contato como aparece no WhatsApp)",
            "message": "string (texto completo da mensagem — escreva de forma profissional e personalizada)",
            "contact_name": "string opcional (nome para o log de atividade)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"WhatsApp para {args.get('contact')}: \"{args.get('message', '')[:80]}\"",
    },

    # ── Email ──────────────────────────────────────────────────────────────────
    "email_get_inbox": {
        "description": "Busca e-mails recentes da caixa de entrada geral. PROIBIDO usar para investigar e-mails de uma empresa específica ou contato — para isso, é OBRIGATÓRIO usar email_get_contact_history.",
        "args_schema": {"limit": "int (padrão 5)", "from_name": "string opcional (nome ou domínio do remetente)"},
        "type": "read",
        "executor": exec_email_get_inbox,
    },
    "email_get_contact_history": {
        "description": "Busca TODO o histórico de e-mails (caixa de entrada e enviados). ÚNICA ferramenta permitida para investigar e-mails de uma empresa ou contato. IMPORTANTE: Se a empresa NÃO tiver contatos cadastrados, você DEVE chamar esta ferramenta passando o 'domain' (se souber) ou o 'org_name' para buscar e-mails da empresa.",
        "args_schema": {
            "contact_name": "string opcional (nome do contato)",
            "contact_email": "string opcional (e-mail do contato)",
            "org_name": "string opcional (nome da empresa — fallback se não tiver contatos)",
            "domain": "string opcional (domínio do site/email da empresa. Ex: 'empresa.com.br')",
            "limit": "int (padrão 25)",
        },
        "type": "read",
        "executor": exec_email_get_contact_history,
    },
    "email_send": {
        "description": "Envia um e-mail NOVO para um destinatário. Requer confirmação. Use email_reply para responder a um thread existente.",
        "args_schema": {
            "to": "string (e-mail do destinatário)",
            "subject": "string (assunto do e-mail)",
            "body": "string (corpo completo — escreva profissionalmente com saudação e assinatura)",
            "contact_name": "string opcional (nome do destinatário para o log)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"E-mail para {args.get('to')} — {args.get('subject', '')}",
    },
    "email_reply": {
        "description": "Responde a um e-mail existente usando o entryId. Prefira este ao email_send quando houver thread ativo. Requer confirmação.",
        "args_schema": {
            "entry_id": "string (entryId do e-mail original, obtido via email_get_contact_history ou email_get_inbox)",
            "body": "string (corpo da resposta — profissional, sem repetir o assunto original)",
            "subject": "string opcional (assunto original para contexto no log)",
            "contact_name": "string opcional (nome do destinatário para o log)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Responder e-mail de {args.get('contact_name', 'contato')}: \"{args.get('body', '')[:80]}\"",
    },

    # ── Pipedrive ──────────────────────────────────────────────────────────────
    "pipedrive_get_org": {
        "description": "Busca dados completos de uma organização no Pipedrive: cadastro, todos os deals e primeiros contatos. Use SEMPRE como ponto de partida ao analisar qualquer empresa.",
        "args_schema": {"org_name": "string (nome da empresa)"},
        "type": "read",
        "executor": exec_pipedrive_get_org,
    },
    "pipedrive_get_persons": {
        "description": "Busca todos os contatos (pessoas) de uma organização no Pipedrive com telefone, e-mail e canais disponíveis. Use para identificar com quem falar.",
        "args_schema": {"org_name": "string (nome da empresa)"},
        "type": "read",
        "executor": exec_pipedrive_get_persons,
    },
    "pipedrive_get_deals": {
        "description": "Busca deals de uma organização com detalhes: título, status, valor, etapa e notas recentes. Use para entender o estado comercial.",
        "args_schema": {"org_name": "string (nome da empresa)"},
        "type": "read",
        "executor": exec_pipedrive_get_deals,
    },
    "pipedrive_get_activities": {
        "description": "Busca atividades e tarefas pendentes de uma organização específica no Pipedrive.",
        "args_schema": {"org_name": "string (nome da empresa)"},
        "type": "read",
        "executor": exec_pipedrive_get_activities,
    },
    "pipedrive_get_all_activities": {
        "description": "Busca TODAS as atividades pendentes do Pipedrive (hoje + atrasadas) de TODAS as empresas. Use APENAS quando o usuário perguntar sobre agenda geral, tarefas do dia ou follow-ups de todas as empresas. NUNCA use durante a investigação específica de uma empresa — para isso use pipedrive_get_activities com o nome da empresa.",
        "args_schema": {},
        "type": "read",
        "executor": exec_pipedrive_get_all_activities,
    },
    "pipedrive_update_deal": {
        "description": "Atualiza campos de um deal no Pipedrive (stage_id, status, value etc.). Requer confirmação.",
        "args_schema": {
            "deal_id": "int (ID do deal)",
            "fields": "dict (campos a atualizar, ex: {\"stage_id\": 5, \"status\": \"won\"})",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Atualizar deal #{args.get('deal_id')} → {args.get('fields')}",
    },
    "pipedrive_create_task": {
        "description": "Cria uma nova atividade/tarefa no Pipedrive vinculada a um deal ou empresa. Requer confirmação.",
        "args_schema": {
            "subject": "string (título da tarefa)",
            "type": "string (call | meeting | task | deadline — use 'call' para ligações, 'task' para tarefas genéricas)",
            "due_date": "string (data no formato YYYY-MM-DD)",
            "note": "string opcional (descrição ou instruções)",
            "deal_id": "int opcional (ID do deal — preferível se souber)",
            "org_name": "string opcional (nome da empresa — usado para resolver o deal se deal_id não for fornecido)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Criar tarefa: '{args.get('subject')}' ({args.get('type', 'task')}) em {args.get('due_date', 'sem data')}",
    },
    "pipedrive_update_task": {
        "description": "Atualiza ou conclui uma atividade existente no Pipedrive. Requer confirmação.",
        "args_schema": {
            "activity_id": "int (ID da atividade)",
            "done": "bool opcional (true para marcar como concluída)",
            "due_date": "string opcional (reagendar — formato YYYY-MM-DD)",
            "note": "string opcional (atualizar descrição)",
            "subject": "string opcional (novo título)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: (
            f"Concluir atividade #{args.get('activity_id')}" if args.get("done")
            else f"Atualizar atividade #{args.get('activity_id')}"
        ),
    },
    "pipedrive_create_note": {
        "description": "Adiciona uma nota a um deal no Pipedrive. Use para registrar decisões, informações importantes ou resumo de conversas. Requer confirmação.",
        "args_schema": {
            "deal_id": "int (ID do deal)",
            "content": "string (texto da nota — seja descritivo e objetivo)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Criar nota no deal #{args.get('deal_id')}: \"{args.get('content', '')[:60]}\"",
    },
    "pipedrive_create_person": {
        "description": "Cria um novo contato (pessoa) no Pipedrive vinculado a uma organização. Requer confirmação.",
        "args_schema": {
            "name": "string (nome completo do contato)",
            "email": "string opcional (endereço de e-mail)",
            "phone": "string opcional (número de telefone)",
            "org_id": "int opcional (ID da organização no Pipedrive)",
            "org_name": "string opcional (nome da empresa para vincular)",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: f"Adicionar contato: '{args.get('name')}'" + (f" na empresa '{args.get('org_name')}'" if args.get("org_name") else ""),
    },

    # ── Consolidação ──────────────────────────────────────────────────────────
    "generate_dossier": {
        "description": (
            "Chame esta ferramenta UMA VEZ, após ter esgotado TODAS as fontes "
            "(Pipedrive + WhatsApp + Email de todos os contatos + busca por empresa). "
            "Ela sinaliza o início da consolidação. No turno seguinte, gere o dossiê final completo."
        ),
        "args_schema": {},
        "type": "read",
        "executor": exec_generate_dossier,
    },
    "suggest_next_actions": {
        "description": "Gere botões de ação estruturados baseados nas informações reais encontradas. Chame esta ferramenta NA MESMA VEZ que gerar ou entregar o Dossiê Final. Cada item será um botão que o usuário pode aprovar e você vai executar usando as informações/IDs encontrados.",
        "args_schema": {
            "actions": "array de objetos contendo chaves: 'label' (Texto curto do botão, ex: 'Concluir atividade ID 123'), 'prompt' (Instrução detalhada que será enviada de volta pra você pedindo para executar a ação, ex: 'Use pipedrive_update_task na atividade 123 com done=true')"
        },
        "type": "read",
        "executor": exec_suggest_next_actions,
    },

    # ── Web ────────────────────────────────────────────────────────────────────
    "web_search_external": {
        "description": "Pesquisa informações EXTERNAS na internet (notícias, mercado, concorrentes). PROIBIDO usar durante investigação de uma empresa específica. PROIBIDO usar para buscar dados de negócios, deals, contatos ou histórico de comunicação — use as ferramentas Pipedrive/WhatsApp/Email para isso.",
        "args_schema": {"query": "string (termos de busca)"},
        "type": "read",
        "executor": exec_web_search,
    },
}


# ─── Schema para API Anthropic ────────────────────────────────────────────────

def get_tools_anthropic_schema() -> list:
    """Gera o schema no formato Anthropic/Claude para todas as ferramentas."""
    schemas = []
    for name, meta in TOOLS.items():
        args = meta.get("args_schema", {})
        properties: dict = {}
        required: list = []

        for k, desc in args.items():
            desc_lower = desc.lower()
            # Mapeamento de tipos mais robusto
            if "int" in desc_lower:
                prop_type = "integer"
            elif "bool" in desc_lower:
                prop_type = "boolean"
            elif "array" in desc_lower:
                prop_type = "array"
            elif "dict" in desc_lower or "object" in desc_lower or "campos" in desc_lower:
                prop_type = "object"
            else:
                prop_type = "string"

            if prop_type == "array":
                properties[k] = {"type": "array", "items": {"type": "object"}, "description": desc}
            else:
                properties[k] = {"type": prop_type, "description": desc}
            
            # Se não for opcional e não tiver padrão, é obrigatório
            # Exception: 'limit' e 'contact_name'/'org_name' em buscas flexíveis
            is_optional = "opcional" in desc_lower or "padrão" in desc_lower or "optional" in desc_lower
            if not is_optional and k != "limit":
                required.append(k)

        schema: dict = {
            "name": name,
            "description": meta["description"],
            "input_schema": {
                "type": "object",
                "properties": properties,
            },
        }
        if required:
            schema["input_schema"]["required"] = required
            
        schemas.append(schema)
    return schemas


# ─── Executor de ferramentas de ESCRITA (após confirmação) ────────────────────

async def execute_write_tool(tool_name: str, args: Dict[str, Any], org_id=None) -> Dict[str, Any]:
    """Executa uma ferramenta de escrita após confirmação do usuário."""

    # ── WhatsApp ──────────────────────────────────────────────────────────────
    if tool_name == "whatsapp_send_message":
        contact = args.get("contact", "")
        message = args.get("message", "")
        async with httpx.AsyncClient() as client:
            chat_id, found_name = await _resolve_wa_chat(client, contact)
            if not chat_id:
                return {"ok": False, "error": f"Contato '{contact}' não encontrado"}
            number = chat_id.split("@")[0] if "@" in chat_id else chat_id
            r = await client.post(f"{WA_BASE}/send", json={"number": number, "message": message}, timeout=20.0)
            ok = r.status_code == 200
            if ok:
                await _log_activity_bg(
                    "whatsapp_sent",
                    {"to_name": args.get("contact_name") or found_name or contact, "to_phone": number, "message_preview": message[:200]},
                    org_id=org_id,
                )
            return {"ok": ok, "result": "Mensagem enviada" if ok else f"Erro {r.status_code}: {r.text[:100]}"}

    # ── Email: envio novo ──────────────────────────────────────────────────────
    elif tool_name == "email_send":
        to = args.get("to", "")
        subject = args.get("subject", "")
        body = args.get("body", "")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(f"{EMAIL_SERVICE_BASE}/send", json={"to": to, "subject": subject, "body": body})
                ok = r.status_code in (200, 201, 202)
                if ok:
                    await _log_activity_bg(
                        "email_sent",
                        {"to_name": args.get("contact_name", to), "to_email": to, "subject": subject, "message_preview": body[:200]},
                        org_id=org_id,
                        status="awaiting_reply",
                    )
                return {"ok": ok, "result": f"E-mail enviado para {to}" if ok else f"Falha (HTTP {r.status_code})"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Email: resposta ────────────────────────────────────────────────────────
    elif tool_name == "email_reply":
        entry_id = args.get("entry_id", "")
        body = args.get("body", "")
        if not entry_id or not body:
            return {"ok": False, "error": "entry_id e body são obrigatórios"}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    f"{EMAIL_SERVICE_BASE}/reply",
                    json={"entry_id": entry_id, "body": body, "reply_all": True},
                )
                ok = r.status_code in (200, 201, 202)
                if ok:
                    await _log_activity_bg(
                        "email_reply_sent",
                        {
                            "to_name": args.get("contact_name", "Contato"),
                            "subject": args.get("subject", "Re: resposta"),
                            "message_preview": body[:200],
                            "is_reply": True,
                        },
                        org_id=org_id,
                        status="completed",
                    )
                return {"ok": ok, "result": "Resposta enviada" if ok else f"Falha (HTTP {r.status_code})"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: atualizar deal ──────────────────────────────────────────────
    elif tool_name == "pipedrive_update_deal":
        deal_id = args.get("deal_id")
        fields = args.get("fields", {})
        try:
            from services.pipedrive.pipedrive_service import pipedrive_service
            result = await pipedrive_service.update_deal(int(deal_id), fields)
            ok = result.get("success", False)
            if ok:
                try:
                    await pipedrive_service.make_request(
                        "POST", "notes",
                        json={"content": f"✅ Deal atualizado via Assistente V2.\nAlterações: {json.dumps(fields, ensure_ascii=False)}", "deal_id": deal_id}
                    )
                except Exception:
                    pass
            return {"ok": ok, "result": "Deal atualizado" if ok else f"Erro: {result.get('error', 'desconhecido')}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: criar tarefa ────────────────────────────────────────────────
    elif tool_name == "pipedrive_create_task":
        subject = args.get("subject", "Atividade")
        task_type = args.get("type", "task")
        due_date = args.get("due_date", "")
        note = args.get("note", "")
        deal_id = args.get("deal_id")
        org_name = args.get("org_name", "")

        type_map = {"tarefa": "task", "ligação": "call", "ligar": "call", "reunião": "meeting", "prazo": "deadline"}
        task_type = type_map.get(task_type.lower(), task_type)

        try:
            from services.pipedrive.pipedrive_service import pipedrive_service
            pd_org_id = org_id
            if not deal_id and (org_name or pd_org_id):
                if not pd_org_id and org_name:
                    match, pd_org_id = await _pipedrive_find_org(org_name)
                if pd_org_id:
                    details = await pipedrive_service.get_organization_details(pd_org_id)
                    deals = details.get("deals", []) if isinstance(details, dict) else []
                    open_deal = next((d for d in deals if d.get("status") == "open"), deals[0] if deals else None)
                    if open_deal:
                        deal_id = open_deal.get("id")

            data: dict = {"subject": subject, "type": task_type, "note": note}
            if deal_id:
                data["deal_id"] = int(deal_id)
            if due_date:
                data["due_date"] = due_date

            result = await pipedrive_service.create_activity(data)
            ok = result.get("success", False)
            act_id = (result.get("data") or {}).get("id")
            return {
                "ok": ok,
                "activity_id": act_id,
                "result": f"Tarefa '{subject}' criada (ID: {act_id})" if ok else f"Erro: {result.get('error', 'desconhecido')}",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: atualizar tarefa ────────────────────────────────────────────
    elif tool_name == "pipedrive_update_task":
        activity_id = args.get("activity_id")
        if not activity_id:
            return {"ok": False, "error": "activity_id é obrigatório"}
        data: dict = {}
        if args.get("done") in (True, "true", 1, "1"):
            data["done"] = 1
        if args.get("due_date"):
            data["due_date"] = args["due_date"]
        if args.get("note"):
            data["note"] = args["note"]
        if args.get("subject"):
            data["subject"] = args["subject"]
        try:
            from services.pipedrive.pipedrive_service import pipedrive_service
            ok = await pipedrive_service.update_activity(int(activity_id), data)
            return {"ok": ok, "result": "Atividade atualizada" if ok else "Erro ao atualizar"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: criar nota ──────────────────────────────────────────────────
    elif tool_name == "pipedrive_create_note":
        deal_id = args.get("deal_id")
        content = args.get("content", "")
        if not deal_id or not content:
            return {"ok": False, "error": "deal_id e content são obrigatórios"}
        try:
            from services.pipedrive.pipedrive_service import pipedrive_service
            r = await pipedrive_service.make_request(
                "POST", "notes",
                json={"content": content, "deal_id": int(deal_id)}
            )
            ok = r is not None and r.status_code in (200, 201)
            return {"ok": ok, "result": "Nota criada" if ok else f"Erro (HTTP {getattr(r, 'status_code', '?')})"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Pipedrive: criar pessoa/contato ────────────────────────────────────────
    elif tool_name == "pipedrive_create_person":
        name = args.get("name")
        email = args.get("email")
        phone = args.get("phone")
        arg_org_id = args.get("org_id")
        org_name = args.get("org_name")
        if not name:
            return {"ok": False, "error": "Nome é obrigatório"}
        try:
            from services.pipedrive.pipedrive_service import pipedrive_service
            pd_org_id = org_id or arg_org_id
            if not pd_org_id and org_name:
                match, resolved_id = await _pipedrive_find_org(org_name)
                if resolved_id:
                    pd_org_id = resolved_id
            target_org_id = pd_org_id
            
            result = await pipedrive_service.create_person(
                name=name,
                email=email,
                phone=phone,
                org_id=int(target_org_id) if target_org_id else None,
            )
            ok = result.get("success", False)
            person_id = (result.get("data") or {}).get("id")
            
            if ok and target_org_id:
                try:
                    details = await pipedrive_service.get_organization_details(int(target_org_id))
                    deals = details.get("deals", []) if isinstance(details, dict) else []
                    open_deal = next((d for d in deals if d.get("status") == "open"), deals[0] if deals else None)
                    if open_deal:
                        deal_id = open_deal.get("id")
                        await pipedrive_service.make_request(
                            "POST", "notes",
                            json={"content": f"👤 Novo contato adicionado via Assistente V2: {name} ({email or 'sem email'})", "deal_id": deal_id}
                        )
                except Exception:
                    pass
            return {"ok": ok, "result": f"Contato '{name}' adicionado com sucesso" if ok else f"Erro ao adicionar contato: {result.get('error', 'desconhecido')}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": f"Ferramenta desconhecida: {tool_name}"}
