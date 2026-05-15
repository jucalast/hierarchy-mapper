"""
Ferramentas Pipedrive do Agente V2.
"""
from __future__ import annotations

import httpx
from typing import Any, Dict
from core.logging_config import get_logger
from ._constants import WA_BASE, EMAIL_SERVICE_BASE, JFERRES_DOMAIN
from ._utils import (
    _pipedrive_find_org,
    _pipedrive_get_org_by_id,
    _remove_diacritics,
    _fix_llama_corrupted_name,
)

log = get_logger(__name__)


async def exec_pipedrive_get_org(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    org_name = args.get("org_name", "")
    # Aceita org_id nos args (quando agente conhece o ID mas não o nome)
    if not org_id and args.get("org_id"):
        try:
            org_id = int(args["org_id"])
        except (ValueError, TypeError):
            pass
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

        # Busca CNPJ no banco local para disponibilizar à tool find_company_contact
        cnpj_local = None
        try:
            from core.database import async_session
            from models.organization import Organization
            from sqlalchemy import select
            async with async_session() as session:
                stmt = select(Organization).where(
                    (Organization.pipedrive_id == org_id) | (Organization.id == org_id)
                )
                res = await session.execute(stmt)
                local_org = res.scalar_one_or_none()
                if local_org and local_org.cnpj:
                    cnpj_local = local_org.cnpj
        except Exception:
            pass

        return {
            "ok": True,
            "org": match,
            "org_id": org_id,
            "cnpj": cnpj_local,
            "deals": deals,
            "persons": persons,
            "summary": (
                f"{match.get('name')} | CNPJ: {cnpj_local or 'não cadastrado'} | "
                f"{deals_summary} | {len(persons)} contato(s)"
            ),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def exec_pipedrive_get_persons(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    org_name = args.get("org_name", "")
    if not org_id and args.get("org_id"):
        try:
            org_id = int(args["org_id"])
        except (ValueError, TypeError):
            pass
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
        org_real_name_lower = match.get("name", org_name).lower() if match else org_name.lower()
        for p in persons[:30]:
            name = p.get("name", "")

            # Filtra contatos cuja sintaxe "Nome - Empresa" aponta para empresa errada
            if "-" in name or "(" in name:
                parts = name.replace("(", "-").replace(")", "").split("-")
                company_hint = parts[-1].strip().lower()
                if (company_hint
                    and company_hint not in org_real_name_lower
                    and org_real_name_lower not in company_hint
                    and len(company_hint) > 3):
                    continue

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
                    stmt_emp = select(Employee).where(
                        Employee.company_id == local_org.id,
                        Employee.role != "Reprovado",
                        Employee.department != "Reprovado"
                    )
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
                + ", ".join(
                    f"{p['name']} ({'WhatsApp:registrado' if p['phone'] and len(''.join(c for c in str(p['phone']) if c.isdigit())) > 13 else ('tel: ' + (p['phone'] or 'nenhum'))}, email: {p['email'] or 'nenhum'})"
                    for p in result[:4]
                )
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
             "person_name": a.get("person_name"),
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
    if not org_id and args.get("org_id"):
        try:
            org_id = int(args["org_id"])
        except (ValueError, TypeError):
            pass
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
            # Apenas atividades atreladas a um negócio (deal_id)
            if not act.get("deal_id"):
                continue
            raw_org = act.get("org_id")
            if isinstance(raw_org, dict):
                org_name = raw_org.get("name", "").strip()
                org_pd_id = raw_org.get("value")
            else:
                # Pipedrive às vezes retorna org_id como inteiro e org_name como campo separado
                org_name = (act.get("org_name") or "").strip()
                org_pd_id = raw_org if isinstance(raw_org, int) else None
            entry = {
                "id": act.get("id"),
                "subject": act.get("subject", ""),
                "type": act.get("type", ""),
                "person_name": act.get("person_name"),
                "org": org_name,
                "org_id": org_pd_id,
                "deal_id": act.get("deal_id"),
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
