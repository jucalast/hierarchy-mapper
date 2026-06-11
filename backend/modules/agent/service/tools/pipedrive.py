"""
Ferramentas Pipedrive do Agente V2.
"""
from __future__ import annotations

import httpx
from typing import Any, Dict
from core.observability.logging_config import get_logger
from ._constants import WA_BASE, EMAIL_SERVICE_BASE, JFERRES_DOMAIN
from ._utils import (
    _pipedrive_find_org,
    _pipedrive_get_org_by_id,
    _remove_diacritics,
    _fix_llama_corrupted_name,
)

log = get_logger(__name__)


async def exec_pipedrive_advance_deal(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    deal_id = args.get("deal_id")
    target_stage = args.get("target_stage")
    reason = args.get("reason", "")
    
    if not deal_id or not target_stage:
        return {"ok": False, "error": "deal_id e target_stage são obrigatórios"}
        
    STAGE_FLOW = {
        # Novos Negócios
        2: 18,   # Entrada -> Qualificação
        18: 19,  # Qualificação -> Contatado
        19: 4,   # Contatado -> Reunião Agendada
        4: 26,   # Reunião Agendada -> Reunião Realizada
        26: 27,  # Reunião Realizada -> Proposta em Andamento
        27: 28,  # Proposta em Andamento -> Em Negociação
        # Clientes Carteira
        14: 16,  # Entrada -> Contato
        16: 17,  # Contato -> Proposta
        17: 32   # Proposta -> Programação
    }
    
    STAGE_NAMES = {
        2: "Entrada (Novos Negócios)", 18: "Qualificação", 19: "Contatado", 
        4: "Reunião Agendada", 26: "Reunião Realizada", 27: "Proposta em Andamento", 28: "Em Negociação",
        14: "Entrada (Carteira)", 16: "Contato", 17: "Proposta", 32: "Programação"
    }

    try:
        from modules.crm.service.pipedrive_service import pipedrive_service
        # Fetch current deal state
        deal_res = await pipedrive_service.make_request("GET", f"deals/{deal_id}")
        if not deal_res or deal_res.status_code != 200:
            return {"ok": False, "error": f"Deal {deal_id} não encontrado."}
            
        deal_data = deal_res.json().get("data", {})
        current_stage_id = deal_data.get("stage_id")
        
        next_stage_id = None
        if target_stage.lower() == "next":
            next_stage_id = STAGE_FLOW.get(current_stage_id)
            if not next_stage_id:
                return {"ok": False, "error": f"Não há estágio mapeado após o estágio atual ({current_stage_id})."}
        else:
            # We assume target_stage is provided as the stage ID (int) if it's not "next"
            try:
                next_stage_id = int(target_stage)
            except ValueError:
                return {"ok": False, "error": "target_stage deve ser 'next' ou um ID numérico de estágio."}
                
        # Advance the deal
        update_res = await pipedrive_service.update_deal(int(deal_id), {"stage_id": next_stage_id})
        ok = update_res.get("success", False)
        
        if ok:
            stage_name = STAGE_NAMES.get(next_stage_id, str(next_stage_id))
            note_content = f"⏩ Deal avançado para '{stage_name}' via Assistente V2."
            if reason:
                note_content += f"\nMotivo: {reason}"
            try:
                await pipedrive_service.make_request(
                    "POST", "notes",
                    json={"content": note_content, "deal_id": int(deal_id)}
                )
            except Exception:
                pass
            return {"ok": True, "result": f"Deal movido para a etapa {stage_name}.", "new_stage_id": next_stage_id, "new_stage_name": stage_name}
        else:
            return {"ok": False, "error": f"Erro ao avançar deal: {update_res.get('error', 'desconhecido')}"}
            
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def exec_pipedrive_get_org(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    org_name = args.get("org_name", "")
    # Aceita org_id nos args (quando agente conhece o ID mas não o nome)
    if not org_id and args.get("org_id"):
        try:
            org_id = int(args["org_id"])
        except (ValueError, TypeError):
            pass
    try:
        from modules.crm.service.pipedrive_service import pipedrive_service
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

        # Busca CNPJ e Contexto no banco local para disponibilizar à tool
        cnpj_local = None
        prospecting_context = None
        temperature = None
        try:
            from core.infra.database import async_session
            from models.organization import Organization
            from sqlalchemy import select
            async with async_session() as session:
                stmt = select(Organization).where(
                    (Organization.pipedrive_id == org_id) | (Organization.id == org_id)
                )
                res = await session.execute(stmt)
                local_org = res.scalar_one_or_none()
                if local_org:
                    cnpj_local = local_org.cnpj
                    prospecting_context = local_org.prospecting_context
                    temperature = local_org.temperature
        except Exception:
            pass

        context_str = f" | Temp: {temperature}" if temperature else ""
        if prospecting_context:
            context_str += f" | Contexto: {prospecting_context}"

        return {
            "ok": True,
            "org": match,
            "org_id": org_id,
            "cnpj": cnpj_local,
            "temperature": temperature,
            "prospecting_context": prospecting_context,
            "deals": deals,
            "persons": persons,
            "summary": (
                f"{match.get('name')} | CNPJ: {cnpj_local or 'não cadastrado'}{context_str} | "
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
        from modules.crm.service.pipedrive_service import pipedrive_service
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
                "email_validated": True if email else False,
                "role": p.get("job_title", ""),
                "channels": channels,
                "source": "Pipedrive"
            })

        # 🚀 INTEGRATION: Busca no banco local (Hierarchy Mapper) por funcionários vinculados à organização
        try:
            from core.infra.database import async_session
            from models.organization import Organization
            from models.people.employee import Employee
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

                        # Tenta encontrar contato já existente (vindo do Pipedrive) para enriquecer
                        # Usa comparação robusta (sem acentos, lowercase, sem espaços extras)
                        def normalize(s):
                            return _remove_diacritics(str(s or "").lower().strip())
                            
                        emp_name_norm = normalize(emp.name)
                        existing = next((p for p in result if normalize(p.get("name")) == emp_name_norm), None)
                        
                        phone = emp.whatsapp_number or emp.phone
                        channels = [c for c, v in [("WhatsApp", phone), ("Email", emp.email)] if v]
                        
                        if emp.role and emp.department:
                            role_desc = f"{emp.role} - Setor: {emp.department}"
                        elif emp.role:
                            role_desc = emp.role
                        elif emp.department:
                            role_desc = f"Setor: {emp.department}"
                        else:
                            role_desc = "Contato Banco Local"

                        if existing:
                            # Enriquece o contato do Pipedrive com dados do Banco Local
                            existing["local_id"] = emp.id
                            # Prioriza o cargo do Banco Local que costuma ser mais preciso para Compras
                            if role_desc and role_desc != "Contato Banco Local":
                                existing["role"] = role_desc
                            existing["department"] = emp.department
                            existing["source"] = f"Pipedrive + Banco Local"
                            # Se o Pipedrive não tinha contato mas o Banco Local tem, atualiza
                            if not existing.get("phone") and phone:
                                existing["phone"] = phone
                                if "WhatsApp" not in existing["channels"]: existing["channels"].append("WhatsApp")
                            if not existing.get("email") and emp.email:
                                existing["email"] = emp.email
                                if "Email" not in existing["channels"]: existing["channels"].append("Email")
                        else:
                            result.append({
                                "id": None,
                                "local_id": emp.id,
                                "name": emp.name,
                                "phone": phone,
                                "email": emp.email,
                                "email_validated": True if emp.email else False,
                                "role": role_desc,
                                "department": emp.department,
                                "channels": channels,
                                "source": "Banco Local",
                                "temperature": emp.temperature,
                                "prospecting_context": emp.prospecting_context
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

        # Garante o campo email_validated para todos os contatos
        for p in result:
            p["email_validated"] = True if p.get("email") else False

        # Analisa se existem decisores ICP (Compras/Logística) mapeados que NÃO estão no Pipedrive
        local_icp_contacts = []
        for p in result:
            # Apenas destaca como "Decisor Local" se ele NÃO tiver ID do Pipedrive
            if p.get("id") is None:
                role_lower = str(p.get("role", "")).lower()
                dept_lower = str(p.get("department", "")).lower() if p.get("department") else ""
                is_icp = any(x in role_lower or x in dept_lower for x in ["compras", "logist", "suprimento", "adquir", "comprador"])
                if is_icp:
                    available_channels = []
                    if p.get("phone"): available_channels.append("WhatsApp")
                    if p.get("email"): available_channels.append("Email")
                    
                    if available_channels:
                        channels_str = ", ".join(available_channels)
                        if "WhatsApp" not in available_channels:
                            channels_str += " (SEM WHATSAPP)"
                    else:
                        channels_str = "nenhum"
                        
                    local_icp_contacts.append(f"{p['name']} ({p.get('role')} - Canais: {channels_str})")

        icp_str = ""
        if local_icp_contacts:
            icp_str = f" | [ALERTA: DECISOR LOCAL ENCONTRADO] " + ", ".join(local_icp_contacts)

        # Se tem apenas contatos locais, não paramos aqui. Deixamos a IA avaliar.
        # has_pipedrive = any(p.get("id") is not None for p in result)
        # if not has_pipedrive and result: ... (removido para que o evaluate_prospects decida)

        return {
            "ok": True,
            "org": match.get("name"),
            "persons": result,
            "count": len(result),
            "summary": (
                f"{len(result)} contatos em {match.get('name')}: "
                + ", ".join(
                    f"{p['name']} (ID Pipedrive: {p['id'] if p['id'] else 'NULO/NÃO CADASTRADO'}, tel: {p['phone'] or 'nenhum'}, email: {p['email'] or 'nenhum'})"
                    for p in result[:6]
                ) + icp_str
            ),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def exec_pipedrive_get_activities(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    org_name = args.get("org_name", "")
    try:
        from modules.crm.service.pipedrive_service import pipedrive_service
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
        notes = details.get("notes", []) if isinstance(details, dict) else []
        recent_notes = [
            {"id": n.get("id"), "content": n.get("content"), "add_time": n.get("add_time")}
            for n in sorted(notes, key=lambda x: x.get("add_time", ""), reverse=True)[:5]
        ]
        
        return {
            "ok": True,
            "org": match.get("name"),
            "pending": pending[:10],
            "done_count": len(done),
            "recent_notes": recent_notes,
            "count": len(pending),
            "summary": f"{len(pending)} atividades pendentes e {len(notes)} anotações para {match.get('name')}",
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
        from modules.crm.service.pipedrive_service import pipedrive_service
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
        from modules.crm.service.pipedrive_service import pipedrive_service
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


async def exec_pipedrive_get_deals_without_tasks(args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from modules.crm.service.pipedrive_service import pipedrive_service
        r = await pipedrive_service.make_request("GET", f"deals?user_id={pipedrive_service.user_id}&status=open&limit=500")
        if not r or r.status_code != 200:
            return {"ok": False, "error": "Erro ao buscar negócios do Pipedrive"}
        deals = r.json().get("data") or []
        deals_without_tasks = []
        for d in deals:
            undone_count = d.get("undone_activities_count", 0)
            if undone_count == 0:
                person_name = d.get("person_name") or ""
                stage_id = d.get("stage_id", "Desconhecido")
                deals_without_tasks.append({
                    "id": d.get("id"),
                    "title": d.get("title", ""),
                    "org_name": d.get("org_name", ""),
                    "person_name": person_name,
                    "stage_id": stage_id,
                    "value": d.get("value", 0),
                    "status": d.get("status", ""),
                    "owner_name": d.get("owner_name", "")
                })
        
        summary_parts = [f"Encontrados {len(deals_without_tasks)} negócio(s) em andamento sem tarefas pendentes:"]
        for d in deals_without_tasks[:30]:
            contact_info = f"Contato: {d['person_name']}" if d['person_name'] else "SEM CONTATO"
            summary_parts.append(f"- {d['title']} (ID: {d['id']}) | Etapa: {d['stage_id']} | {contact_info}")
        summary = "\n".join(summary_parts)
        
        return {
            "ok": True,
            "deals": deals_without_tasks[:30],
            "count": len(deals_without_tasks),
            "summary": summary
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def exec_pipedrive_bulk_update_tasks(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ferramenta para atualizar tarefas em massa filtrando por stage_id (etapa do funil) e texto da tarefa.
    - Fecha a tarefa encontrada.
    - Cria a nova tarefa concluída (se create_completed_task for informado).
    - Cria a nova tarefa pendente (se create_pending_task for informado).
    """
    stage_id = args.get("stage_id")
    task_keyword = args.get("task_keyword", "").lower()
    create_completed_task = args.get("create_completed_task")
    create_pending_task = args.get("create_pending_task")
    
    if not stage_id or not task_keyword:
        return {"ok": False, "error": "stage_id e task_keyword são obrigatórios"}
        
    try:
        from modules.crm.service.pipedrive_service import pipedrive_service
        from datetime import date, timedelta
        
        deals_resp = await pipedrive_service.make_request("GET", f"deals?stage_id={stage_id}&limit=500&status=open")
        if not deals_resp or deals_resp.status_code != 200:
            return {"ok": False, "error": "Erro ao buscar deals no Pipedrive"}
            
        deals = deals_resp.json().get("data", [])
        if not deals:
            return {"ok": True, "summary": f"Nenhum deal encontrado na etapa {stage_id}."}
            
        count_updated = 0
        details = []
        
        today_str = date.today().isoformat()
        tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
        
        for d in deals:
            deal_id = d.get("id")
            title = d.get("title")
            org_id = d.get("org_id")
            if isinstance(org_id, dict):
                org_id = org_id.get("value")
                
            act_resp = await pipedrive_service.make_request("GET", f"deals/{deal_id}/activities")
            if not act_resp or act_resp.status_code != 200:
                continue
                
            acts = act_resp.json().get("data") or []
            
            target_act = None
            for a in acts:
                subject_lower = a.get("subject", "").lower()
                if task_keyword in subject_lower:
                    target_act = a
                    break
                    
            if target_act:
                count_updated += 1
                deal_log = f"Deal {deal_id} ({title}): "
                
                # 1. Fechar a tarefa atual se estiver pendente
                if not target_act.get("done"):
                    await pipedrive_service.update_activity(target_act.get("id"), {"done": 1})
                    deal_log += f"Tarefa '{target_act.get('subject')}' fechada. "
                
                # 2. Criar tarefa concluida
                if create_completed_task:
                    has_completed = any(create_completed_task.lower() in a.get("subject", "").lower() for a in acts)
                    if not has_completed:
                        payload_comp = {
                            "subject": create_completed_task,
                            "done": 1,
                            "deal_id": deal_id,
                            "org_id": org_id,
                            "type": "task",
                            "due_date": today_str
                        }
                        await pipedrive_service.make_request("POST", "activities", json=payload_comp)
                        deal_log += f"Tarefa '{create_completed_task}' criada (concluída). "
                
                # 3. Criar proxima tarefa pendente
                if create_pending_task:
                    has_pending = any(create_pending_task.lower() in a.get("subject", "").lower() for a in acts)
                    if not has_pending:
                        payload_pend = {
                            "subject": create_pending_task,
                            "done": 0,
                            "deal_id": deal_id,
                            "org_id": org_id,
                            "type": "task",
                            "due_date": tomorrow_str
                        }
                        await pipedrive_service.make_request("POST", "activities", json=payload_pend)
                        deal_log += f"Tarefa '{create_pending_task}' criada (pendente para amanhã). "
                        
                details.append(deal_log)
                
        summary = f"Massa atualizada com sucesso. {count_updated} negócios alterados.\n" + "\n".join(details)
        return {"ok": True, "count": count_updated, "summary": summary}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}

