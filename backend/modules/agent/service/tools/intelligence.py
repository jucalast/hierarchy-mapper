"""
Ferramentas de inteligência (web search, IA, scripts, etc.) do Agente V2.
"""
from __future__ import annotations

import json
import httpx
import os
from typing import Any, Dict
from core.observability.logging_config import get_logger
from ._constants import WA_BASE, EMAIL_SERVICE_BASE, JFERRES_DOMAIN
from ._utils import (
    _pipedrive_find_org,
    _pipedrive_get_org_by_id,
    _fix_llama_corrupted_name,
)

log = get_logger(__name__)


async def exec_deep_company_investigation(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Realiza uma investigação profunda sobre a empresa criando um Dossiê Pré-Abordagem.
    Busca no banco, dados de CNPJ (Receita Federal) e Web.
    """
    import re as _re
    from core.infra.database import async_session
    from models.organization import Organization
    from sqlalchemy import select
    from modules.hierarchy.service.cnpj_resolver import fetch_company_data_by_cnpj, build_full_address

    org_name = args.get("org_name", "")
    cnpj_raw = args.get("cnpj", "")
    cnpj_clean = _re.sub(r"\D", "", cnpj_raw or "")

    if not org_name and not cnpj_clean:
        return {"ok": False, "error": "Forneça org_name ou cnpj para investigação profunda."}

    dossier = {
        "local_intelligence": None,
        "cnpj_data": None,
        "web_research": "Informação não encontrada via OSINT básica."
    }

    # 1. Inteligência Local (Banco de Dados) e descoberta de CNPJ
    try:
        async with async_session() as session:
            stmt = select(Organization).where(
                (Organization.name.ilike(f"%{org_name}%")) | 
                (Organization.cnpj == cnpj_clean if len(cnpj_clean) == 14 else False)
            ).limit(1)
            res = await session.execute(stmt)
            org = res.scalar()
            if org:
                dossier["local_intelligence"] = {
                    "category": org.category,
                    "product_focus": org.product_focus,
                    "prospecting_context": org.prospecting_context or "Sem contexto salvo."
                }
                if not cnpj_clean and org.cnpj:
                    cnpj_clean = _re.sub(r"\D", "", org.cnpj)
    except Exception: pass

    # 2. Dados da Receita Federal (CNPJ)
    if len(cnpj_clean) == 14:
        try:
            data = await fetch_company_data_by_cnpj(cnpj_clean)
            if data:
                dossier["cnpj_data"] = {
                    "capital_social": data.get("capital_social"),
                    "cnae": f"{data.get('cnae_fiscal', '')} - {data.get('cnae_fiscal_descricao', '')}",
                    "address": build_full_address(data),
                    "size": data.get("porte")
                }
        except Exception: pass

    # 3. Web Research ( DuckDuckGo )
    search_query = f'"{org_name}" site oficial atuação notícias 2024 2025'
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": search_query, "format": "json", "no_html": 1},
                timeout=10.0
            )
            if r.status_code == 200:
                data = r.json()
                abstract = data.get("AbstractText")
                if abstract:
                    dossier["web_research"] = abstract
    except Exception: pass

    # 4. Formata o Dossiê
    dossier_text = f"Dossiê Pré-Abordagem para {org_name}:\n"
    if dossier["local_intelligence"]:
        dossier_text += f"- Categoria: {dossier['local_intelligence']['category']}\n"
        dossier_text += f"- Foco do Produto: {dossier['local_intelligence']['product_focus']}\n"
    if dossier["cnpj_data"]:
        dossier_text += f"- Porte: {dossier['cnpj_data']['size']}\n"
        dossier_text += f"- CNAE: {dossier['cnpj_data']['cnae']}\n"
        dossier_text += f"- Capital Social: {dossier['cnpj_data']['capital_social']}\n"
        dossier_text += f"- Endereço: {dossier['cnpj_data']['address']}\n"
    dossier_text += f"- Pesquisa Web: {dossier['web_research']}\n"

    # 5. Salva no banco (append)
    try:
        async with async_session() as session:
            stmt = select(Organization).where(
                (Organization.name.ilike(f"%{org_name}%")) | 
                (Organization.cnpj == cnpj_clean if len(cnpj_clean) == 14 else False)
            ).limit(1)
            res = await session.execute(stmt)
            org = res.scalar()
            if org:
                new_context = f"[Dossiê] {dossier_text[:1000]}"
                if org.prospecting_context and new_context not in org.prospecting_context:
                    org.prospecting_context += f" | {new_context}"
                else:
                    org.prospecting_context = new_context
                await session.commit()
    except Exception as e:
        log.warning(f"Falha ao salvar dossiê: {e}")

    summary = f"Investigação profunda concluída para {org_name}."

    return {
        "ok": True,
        "org_name": org_name,
        "data": dossier,
        "summary": summary
    }


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


async def _save_maps_phone(org_name: str, phone: str) -> None:
    """Persiste o telefone do Google Maps na organização (atualiza apenas se ainda não tiver)."""
    try:
        from core.infra.database import async_session
        from models.organization import Organization
        from sqlalchemy import select, update
        async with async_session() as session:
            result = await session.execute(
                select(Organization.id, Organization.maps_phone)
                .where(Organization.name.ilike(f"%{org_name}%"))
                .limit(1)
            )
            row = result.first()
            if row and not row.maps_phone:
                await session.execute(
                    update(Organization).where(Organization.id == row.id).values(maps_phone=phone)
                )
                await session.commit()
    except Exception:
        pass


async def exec_find_company_contact(args: dict) -> dict:
    """Busca contato da empresa via Google Maps API (Principal), Receita Federal (BrasilAPI) e web search."""
    import re as _re
    import os
    org_name = args.get("org_name", "")
    cnpj_raw = args.get("cnpj", "")
    cnpj_clean = _re.sub(r"\D", "", cnpj_raw or "")

    # Se não veio CNPJ válido, tenta buscar no banco de dados pelo org_name
    if len(cnpj_clean) != 14 and org_name:
        try:
            from core.infra.database import async_session
            from models.organization import Organization
            from sqlalchemy import select
            async with async_session() as session:
                stmt = select(Organization.cnpj).where(Organization.name.ilike(f"%{org_name}%")).limit(1)
                res = await session.execute(stmt)
                db_cnpj = res.scalar()
                if db_cnpj:
                    cnpj_clean = _re.sub(r"\D", "", db_cnpj)
        except Exception:
            pass

    phones, emails, address, web_snippets = [], [], "", []

    # 1. Tentativa via Google Maps API (Principal)
    from core.config import settings
    google_maps_api_key = settings.GOOGLE_MAPS_API_KEY
    quota = None
    if org_name and google_maps_api_key:
        import json
        from datetime import datetime
        quota_file = "google_maps_quota.json"
        today = datetime.now().strftime("%Y-%m-%d")
        used = 0
        limit = settings.GOOGLE_MAPS_DAILY_LIMIT
        
        try:
            if os.path.exists(quota_file):
                with open(quota_file, "r", encoding="utf-8") as f:
                    qdata = json.load(f)
                    if qdata.get("date") == today:
                        used = qdata.get("used", 0)
        except Exception:
            pass

        quota = {"used": used, "limit": limit}

        if used < limit:
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    headers = {
                        "X-Goog-Api-Key": google_maps_api_key,
                        "X-Goog-FieldMask": "places.nationalPhoneNumber,places.internationalPhoneNumber,places.websiteUri,places.formattedAddress",
                    }
                    body = {
                        "textQuery": org_name,
                        "languageCode": "pt-BR"
                    }
                    r = await client.post(
                        "https://places.googleapis.com/v1/places:searchText",
                        headers=headers,
                        json=body
                    )
                    if r.status_code == 200:
                        used += 1
                        quota["used"] = used
                        try:
                            with open(quota_file, "w", encoding="utf-8") as f:
                                json.dump({"date": today, "used": used, "limit": limit}, f)
                        except Exception:
                            pass
                        
                        data = r.json()
                        places = data.get("places", [])
                        if places:
                            place = places[0]
                            # Tenta pegar nacional primeiro, depois internacional
                            phone = place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber")
                            if phone:
                                phones.append({"source": "Google Maps", "value": phone})
                                # Persiste o telefone do Google Maps na organização (fire-and-forget)
                                import asyncio as _asyncio
                                _asyncio.create_task(_save_maps_phone(org_name, phone))

                            website = place.get("websiteUri")
                            if website:
                                web_snippets.append(f"Site Oficial: {website}")

                            g_address = place.get("formattedAddress")
                            if g_address and not address:
                                address = g_address
                    else:
                        print(f"Google Maps API Error: {r.status_code} - {r.text}")
            except Exception as e:
                print(f"Erro na requisição do Google Maps: {e}")
                pass

    # 2. Receita Federal via BrasilAPI / MinhReceita / ReceitaWS (Fallback se não achar telefone no Google Maps)
    if len(cnpj_clean) == 14 and not phones:
        try:
            from modules.hierarchy.service.cnpj_resolver import fetch_company_data_by_cnpj, build_full_address
            data = await fetch_company_data_by_cnpj(cnpj_clean)
            if data:
                for field in ["ddd_telefone_1", "ddd_telefone_2"]:
                    val = (data.get(field) or "").strip()
                    if val:
                        phones.append({"source": "Receita Federal", "value": val})
                email_rf = (data.get("email") or "").strip().lower()
                if email_rf and "@" in email_rf:
                    emails.append({"source": "Receita Federal", "value": email_rf})
                if not address:
                    address = build_full_address(data)
        except Exception:
            pass

    # 3. Web search via DuckDuckGo Instant Answer
    if org_name:
        try:
            queries = [
                f'"{org_name}" email compras OR suprimentos OR comercial',
                f'"{org_name}" telefone contato',
            ]
            async with httpx.AsyncClient(timeout=8.0) as client:
                for q in queries:
                    try:
                        r = await client.get(
                            "https://api.duckduckgo.com/",
                            params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1},
                        )
                        if r.status_code == 200:
                            body = r.json()
                            abstract = (body.get("AbstractText") or "").strip()
                            related = [t.get("Text", "").strip() for t in body.get("RelatedTopics", [])[:2] if t.get("Text")]
                            snippet = abstract or " | ".join(related)
                            if snippet:
                                web_snippets.append(snippet[:300])
                    except Exception:
                        pass
        except Exception:
            pass

    # Monta resumo legível
    parts = []
    if phones:
        parts.append("Telefones: " + " | ".join(f"{p['value']} ({p['source']})" for p in phones))
    else:
        parts.append("Nenhum telefone encontrado nas buscas.")
    if emails:
        parts.append("E-mail: " + " | ".join(f"{e['value']} ({e['source']})" for e in emails))
    if address:
        parts.append(f"Endereco: {address}")
    if web_snippets:
        parts.append("Web: " + " | ".join(web_snippets[:2]))

    can_create = bool(phones or emails)
    if can_create:
        parts.append(
            "Dados encontrados. Se necessario, use pipedrive_create_person para salvar o contato.\n\n"
            "[INSTRUÇÃO CRÍTICA DO SISTEMA]: VOCÊ ENCONTROU DADOS COM SUCESSO! É ESTRITAMENTE PROIBIDO ENCERRAR SEU TURNO (end_turn) AGORA. VOCÊ DEVE PROSSEGUIR IMEDIATAMENTE PARA A FASE 2 CHAMANDO `prepare_live_coaching_session`!"
        )
    else:
        parts.append("Nenhum contato encontrado. Informe o usuario e finalize com PARADA ANTECIPADA.")

    return {
        "ok": True,
        "phones": phones,
        "emails": emails,
        "address": address,
        "web_snippets": web_snippets,
        "can_create_contact": can_create,
        "summary": "\n".join(parts),
        "quota": quota
    }


def extract_activity_id(args: dict, messages: list | None) -> str | None:
    # 1. Verifica se veio nos args
    activity_id = args.get("activity_id")
    if activity_id:
        return str(activity_id)

    # 2. Se não veio, analisa as mensagens do histórico
    if not messages:
        return None

    import re
    # Procura no conteúdo textual das mensagens de trás para frente
    for m in reversed(messages):
        content = m.get("content") or ""
        if isinstance(content, list):
            content_str = " ".join(
                str(x.get("text", "")) if isinstance(x, dict) else str(x)
                for x in content
            )
        else:
            content_str = str(content)

        patterns = [
            r"ID da tarefa no Pipedrive:\s*(\d+)",
            r"activity_id[\"\s:]+(\d+)",
            r"tarefa no Pipedrive:\s*(\d+)",
            r"activity_id=(\d+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, content_str, re.IGNORECASE)
            if match:
                return match.group(1)

    # 3. Fallback: extrai do tool_result de pipedrive_get_activities
    from modules.agent.service.core.runner import _extract_first_activity_id
    try:
        val = _extract_first_activity_id(messages)
        if val:
            return str(val)
    except Exception:
        pass

    return None


async def exec_prepare_live_coaching_session(args: dict, org_id: int | None = None, messages: list | None = None) -> dict:
    """Gera um plano de voo (passo a passo) para a ligação. Delega o tipo de ligação para o CallTypeRouter."""
    from core.llm.router import ask_llm
    from core.llm.base import LLMTier
    from modules.ai.service.context.business_context_service import BusinessContextService
    from modules.agent.skills.call_types import classify_call_type, get_call_type_config
    import json

    contact_name = args.get("contact_name", "")
    phone = args.get("phone", "")
    profile_pic = args.get("profile_pic", None)
    activity_id = extract_activity_id(args, messages)
    goal = args.get("goal")

    # Tenta buscar profile_pic no banco local se não foi fornecida
    if not profile_pic and (contact_name or phone):
        try:
            from core.infra.database import async_session
            from models.people.employee import Employee
            from sqlalchemy import select, or_
            async with async_session() as session:
                stmt = select(Employee.profile_pic).where(
                    or_(
                        Employee.name.ilike(f"%{contact_name}%") if contact_name else False,
                        Employee.whatsapp_number == phone if phone else False
                    )
                ).limit(1)
                res = await session.execute(stmt)
                db_pic = res.scalar()
                if db_pic:
                    profile_pic = db_pic
        except Exception as _pic_err:
            log.debug(f"Erro ao buscar profile_pic de fallback: {_pic_err}")

    # Busca contexto dinâmico da empresa
    ctx = await BusinessContextService.get_tenant_context()
    company_name = ctx.get("company_name", "a Empresa")
    company_segment = ctx.get("company_segment", "seu segmento")
    differentials = "\n".join([f"- {d}" for d in ctx.get("company_differentials", [])])
    seller_name = ctx.get("seller_name", "João Luccas")

    # ─── Coleta de sinais de contexto do histórico de mensagens ───────────────
    is_company_phone = args.get("is_company_phone")
    has_previous_contact = False
    has_open_proposal = False
    deal_stage_id = None
    activity_subject = None

    if is_company_phone is None:
        is_company_phone = False

    if messages:
        for msg in reversed(messages):
            content = msg.get("content") if isinstance(msg, dict) else []
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                tool_name = block.get("tool_name", "")
                block_content = str(block.get("content", ""))

                # Detecta telefone de gatekeeper via find_company_contact
                if (block.get("type") == "tool_result" and
                        tool_name == "find_company_contact" and
                        phone in block_content):
                    is_company_phone = True

                # Detecta histórico de contato via WA ou email
                if (block.get("type") == "tool_result" and
                        tool_name in ("whatsapp_get_messages", "email_get_contact_history") and
                        len(block_content) > 80):
                    has_previous_contact = True

                # Detecta deal stage a partir do resultado do get_deals
                if block.get("type") == "tool_result" and tool_name == "pipedrive_get_deals":
                    try:
                        data = json.loads(block.get("content", "{}"))
                        deals = data.get("deals") or data.get("data", {}).get("deals", [])
                        open_deals = [d for d in deals if isinstance(d, dict) and d.get("status") == "open"]
                        if open_deals:
                            deal_stage_id = open_deals[0].get("stage_id")
                    except Exception:
                        pass

                # Detecta proposta enviada via atividade ou deal stage
                if block.get("type") == "tool_result" and tool_name == "pipedrive_get_activities":
                    try:
                        data = json.loads(block.get("content", "{}"))
                        acts = data.get("activities") or []
                        for act in acts:
                            subj = (act.get("subject") or "").lower()
                            if any(kw in subj for kw in ["proposta", "orçamento", "cotação"]):
                                has_open_proposal = True
                            if act.get("id") and str(act.get("id")) == str(activity_id):
                                activity_subject = act.get("subject")
                    except Exception:
                        pass

    # ─── Extrai snippets reais de comunicação para enriquecer o prompt ──────
    # Varre o histórico de mensagens coletando os CONTEÚDOS reais de WA, email, deals e atividades
    wa_snippet = ""
    email_snippet = ""
    deal_snippet = ""
    activity_snippet = ""

    if messages:
        for msg in reversed(messages):
            content = msg.get("content") if isinstance(msg, dict) else []
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_name = block.get("tool_name", "")
                raw = block.get("content", "")
                raw_str = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)

                if tool_name == "whatsapp_get_messages" and not wa_snippet and len(raw_str) > 50:
                    # Pega até 1500 chars — o suficiente para capturar o tom e histórico real
                    wa_snippet = raw_str[:1500]

                if tool_name == "email_get_contact_history" and not email_snippet and len(raw_str) > 50:
                    email_snippet = raw_str[:1200]

                if tool_name == "pipedrive_get_deals" and not deal_snippet and len(raw_str) > 20:
                    deal_snippet = raw_str[:600]

                if tool_name == "pipedrive_get_activities" and not activity_snippet and len(raw_str) > 20:
                    activity_snippet = raw_str[:600]

    # Monta bloco de contexto real a injetar no prompt
    real_context_parts = []
    if wa_snippet:
        real_context_parts.append(
            f"HISTÓRICO DE WHATSAPP COM {contact_name}\n"
            f"→ USE para: calibrar o tom (formal/informal), referenciar conversas anteriores, mencionar follow-ups já feitos.\n"
            f"→ ATENÇÃO: Se houver várias mensagens não respondidas, o cliente está evitando. Não seja robótico.\n"
            f"{wa_snippet}"
        )
    if email_snippet:
        real_context_parts.append(
            f"HISTÓRICO DE E-MAILS COM {contact_name}\n"
            f"→ USE para: referenciar datas reais de contato, assuntos enviados, e-mails em aberto.\n"
            f"→ Se houver um e-mail de apresentação sem resposta, mencione-o com a data exata.\n"
            f"{email_snippet}"
        )
    if activity_snippet:
        real_context_parts.append(
            f"ATIVIDADES NO CRM (tarefas e notas):\n"
            f"→ USE para: saber exatamente qual proposta foi enviada e quando, e qual é o objetivo da ligação.\n"
            f"{activity_snippet}"
        )
    if deal_snippet:
        real_context_parts.append(
            f"DADOS DO NEGÓCIO (deal no Pipedrive):\n"
            f"→ USE para: referenciar o valor real da proposta se disponível.\n"
            f"{deal_snippet}"
        )
    real_context_block = "\n\n".join(real_context_parts) if real_context_parts else ""

    # ─── Classifica o tipo de ligação via CallTypeRouter ─────────────────────
    call_type = classify_call_type(
        goal=goal,
        is_company_phone=is_company_phone,
        has_previous_contact=has_previous_contact,
        has_open_proposal=has_open_proposal,
        deal_stage_id=deal_stage_id,
        activity_subject=activity_subject or goal,
    )
    call_config = get_call_type_config(call_type)

    log.info(f"[CallTypeRouter] Tipo de ligação classificado: {call_type} | goal='{goal}' | has_previous={has_previous_contact} | has_proposal={has_open_proposal} | stage={deal_stage_id} | wa_snippet={bool(wa_snippet)} | email_snippet={bool(email_snippet)}")

    # ─── Monta objective_instruction com base no tipo classificado ────────────
    if call_type == "gatekeeper":
        objective_instruction = (
            f"ATENÇÃO: O telefone identificado ({phone}) é o contato geral da empresa (Recepção/PABX), "
            f"e não o número direto de {contact_name}. "
            f"O objetivo desta ligação NÃO é vender na recepção, mas sim ser transferido para o decisor {contact_name}."
        )
    elif call_type == "proposal_return":
        objective_instruction = (
            f"Gere um plano de voo para uma ligação de COBRANÇA DE RETORNO DE PROPOSTA com {contact_name} (Tel: {phone}). "
            f"O objetivo é verificar o status da avaliação da proposta/orçamento e avançar para o fechamento."
            + (f" Contexto adicional: {goal}" if goal else "")
        )
    elif call_type == "followup_call":
        objective_instruction = (
            f"Gere um plano de voo para uma ligação de FOLLOW-UP DE RELACIONAMENTO com {contact_name} (Tel: {phone}). "
            f"Já houve contato anterior — mencione o histórico e avance o relacionamento."
            + (f" Objetivo específico: {goal}" if goal else "")
        )
    else:  # cold_call
        objective_instruction = (
            f"Gere um plano de voo de alta performance para uma LIGAÇÃO FRIA (Cold Call) com {contact_name} (Tel: {phone}). "
            f"Esse é o primeiro contato — use SPIN Selling completo."
        )

    # ─── Monta o JSON de etapas para o prompt ────────────────────────────────
    steps = call_config["steps"]
    pre_filled = call_config["pre_filled_step"]
    step_dicts = []
    for label in steps:
        if label == pre_filled:
            step_dicts.append(f'    {{"label": "{label}", "content": "..."}}')  # LLM preenche
        else:
            step_dicts.append(f'    {{"label": "{label}", "content": "Pendente..."}}')
    steps_json = '"steps": [\n' + ',\n'.join(step_dicts) + '\n        ]'

    instruction_extra = (
        f'O plano deve ter EXATAMENTE as etapas: {", ".join(f"{chr(34)}{s}{chr(34)}" for s in steps)}.\n'
        f'IMPORTANTE: Gere a sugestão de fala APENAS para a etapa "{pre_filled}". '
        f'Para TODAS as demais etapas, o "content" DEVE ser exatamente "Pendente...".'
    )

    prompt = f"""
    Você é um treinador de vendas B2B (Copiloto) da {company_name}, especialista em {company_segment}.
    
    TIPO DE LIGAÇÃO: {call_config["type_label"]}
    {objective_instruction}
    
    CONTEXTO DA {company_name.upper()}:
    Segmento: {company_segment}
    Diferenciais:
    {differentials}

    {call_config["rules"]}

    {'─' * 60}
    CONTEXTO REAL DO RELACIONAMENTO COM {contact_name.upper()} (OBRIGATÓRIO: USE ESSES DADOS PARA PERSONALIZAR O SCRIPT):
    {real_context_block if real_context_block else "Sem histórico de comunicação encontrado — este é um primeiro contato."}
    {'─' * 60}

    {instruction_extra}
    ━━ REGRA CRÍTICA DE PERSONALIZAÇÃO ━━
    Use o contexto acima para gerar uma abertura HUMANA e PERSONALIZADA. Siga esta ordem de prioridade:
    
    1. ATIVIDADES NO CRM (mais confiável): Se há uma nota de atividade descrevendo quando a proposta/orçamento foi enviada (ex: "proposta de valores enviada em 20/05"), USE ESSA DATA. Esta é a referência mais confiável da proposta real.
    2. WHATSAPP: Use o tom das mensagens para calibrar a informalidade. Se já houve vários follow-ups sem resposta, reconheça isso com humor/leveza (ex: "sei que já apareci algumas vezes...").
    3. E-MAIL: O e-mail de apresentação (ex: Janeiro) pode ter sido o PRIMEIRO CONTATO, mas NÃO confunda com a data da proposta. Se o e-mail de Janeiro era uma apresentação e a proposta real foi enviada em Maio, mencione Maio na abertura.
    
    NUNCA use frases vagas como "enviei há alguns dias" se você tem a data exata.
    NUNCA confunda e-mail de apresentação (primeiro contato) com proposta/orçamento (a proposta real pode ter data diferente).
    NUNCA utilize placeholders como [Seu Nome], [Sua Empresa] ou [Nome do Contato]. O vendedor é "{seller_name}", sua empresa é "{company_name}" e o contato é "{contact_name}". O script deve vir pronto para leitura!
    As próximas etapas serão geradas progressivamente em tempo real de acordo com as respostas do cliente.

    Retorne o resultado em formato JSON:
    {{
        "contact_name": "{contact_name}",
        "phone": "{phone}",
        "call_type": "{call_type}",
        "is_company_phone": {"true" if is_company_phone else "false"},
        {steps_json}
    }}
    """
    
    plan_data = {}
    try:
        res = await ask_llm(
            prompt=prompt,
            system="Retorne EXATAMENTE o JSON estruturado do plano de voo. Use as chaves 'label' e 'content' para cada passo.",
            json_mode=True,
            tier=LLMTier.STANDARD
        )
        plan_data = res.json_data or {}
        
        # Salvar o plano de voo ativo na sessão em tempo real (best-effort)
        try:
            from services.realtime_call import assistant_manager
            assistant_manager.set_active_coaching_plan(plan_data)
        except Exception as _am_err:
            log.warning(f"assistant_manager não disponível: {_am_err}")
            
    except Exception as e:
        log.error(f"Erro ao gerar plano de voo: {e}")

    # Salva no banco de dados SQLite
    try:
        from core.infra.database import async_session
        from models.conversation.conversation import CallSession
        from sqlalchemy import select
        
        async with async_session() as session:
            db_session = None
            if activity_id or phone:
                stmt = select(CallSession).where(
                    (CallSession.pipedrive_activity_id == activity_id) if activity_id else (CallSession.phone == phone)
                )
                res = await session.execute(stmt)
                db_session = res.scalar_one_or_none()
            
            if not db_session:
                db_session = CallSession(
                    pipedrive_activity_id=activity_id,
                    org_id=org_id,
                    contact_name=contact_name,
                    phone=phone,
                    profile_pic=profile_pic,
                    flight_plan=plan_data
                )
                session.add(db_session)
            else:
                db_session.contact_name = contact_name
                db_session.phone = phone
                if profile_pic:
                    db_session.profile_pic = profile_pic
                db_session.flight_plan = plan_data
                db_session.latest_insight = None  # Limpa o insight da chamada anterior
                if org_id:
                    db_session.org_id = org_id
                if activity_id:
                    db_session.pipedrive_activity_id = activity_id
                
                # Deleta as mensagens da chamada anterior
                from sqlalchemy import delete
                from models.conversation.conversation import CallMessage
                stmt_del = delete(CallMessage).where(CallMessage.call_session_id == db_session.id)
                await session.execute(stmt_del)
            
            await session.commit()
            log.info(f"CallSession salva no banco: activity_id={activity_id}, phone={phone}")
    except Exception as db_err:
        log.warning(f"Falha ao salvar CallSession no banco: {db_err}")
        
    if plan_data:
        return {
            "ok": True,
            "contact_name": contact_name,
            "phone": phone,
            "activity_id": activity_id,
            "flight_plan": plan_data,
            "summary": "Plano de voo gerado com sucesso. Use a ferramenta 'open_ligacao_view' AGORA passando APENAS contact_name e phone."
        }
    else:
        return {
            "ok": True,
            "contact_name": contact_name,
            "phone": phone,
            "activity_id": activity_id,
            "flight_plan": {},
            "summary": f"Não foi possível gerar o plano de voo, mas o número {phone} está disponível. Chame 'open_ligacao_view' com contact_name='{contact_name}' e phone='{phone}' IMEDIATAMENTE."
        }


async def exec_open_ligacao_view(args: dict, org_id: int | None = None, messages: list | None = None) -> dict:
    """Solicita ao frontend que abra a interface de ligação (LigacaoView)."""
    contact_name = args.get("contact_name", "")
    phone = args.get("phone", "")
    flight_plan = args.get("flight_plan", {})
    activity_id = extract_activity_id(args, messages)
    profile_pic = None
    
    # Faz fallback para o último plano de voo em memória, se o agente não o passou implicitamente
    if not flight_plan:
        try:
            from services.realtime_call import assistant_manager
            flight_plan = assistant_manager.get_active_coaching_plan() or {}
        except Exception:
            pass

    # Tenta resgatar a profile_pic do DB para o contato
    if contact_name or phone:
        try:
            from core.infra.database import async_session
            from models.people.employee import Employee
            from sqlalchemy import select, or_
            async with async_session() as session:
                stmt = select(Employee.profile_pic).where(
                    or_(
                        Employee.name.ilike(f"%{contact_name}%") if contact_name else False,
                        Employee.whatsapp_number == phone if phone else False
                    )
                ).limit(1)
                res = await session.execute(stmt)
                db_pic = res.scalar()
                if db_pic:
                    profile_pic = db_pic
        except Exception:
            pass

    return {
        "ok": True,
        "status": "ligacao_view_requested",
        "contact_name": contact_name,
        "phone": phone,
        "activity_id": activity_id,
        "flight_plan": flight_plan,
        "profile_pic": profile_pic,
        "summary": f"Solicitação para abrir a interface de Ligação ao Vivo com {contact_name} ({phone}) enviada ao frontend."
    }

async def exec_generate_sales_message(args: dict, messages: list | None = None, org_id: int | None = None) -> dict:
    """Gera uma mensagem comercial: o LLM decide o modo (follow-up leve vs. venda ativa) com base no histórico e objetivo."""
    from modules.ai.service.context.business_context_service import BusinessContextService
    from core.llm.router import ask_llm
    from core.llm.base import LLMTier
    from datetime import datetime, timedelta, timezone

    contact_name = args.get("contact_name", "")
    goal = args.get("goal", "fazer follow-up e avançar o negócio")
    channel = args.get("channel", "whatsapp").lower()
    phone = args.get("phone", "")

    # ── Saudação baseada no horário de Brasília (UTC-3)
    br_time = datetime.now(timezone(timedelta(hours=-3)))
    hour = br_time.hour
    if 5 <= hour < 12:
        greeting_hint = "Bom dia"
    elif 12 <= hour < 18:
        greeting_hint = "Boa tarde"
    else:
        greeting_hint = "Boa noite"

    if not messages:
        _reason = "None" if messages is None else "vazia"
        log.warning(f"exec_generate_sales_message: histórico de mensagens está {_reason}")
        return {"ok": False, "error": f"Histórico de mensagens necessário para gerar a mensagem (recebido: {_reason})."}

    log.info(f"exec_generate_sales_message: processando histórico com {len(messages)} entradas.")

    # Serializa o histórico para contexto do LLM
    history_serialized = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "tool_result":
                        tool_content = str(item.get("content", ""))
                        if len(tool_content) > 12000:
                            tool_content = tool_content[:12000] + "... [truncado]"
                        text_parts.append(f"[Ferramenta '{item.get('tool_name', '')}': {tool_content}]")
            content = "\n".join(text_parts)
        history_serialized.append({"role": role, "content": str(content)})

    # Carrega diferenciais e contexto configurados no banco de dados
    from modules.ai.service.context.business_context import get_business_context_for_prompt
    biz_data_str = await get_business_context_for_prompt()

    prospecting_context_str = ""
    if org_id:
        try:
            from core.infra.database import async_session
            from models.organization import Organization
            from sqlalchemy import select
            async with async_session() as session:
                stmt = select(Organization.prospecting_context).where((Organization.id == org_id) | (Organization.pipedrive_id == org_id))
                res = await session.execute(stmt)
                pc = res.scalar_one_or_none()
                if pc:
                    prospecting_context_str = f"\n\n## PLANO DE PROSPECÇÃO (ESTRUTURA A SEGUIR):\n{pc}\n"
        except Exception:
            pass

    # ── Inteligência de Seleção de Canal
    requested_channel = args.get("channel")
    intent_signal = args.get("intent_signal", "")
    auto_channel = None
    
    # 1. Prioridade: Intent explícito no Goal, Intent Signal ou Channel
    _combined_context = f"{goal} {intent_signal} {requested_channel}".lower()
    
    if "email" in _combined_context or "e-mail" in _combined_context:
        auto_channel = "email"
        log.info("generate_sales_message.intent_detected", channel="email")
    elif "whatsapp" in _combined_context or "whats" in _combined_context:
        auto_channel = "whatsapp"
        log.info("generate_sales_message.intent_detected", channel="whatsapp")
    
    # 2. Se não houver intent claro, usa a lógica de histórico
    if not auto_channel:
        wa_count = 0
        email_count = 0
        for msg in messages:
            if msg.get("role") == "user":
                content = str(msg.get("content", ""))
                if "whatsapp_get_messages" in content:
                    import re
                    m = re.search(r"(\d+)\s+mensagens\s+com", content)
                    if m: wa_count += int(m.group(1))
                elif "email_get_contact_history" in content:
                    import re
                    m = re.search(r"(\d+)\s+e-mails\s+encontrados", content)
                    if m: email_count += int(m.group(1))

        if email_count > 0 and wa_count == 0:
            auto_channel = "email"
        elif wa_count > 0 and email_count == 0:
            auto_channel = "whatsapp"
        else:
            # Default para o que foi pedido ou whatsapp
            auto_channel = requested_channel.lower() if requested_channel else "whatsapp"
            
    # 3. Trava de Sanidade: Não pode mandar WhatsApp sem telefone
    if auto_channel == "whatsapp" and (not phone or phone == "None" or str(phone).strip() == ""):
        log.warning("generate_sales_message.sanity_check", msg="Alterando para email pois o telefone é nulo.")
        auto_channel = "email"

    channel = auto_channel or "whatsapp"

    channel_tone = (
        "CANAL: WhatsApp — seja direto, natural e conversacional. Parágrafos curtos. "
        f"Comece SEMPRE com '{greeting_hint}, [Nome]'. "
        "PROIBIDO incluir assinaturas formais (ex: 'Att. João', 'Atenciosamente', etc). "
        "A mensagem deve terminar de forma natural ou com um CTA, sem assinatura de e-mail."
        if channel == "whatsapp" else
        "CANAL: Email — pode ter mais profundidade técnica. Linha de assunto impactante. Evite parágrafos longos. "
        f"Comece com '{greeting_hint}, [Nome]'. "
        "Escreva o corpo do e-mail de forma profissional. "
        "Como a apresentação comercial em PDF será anexada automaticamente, você DEVE fazer referência a ela no texto do e-mail (ex: 'Estou enviando em anexo nossa apresentação...', 'Segue anexo nossa apresentação comercial...'). "
        "TERMINE SEMPRE o e-mail APENAS com 'Atenciosamente,'. É ESTRITAMENTE PROIBIDO colocar o seu nome, cargo (ex: Diretor Comercial Sênior) ou empresa abaixo do 'Atenciosamente', pois a assinatura em imagem será inserida automaticamente na parte inferior pelo sistema."
    )

    system_prompt = (
        "Você é um redator comercial B2B sênior. "
        "Sua ÚNICA tarefa é escrever UMA mensagem comercial completa e pronta para envio. "
        "Não faça diagnóstico, não liste opções, não explique sua estratégia. Escreva apenas a mensagem.\n\n"
        f"## CONTEXTO DA NOSSA EMPRESA E PROSPECÇÃO:\n{biz_data_str}\n{prospecting_context_str}\n"
        "## INTELIGÊNCIA DE CONTEXTO — LEIA O HISTÓRICO E DECIDA O MODO:\n\n"
        "**MODO 1 — FOLLOW-UP SIMPLES**\n"
        "Use quando: o objetivo é cobrar retorno/resposta/confirmação E o histórico não mostra objeções ativas nem férias/ausências recentes.\n"
        "→ Mensagem curta (máx. 3-4 linhas). Referencie o que ficou pendente. Tom humano, sem pressão. CTA único.\n"
        "→ PROIBIDO: diferenciais técnicos, laboratório, certificações, TCO, pitch de vendas. "
        "Inserir argumentos de venda num follow-up simples passa despreparo e é invasivo.\n\n"
        "**MODO 2 — FOLLOW-UP COM OBJEÇÃO**\n"
        "Use quando: o objetivo é dar continuidade MAS o histórico mostra uma objeção clara e não respondida "
        "(ex: 'está caro', 'estou com outro fornecedor', 'preciso pensar', reclamação de qualidade, prazo).\n"
        "→ Mensagem moderada (4-6 linhas). Reconheça o contexto brevemente, depois enderece a objeção "
        "com UM argumento cirúrgico e baseado em dados reais do histórico. Não faça lista de diferenciais — "
        "escolha o argumento mais relevante para aquela objeção específica. Feche com CTA claro.\n\n"
        "**MODO 3 — VENDA ATIVA**\n"
        "Use quando: primeiro contato, reativação de lead frio, apresentação de proposta, "
        "rebate de concorrente direto, criação de urgência comercial.\n"
        "→ Use os diferenciais técnicos e contexto da empresa acima. CHALLENGER SALE: ensine algo que o cliente "
        "ainda não sabe. SPIN SELLING: mencione dores reais do histórico. DATA-DRIVEN: cite itens reais "
        "(códigos, preços, datas). NUNCA use placeholders.\n\n"
        "**MODO 4 — RETORNO DE FÉRIAS / RAPPORT (SOFT FOLLOW-UP)**\n"
        "Use quando: o histórico recente (seja WhatsApp ou e-mail) indicar que o contato esteve de férias, ausente, viajando ou fora do escritório recentemente (ou se desculpou pelo atraso devido a esses motivos).\n"
        "→ Mensagem calorosa, empática e acolhedora. Dê as boas-vindas no retorno das férias/ausência, deseje que tenha descansado, tire ABSOLUTAMENTE toda a pressão de cobrança comercial e se coloque à disposição para quando a rotina dele normalizar. NÃO tente vender novos produtos cartonados ou cobrar cotações anteriores nesse momento. A prioridade máxima é gerar conexão (rapport) e se colocar à disposição. Feche de forma super leve e profissional.\n\n"
        "**MODO 5 — FOLLOW-UP DE VALOR (SEM RESPOSTA AO CONTATO INICIAL)**\n"
        "Use quando: a J.Ferres enviou a apresentação inicial ou um e-mail frio e o cliente NÃO respondeu (ghosting).\n"
        "→ PROIBIDO perguntar 'Você viu meu e-mail?'. Envie um Insight de Mercado. Dê uma dica ou compartilhe um dado sobre embalagens (ex: como a estrutura correta da onda do papelão reduz perdas logísticas no empilhamento de pallets). O objetivo não é vender de imediato, mas agregar valor técnico. Termine SEMPRE sugerindo uma reunião rápida de 15 minutos para mapeamento e diagnóstico da operação logística do cliente.\n\n"
        "## REGRAS UNIVERSAIS:\n"
        "- ALINHAMENTO CRONOLÓGICO: Analise rigorosamente a linha do tempo. Identifique e priorize o fato MAIS RECENTE da conversa. Nunca retome ou cobre cotações antigas que já foram canceladas ou substituídas se a negociação já avançou para outra etapa (ex: estudo de caixas, pesos, desenvolvimento de amostras físicas). Fale estritamente do status atual em aberto.\n"
        "- ZERO REDUNDÂNCIA: Não pergunte o que já foi respondido na mensagem mais recente (ex: se o cliente disse 'não obtive retorno ainda', não pergunte 'como está o andamento', mas sim valide que entende a correria e se coloque à disposição).\n"
        "- ANTI-GENÉRICO: JAMAIS comece com 'Prezado', 'Espero que esteja bem', 'Tudo bem?', 'Como vai?'\n"
        "- ZERO PLACEHOLDERS: nunca use [nome], [empresa], [item], [preço] — só dados reais\n"
        "- Tom natural, assertivo, sem desespero\n"
        f"Hoje é {datetime.now().strftime('%A, %d/%m/%Y')}.\n\n"
        f"{channel_tone}\n\n"
        "RETORNE APENAS O TEXTO DA MENSAGEM. Sem introdução, sem explicação, sem título. Só a mensagem."
    )

    prompt_user = (
        f"CONTATO: {contact_name}" + (f" (Tel: {phone})" if phone else "") + "\n"
        f"OBJETIVO: {goal}\n\n"
        "Leia TODO o histórico disponível. Identifique:\n"
        "1. O que está pendente/em aberto e qual a última mensagem real\n"
        "2. Se o contato esteve de férias/viagem/ausente recentemente ou se desculpou por isso na mensagem mais recente\n"
        "3. (CRÍTICO) Verifique a DIREÇÃO (Remetente vs Destinatário) e o TEMPO das mensagens mais recentes. Se a última mensagem da conversa foi enviada PELO USUÁRIO (João Luccas/você) recentemente, NÃO sugira enviar outra mensagem de acompanhamento agora para não ser invasivo. Sugira aguardar ou criar uma tarefa interna no Pipedrive.\n"
        "4. (CRÍTICO) NÃO ALUCINE produtos ou assuntos que não foram discutidos. Não mencione 'caixas CKD' ou outros produtos específicos a menos que estejam LITERALMENTE escritos no histórico recente do cliente.\n\n"
        "5. Se há objeções não respondidas do cliente\n"
        "6. Qual é o momento real da negociação (ex: envio de amostras físicas, análise de resistência)\n\n"
        "Depois escolha o modo correto e escreva a mensagem:\n"
        "- Contato ignorou apresentação inicial → MODO 5 (Insight de mercado + Reunião)\n"
        "- Contato retornou de férias/ausência recentemente → MODO 4 (rapport, empático, sem pressão)\n"
        "- Sem objeções ativas e no meio do fluxo → MODO 1 (follow-up simples, breve)\n"
        "- Com objeção não respondida → MODO 2 (follow-up + argumento cirúrgico)\n"
        "- Primeiro contato / venda ativa → MODO 3 (diferenciais + SPIN + dados reais)"
    )

    try:
        # Busca contexto do tenant para anexos e assinaturas
        tenant_ctx = await BusinessContextService.get_tenant_context()
        
        # 1. Sugestão Proativa de Anexos
        # Sempre sugerimos a apresentação 'apresentacao_linkb2b' se o canal for 'email' e houver apresentação configurada.
        # Caso contrário, mantemos a lógica condicional baseada no objetivo.
        suggested_attachment = None
        if tenant_ctx.get("presentation_path"):
            if channel == "email":
                suggested_attachment = "apresentacao_linkb2b"
            else:
                goal_lower = goal.lower()
                if any(kw in goal_lower for kw in ["apresentação", "apresentar", "introdução", "conhecer"]):
                    suggested_attachment = "apresentacao_linkb2b"

        res = await ask_llm(
            prompt=prompt_user,
            system=system_prompt,
            history=history_serialized,
            json_mode=False,
            temperature=0.4,
            tier=LLMTier.STANDARD
        )

        draft = res.text.strip()

        # A injeção da assinatura real é feita no momento do envio (exec_email_send),
        # mas injetamos a URL da imagem aqui para que o frontend carregue por padrão.
        if channel == "email" and "Atenciosamente," not in draft and "J.Ferres" not in draft:
            pass
        
        if channel == "email":
            # Injeta a URL da assinatura para o frontend exibir a imagem por padrão.
            # Como é uma string curta, não polui o contexto do LLM.
            draft = f'{draft}<br><br><!-- SIGNATURE_START --><img src="http://localhost:8000/api/v1/settings/v2/profile/signature/image" style="max-width: 400px; height: auto; border-radius: 8px;" /><!-- SIGNATURE_END -->'

        return {
            "ok": True,
            "contact_name": contact_name,
            "channel": channel,
            "recommended_message": draft,
            "attachment_name": suggested_attachment, # Passa para o frontend/próxima ferramenta
            "summary": f"Estratégia e rascunho para {channel} gerados com sucesso para {contact_name}." + (f" (Anexo sugerido: {suggested_attachment})" if suggested_attachment else "")
        }
    except Exception as e:
        log.exception("exec_generate_sales_message.failed", exc_info=e)
        return {"ok": False, "error": str(e)}


async def exec_open_hierarchy_drawer(args: dict, org_id: int | None = None) -> dict:
    """Solicita ao frontend que abra o mapeador de hierarquia para a empresa."""
    org_name = _fix_llama_corrupted_name(args.get("org_name") or "")
    # Prioridade: org_id dos args, depois org_id do contexto do loop
    resolved_org_id = args.get("org_id") or org_id

    # LLMs menores corrompem caracteres especiais (ã, õ, ç) ao gerar parâmetros.
    # Usa org_id para buscar o nome canônico do Pipedrive e evitar nome corrompido no scan.
    if resolved_org_id:
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            orgs = await pipedrive_service.list_organizations()
            for o in (orgs or []):
                if str(o.get("id")) == str(resolved_org_id):
                    org_name = o.get("name", org_name)
                    break
        except Exception:
            pass

    return {
        "ok": True,
        "status": "hierarchy_mapping_requested",
        "org_name": org_name,
        "org_id": resolved_org_id,
        "deal_id": args.get("deal_id"),
        "activity_id": args.get("activity_id"),
        "pre_task_id": args.get("pre_task_id"),
        "summary": f"Mapeador de hierarquia aberto para {org_name}. Aguardando o usuário iniciar o mapeamento.",
    }


async def exec_suggest_next_actions(args: dict, messages: list | None = None, org_id: int | None = None) -> dict:
    # Filtro de Repetição: detecta o que já foi feito na sessão para não sugerir o mesmo
    executed_tools = []
    if messages:
        for m in messages:
            if m.get("role") == "tool":
                executed_tools.append(m.get("tool_name"))
            elif m.get("role") == "assistant":
                mc = m.get("content")
                if isinstance(mc, list):
                    for b in mc:
                        if b.get("type") == "tool_use": executed_tools.append(b.get("name"))

    if messages:
        try:
            from modules.sales.service.strategy import sales_strategy_service
            strategy_res = await sales_strategy_service.analyze_and_suggest_actions(messages, org_id)
            if strategy_res:
                if strategy_res.get("ok"):
                    actions = strategy_res.get("actions", [])
                    
                    # Regra: se acabou de atualizar uma tarefa, remove sugestões de "Concluir atividade"
                    if "pipedrive_update_task" in executed_tools:
                        actions = [a for a in actions if "Concluir atividade" not in a.get("label", "") and "Marcar atividade como concluída" not in a.get("label", "")]
                    
                    return {
                        "ok": True,
                        "actions": actions,
                        "summary": strategy_res.get("summary", "")
                    }
                else:
                    from core.observability.logging_config import get_logger
                    logger = get_logger(__name__)
                    logger.error(f"sales_strategy_service falhou: {strategy_res}")
                    # If it explicitly returned ok=False, don't fall back silently to an empty list
                    return strategy_res
        except Exception as e:
            import traceback
            from core.observability.logging_config import get_logger
            logger = get_logger(__name__)
            logger.error(f"Erro em exec_suggest_next_actions (sales_strategy_service): {e}\n{traceback.format_exc()}")
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


async def exec_evaluate_prospects(args: dict, org_id: int | None = None) -> dict:
    org_name = args.get("org_name", "")
    if not org_id and args.get("org_id"):
        try:
            org_id = int(args["org_id"])
        except (ValueError, TypeError):
            pass

    try:
        from core.infra.database import async_session
        from models.organization import Organization
        from models.people.employee import Employee
        from modules.ai.service.context.business_context_service import BusinessContextService
        from core.llm import LLMTier, ask_llm
        from sqlalchemy import select, or_
        import json

        # 1. Resolver organização
        match = None
        if org_id:
            match = await _pipedrive_get_org_by_id(org_id)

        if not match and org_name:
            match, resolved_id = await _pipedrive_find_org(org_name)
            if resolved_id:
                org_id = resolved_id

        if not org_id and match:
            org_id = match.get("id")

        if not org_id:
            return {"ok": False, "error": f"Organização '{org_name or org_id}' não encontrada"}

        org_real_name = match.get("name") if match else org_name

        # 2. Buscar contatos locais da organização no banco de dados
        async with async_session() as session:
            stmt = select(Organization).where((Organization.id == org_id) | (Organization.pipedrive_id == org_id))
            res = await session.execute(stmt)
            local_org = res.scalar_one_or_none()

            if not local_org:
                return {"ok": False, "error": f"Organização '{org_real_name}' não encontrada no banco local."}

            stmt_emp = select(Employee).where(
                Employee.company_id == local_org.id,
                or_(Employee.role.is_(None), Employee.role != "Reprovado"),
                or_(Employee.department.is_(None), Employee.department != "Reprovado")
            )
            res_emp = await session.execute(stmt_emp)
            local_employees = res_emp.scalars().all()

        if not local_employees:
            return {
                "ok": False,
                "error": f"Nenhum contato mapeado encontrado no banco local para '{org_real_name}'."
            }

        # Filtrar "Análise Humana" se necessário ou manter para avaliação do LLM
        valid_employees = []
        for emp in local_employees:
            emp_email = (emp.email or "").lower()
            # Filtros básicos de ruído
            if any(noise in emp_email or noise in emp.name.lower() for noise in ["pcp", "rh", "financeiro", "adm", "nfe", "qualidade"]):
                continue
            valid_employees.append({
                "name": emp.name,
                "role": emp.role,
                "department": emp.department,
                "seniority": emp.seniority,
                "linkedin": emp.linkedin_url,
                "email": emp.email,
                "description": emp.description or ""
            })

        if not valid_employees:
            return {
                "ok": False,
                "error": f"Nenhum contato relevante (não-ruído) encontrado para '{org_real_name}'."
            }

        # 3. Buscar contexto de negócio e produto
        ctx = await BusinessContextService.get_tenant_context()
        products_list = list(ctx.get("products", {}).values())
        company_name = ctx.get("company_name", "J.Ferres")
        company_segment = ctx.get("company_segment", "")
        icp = ctx.get("icp", {})

        prospecting_context_str = ""
        if local_org and local_org.prospecting_context:
            prospecting_context_str = f"\n\nCONTEXTO ESTRATÉGICO / PLANO DE PROSPECÇÃO (ATENÇÃO - ALINHE-SE A ESTA ESTRATÉGIA):\n{local_org.prospecting_context}"

        # 4. Formatar Prompt da IA para pontuação e ranking de prospecção
        prompt = f"""
Você é um especialista em Enterprise B2B Sales e Mapeamento de Contatos Corporativos. Sua tarefa é analisar o grupo de contatos mapeados de uma empresa e identificar a melhor pessoa ou grupo de pessoas para prospectar (fazer cold outreach/cold call) com base nos nossos produtos.

NOSSA EMPRESA E PRODUTOS:
Empresa: {company_name} — {company_segment}
Produtos Configurados:
{json.dumps(products_list, ensure_ascii=False, indent=2)}

DIRETRIZES DO NOSSO ICP (Ideal Customer Profile):
Setores-alvo: {json.dumps(icp.get("industries", []), ensure_ascii=False)}
Decisores-alvo: {json.dumps(icp.get("decision_makers", []), ensure_ascii=False)}
Dores de Mercado que resolvemos: {json.dumps(icp.get("pain_points", []), ensure_ascii=False)}

EMPRESA CLIENTE:
Nome: {org_real_name}{prospecting_context_str}

CONTATOS MAPEADOS E APROVADOS (Para análise):
{json.dumps(valid_employees, ensure_ascii=False, indent=2)}

SUA ANÁLISE DEVE DETERMINAR:
1. Para cada contato, avalie de forma realista a adequação para prospecção ("suitability_score" de 0 a 100) baseando-se no cargo real da pessoa. 
   - ALERTA CRÍTICO: VOCÊ ESTÁ ESTRITAMENTE PROIBIDO DE INVENTAR DEPARTAMENTOS. Se a pessoa for de Vendas, não a coloque como Compras.
   - PRIORIDADE ABSOLUTA: Profissionais com palavras como 'Suprimentos', 'Compras', 'Logística', 'Supply', 'Procurement' no cargo real devem ter score altíssimo.
   - PREFIRA OPERACIONAIS/TÁTICOS: Dê um score MAIOR (ex: 95-100) para cargos como 'Comprador', 'Comprador Pleno', 'Analista de Suprimentos' do que para cargos C-Level/Diretoria (ex: 'Diretor de Suprimentos', 'Head de Supply' - score 80-85), pois os compradores são a melhor porta de entrada para prospecção inicial.
   - PENALIDADE: Profissionais de Vendas, Marketing, RH ou 'Diretores' de áreas não-relacionadas devem receber score muito baixo (abaixo de 30) se houver alguém da área de Compras/Suprimentos disponível.
2. Classifique em Tier (A: Decisor Principal - apenas Suprimentos/Compras se houver, B: Influenciador Importante, C: Usuário ou Baixa Prioridade).
3. Escreva um motivo clínico do porquê esse contato é ou não é bom ("key_reason").
4. Elabore um ângulo de abordagem personalizado (gancho/mensagem curta de cold approach) baseado na dor do cargo e nos diferenciais do nosso produto ("angle_of_approach").

RETORNE EXATAMENTE UM JSON COM ESTA ESTRUTURA:
{{
  "best_prospects": [
    {{
      "name": "Nome do contato",
      "role": "Cargo",
      "department": "Departamento",
      "suitability_score": 95,
      "suitability_tier": "A",
      "key_reason": "Motivo da pontuação...",
      "angle_of_approach": "Gancho de abordagem personalizado..."
    }}
  ],
  "overall_strategy": "Sua recomendação estratégica de como entrar nessa conta de forma coordenada."
}}
"""

        result = await ask_llm(
            prompt=prompt,
            system="Você é um Diretor de Vendas B2B experiente que desenha estratégias de prospecção de alta precisão baseadas em organogramas. Responda apenas com o JSON estruturado.",
            json_mode=True,
            # Scoring/ranking estruturado em JSON não exige o raciocínio pesado do tier DEEP
            # (gemini-2.5-pro) — STANDARD (gemini-2.5-flash) entrega isso bem mais rápido.
            # generate_prospecting_plan chama esta função e DEPOIS ainda faz sua própria
            # chamada DEEP para a prosa do plano — rebaixar aqui evita duas chamadas pesadas
            # em sequência sem perder qualidade na parte que realmente precisa do tier maior.
            tier=LLMTier.STANDARD
        )

        data = result.json_data or {}
        best_prospects = data.get("best_prospects", [])
        overall_strategy = data.get("overall_strategy", "Nenhuma estratégia retornada.")

        # 🚀 NOVO: Se a empresa NÃO tem nenhum contato no Pipedrive (nenhum funcionario tem pipedrive_id),
        # pedimos a confirmação usando a recomendação da IA.
        has_pipedrive = any(e.pipedrive_id is not None for e in local_employees)
        if not has_pipedrive and best_prospects:
            best = best_prospects[0]
            best_name = best.get("name", "Contato")
            best_role = best.get("role", "")
            return {
                "ok": True,
                "status": "confirmation_required",
                "message": f"Após analisar o organograma local da empresa usando Inteligência Artificial, identifiquei **{best_name}** ({best_role}) como o melhor perfil (Score: {best.get('suitability_score')}). Este contato ainda não está no Pipedrive. Deseja prosseguir com ele ou prefere mapear novos nomes?",
                "options": [
                    {"label": f"Usar contato local ({best_name})", "prompt": f"A IA selecionou {best_name} ({best_role}) como a melhor opção. Cadastre este contato no Pipedrive imediatamente e inicie a prospecção usando o gancho gerado na estratégia."},
                    {"label": "Mapear novos contatos", "prompt": "Não utilize os contatos locais sugeridos. Abra o mapeador de hierarquia (open_hierarchy_drawer) para buscar contatos mais atualizados."}
                ],
                "best_prospects": best_prospects,
                "overall_strategy": overall_strategy,
                "org_id": org_id,
                "org_name": org_real_name,
                "summary": f"IA avaliou os contatos locais e sugere {best_name} (Score {best.get('suitability_score')}). Aguardando confirmação do usuário."
            }

        return {
            "ok": True,
            "org_name": org_real_name,
            "best_prospects": best_prospects,
            "overall_strategy": overall_strategy,
            "summary": f"Análise de adequação de prospecção concluída para {org_real_name} com {len(best_prospects)} perfis mapeados."
        }

    except Exception as e:
        log.exception("exec_evaluate_prospects.failed")
        return {"ok": False, "error": str(e)}


async def exec_discover_and_validate_email(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Descobre e valida o e-mail profissional de um contato.
    Gera padrões comuns (ex: joao.moura, j.moura) e valida via DNS/Sintaxe.
    Pode usar pesquisa na web para encontrar e-mails reais citados publicamente.

    ATALHO: Se o contato já tiver um e-mail validado salvo no banco local ou no
    Pipedrive (label='verified'), retorna imediatamente esse e-mail sem fazer
    nenhuma busca externa. A validação só é executada se o e-mail não estiver
    confirmado previamente.
    """
    import re as _re
    from email_validator import validate_email, EmailNotValidError
    from modules.hierarchy.service.search_engine import get_duck_results as search_duckduckgo
    
    contact_name = (args.get("contact_name") or args.get("name") or "").strip()
    company_name = (args.get("org_name") or args.get("company_name") or "").strip()
    domain = (args.get("domain") or "").strip().lower()
    person_id = args.get("person_id")
    # Callback opcional (ex: request.is_disconnected) — se o cliente cancelar/desconectar,
    # interrompemos antes de persistir para não alterar emails após o "Cancelar".
    _cancel_check = args.get("cancel_check")

    async def _is_cancelled() -> bool:
        if not _cancel_check:
            return False
        try:
            return bool(await _cancel_check())
        except Exception:
            return False

    if not contact_name:
        return {"ok": False, "error": "Forneça o nome do contato (contact_name ou name)."}

    force = bool(args.get("force", False))

    # ── ATALHO: Email já validado no banco local ou Pipedrive ──────────────────
    # Verifica primeiro o banco local (mais rápido). Ignorado quando force=True.
    if person_id and not force:
        try:
            from core.infra.database import async_session
            from models.people.employee import Employee
            from sqlalchemy import select
            async with async_session() as session:
                stmt = select(Employee).where(
                    (Employee.pipedrive_id == str(person_id)) | (Employee.id == int(person_id))
                )
                emp = (await session.execute(stmt)).scalar_one_or_none()
                if emp and emp.email and "@" in emp.email and emp.email_verified:
                    saved_email = emp.email.strip()
                    log.info("exec_discover_and_validate_email.shortcut_local_db", email=saved_email, person_id=person_id)
                    return {
                        "ok": True,
                        "contact_name": contact_name,
                        "domain": saved_email.split("@")[-1],
                        "valid_emails": [{"email": saved_email, "status": "Válido (Salvo no sistema)", "source": "Banco Local"}],
                        "recommended": saved_email,
                        "smtp_result": "valid",
                        "summary": f"E-mail já validado para {contact_name}: {saved_email} (recuperado do banco local)"
                    }
        except Exception as _db_err:
            log.warning("exec_discover_and_validate_email.local_db_check_failed", error=str(_db_err))

    # Verifica Pipedrive (label='verified' ou email existente com person_id). Ignorado quando force=True.
    if person_id and not force:
        try:
            from modules.crm.service.pipedrive_service import pipedrive_service
            pd_person = await pipedrive_service.get_person_details(int(person_id))
            if isinstance(pd_person, dict):
                pd_emails = pd_person.get("email") or []
                if isinstance(pd_emails, list):
                    # Prioridade 1: email com label 'verified'
                    verified = next((e["value"] for e in pd_emails if isinstance(e, dict) and e.get("label") == "verified" and e.get("value")), None)
                    # Prioridade 2: email primary
                    primary = next((e["value"] for e in pd_emails if isinstance(e, dict) and e.get("primary") and e.get("value")), None)
                    saved_email = verified or primary
                    if saved_email and "@" in saved_email:
                        label_used = "verified" if verified else "primary"
                        log.info("exec_discover_and_validate_email.shortcut_pipedrive", email=saved_email, label=label_used, person_id=person_id)
                        return {
                            "ok": True,
                            "contact_name": contact_name,
                            "domain": saved_email.split("@")[-1],
                            "valid_emails": [{"email": saved_email, "status": "Válido (Salvo no Pipedrive)", "source": "Pipedrive"}],
                            "recommended": saved_email,
                            "smtp_result": "valid",
                            "summary": f"E-mail já salvo para {contact_name}: {saved_email} (recuperado do Pipedrive)"
                        }
        except Exception as _pd_err:
            log.warning("exec_discover_and_validate_email.pipedrive_check_failed", error=str(_pd_err))
    # ────────────────────────────────────────────────────────────────────────────

    # 1. Tenta descobrir o domínio se não fornecido
    if not domain and company_name:
        from modules.intelligence.service import intelligence_service
        enrich_res = await intelligence_service.enrich_company(company_name)
        if enrich_res.get("success") and enrich_res.get("main_option"):
            domain = enrich_res["main_option"].get("domain") or ""

    if not domain:
        return {"ok": False, "error": "Domínio da empresa não encontrado. Forneça o domínio ou certifique-se de que a empresa está enriquecida."}

    # Limpa o domínio (remove www. se houver)
    domain = domain.replace("www.", "")

    # 2. Gera candidatos baseados em padrões comuns (normalizando acentos)
    import unicodedata
    normalized_name = "".join(
        c for c in unicodedata.normalize("NFKD", contact_name.lower())
        if not unicodedata.combining(c)
    )
    name_parts = _re.sub(r"[^\w\s]", "", normalized_name).split()
    if not name_parts:
        return {"ok": False, "error": "Nome do contato inválido."}

    first = name_parts[0]
    last = name_parts[-1] if len(name_parts) > 1 else ""

    from core.external.email_service import generate_all_patterns

    # 2.5 Verifica se a empresa já tem um padrão de email confirmado
    org_id = args.get("org_id")
    domain_pattern: str | None = None
    _org_local_id: int | None = None

    try:
        from core.infra.database import async_session as _async_session
        from models.organization import Organization as _Org
        from sqlalchemy import select as _select, or_ as _or
        async with _async_session() as _s:
            _cond = []
            if domain:
                _cond.append(_Org.domain == domain)
            if org_id:
                try:
                    _cond.append(_Org.pipedrive_id == int(org_id))
                    _cond.append(_Org.id == int(org_id))
                except (ValueError, TypeError):
                    pass
            if _cond:
                _org_rec = (await _s.execute(_select(_Org).where(_or(*_cond)).limit(1))).scalars().first()
                if _org_rec:
                    _org_local_id = _org_rec.id
                    if _org_rec.email_pattern and not force:
                        domain_pattern = _org_rec.email_pattern
                        log.info("exec_discover_and_validate_email.pattern_reuse", domain=domain, pattern=domain_pattern)
    except Exception as _pe:
        log.warning("exec_discover_and_validate_email.pattern_lookup_failed", error=str(_pe))

    candidates = []
    valid_parts = [p for p in name_parts if p not in ['de', 'da', 'do', 'dos', 'das']]

    if len(valid_parts) > 1:
        main_first = valid_parts[0]
        for part in valid_parts[1:]:
            for e, _ in generate_all_patterns(main_first, part, domain):
                if e not in candidates:
                    candidates.append(e)
    else:
        candidates.append(f"{first}@{domain}")

    # Cliente cancelou antes da busca web → aborta (a busca web é o trecho mais lento).
    if await _is_cancelled():
        log.info("exec_discover_and_validate_email.cancelled_pre_web", contact=contact_name)
        return {"ok": False, "cancelled": True, "contact_name": contact_name}

    # 3. Pesquisa na Web por padrão do domínio — executa UMA VEZ por empresa (não por pessoa)
    # Busca qualquer email do domínio para inferir o padrão corporativo antes de testar variações individuais.
    found_in_web = []
    generic_emails = []

    if not domain_pattern:
        _domain_queries = [
            f'"@{domain}"',
            f'"{company_name}" "@{domain}"' if company_name else None,
        ]
        _detected_domain_emails = []
        for _dq in _domain_queries:
            if not _dq:
                continue
            try:
                _dresults = await search_duckduckgo(_dq, max_results=5, filter_linkedin=False)
                for _dr in _dresults:
                    _dsnippet = _dr.get("snippet", "") + " " + _dr.get("title", "")
                    _demails = _re.findall(r'[\w\.-]+@' + _re.escape(domain), _dsnippet.lower())
                    _detected_domain_emails.extend(_demails)
            except Exception:
                pass
            if _detected_domain_emails:
                break

        if _detected_domain_emails:
            from core.external.email_service import detect_domain_pattern as _detect_dp
            _inferred_pattern = _detect_dp(_detected_domain_emails, domain)
            if _inferred_pattern:
                domain_pattern = _inferred_pattern
                # Salva imediatamente para que as próximas pessoas usem sem nova busca
                try:
                    from core.infra.database import async_session as _asw
                    from models.organization import Organization as _OrgW
                    from sqlalchemy import select as _selw, or_ as _orw
                    async with _asw() as _sw:
                        _wc = [_OrgW.id == _org_local_id] if _org_local_id else ([_OrgW.domain == domain] if domain else [])
                        if _wc:
                            _ow = (await _sw.execute(_selw(_OrgW).where(_orw(*_wc)).limit(1))).scalars().first()
                            if _ow and not _ow.email_pattern:
                                _ow.email_pattern = domain_pattern
                                await _sw.commit()
                                log.info("exec_discover_and_validate_email.pattern_web_discovered", domain=domain, pattern=domain_pattern)
                except Exception:
                    pass
            else:
                # Encontrou emails mas não identificou padrão → usa como candidatos adicionais
                for _de in set(_detected_domain_emails):
                    _de_norm = "".join(c for c in unicodedata.normalize("NFKD", _de) if not unicodedata.combining(c))
                    if _de_norm not in found_in_web:
                        found_in_web.append(_de_norm)

        job_title = (args.get("job_title") or "").strip().lower()
        if job_title:
            if "compra" in job_title or "suprimento" in job_title or "buyer" in job_title:
                generic_emails.extend([f"compras@{domain}", f"suprimentos@{domain}", f"compras1@{domain}"])
            elif "venda" in job_title or "comercial" in job_title or "sales" in job_title:
                generic_emails.extend([f"vendas@{domain}", f"comercial@{domain}", f"contato@{domain}"])
            elif "diretor" in job_title or "ceo" in job_title or "sócio" in job_title or "socio" in job_title:
                generic_emails.extend([f"diretoria@{domain}", f"ceo@{domain}", f"contato@{domain}"])
            elif "rh" in job_title or "recursos humanos" in job_title or "hr" in job_title:
                generic_emails.extend([f"rh@{domain}", f"recursoshumanos@{domain}", f"curriculos@{domain}"])
            elif "ti" in job_title or "tecnologia" in job_title or "it" in job_title:
                generic_emails.extend([f"ti@{domain}", f"suporte@{domain}", f"tecnologia@{domain}"])
            elif "financeiro" in job_title or "faturamento" in job_title:
                generic_emails.extend([f"financeiro@{domain}", f"faturamento@{domain}", f"boletos@{domain}"])
            elif "marketing" in job_title:
                generic_emails.extend([f"marketing@{domain}", f"mkt@{domain}", f"contato@{domain}"])

    if not domain_pattern or domain_pattern == "web_harvested":
        # Sem padrão confirmado: testa todos os padrões para todas as combinações de partes do nome.
        # web_harvested = ainda não sabemos o padrão real → mesma lógica de descoberta completa.
        all_additional = list(set(found_in_web + generic_emails + candidates))
    else:
        all_additional = None

    # 4. Validação multi-sinal via email_service (resiliente a catch-all)
    from core.external.email_service import validate_email_smart

    # Modo estrito (1 email, 2 chamadas MS) apenas para padrões canônicos confirmados.
    # Sem padrão ou web_harvested: testa todos os candidatos gerados acima.
    _strict_pattern = bool(domain_pattern) and domain_pattern != "web_harvested"

    # Cliente já cancelou antes da validação pesada → aborta cedo (economiza ~10s).
    if await _is_cancelled():
        log.info("exec_discover_and_validate_email.cancelled_early", contact=contact_name)
        return {"ok": False, "cancelled": True, "contact_name": contact_name}

    discovery_res = await validate_email_smart(
        first=first,
        last=last,
        domain=domain,
        known_pattern=domain_pattern if domain_pattern != "web_harvested" else None,
        only_known_pattern=_strict_pattern,
        additional_candidates=all_additional,
        pattern_match=_strict_pattern,
    )
    
    valid_emails = []
    # Converte o resultado unificado para o formato esperado pelo drawer
    if discovery_res.get("email"):
        smtp_res = discovery_res.get("smtp_result")
        confidence = discovery_res.get("confidence", "low")
        
        if smtp_res == "valid":
            status_str = "Válido (Confirmado)"
        elif smtp_res == "catchall":
            status_str = "Incerto (Servidor Catch-All)"
        elif smtp_res == "invalid":
            status_str = "Não Confirmado"
        else:
            status_str = "Estimado (DNS OK - Sem confirmação)"
        
        # O e-mail recomendado fica sempre em primeiro lugar
        valid_emails.append({
            "email": discovery_res["email"],
            "status": status_str,
            "source": "Web" if discovery_res["email"] in found_in_web else "Padrão Sugerido"
        })
        
        # Adiciona os outros candidatos testados como opções secundárias no Drawer
        for email in discovery_res.get("all_candidates", []):
            if email != discovery_res["email"]:
                valid_emails.append({
                    "email": email,
                    "status": "Sugestão",
                    "source": "Web" if email in found_in_web else "Padrão Sugerido"
                })

    smtp_result = discovery_res.get("smtp_result")
    _verdict = discovery_res.get("verdict")
    _identity_score = discovery_res.get("identity_score")
    _evidence = discovery_res.get("evidence", [])
    is_confirmed = smtp_result == "valid"

    # Padrão canônico confirmado + MS não rejeitou explicitamente = confiança suficiente.
    # Domínios catch-all aceitam qualquer email no ping, mas se o padrão foi derivado
    # de um email confirmado anteriormente, a geração pelo padrão é confiável.
    _canonical_pattern = domain_pattern and domain_pattern not in (None, "web_harvested")
    _canonical_forced = False  # True quando confirmado só por padrão + catchall (sem bypass real)

    # Veredito negativo da fusão multi-sinal (ex: servidor rejeitou o endereço real) bloqueia.
    if _verdict == "invalid":
        is_confirmed = False
    elif not is_confirmed and smtp_result == "catchall":
        # Catch-all: aceita o melhor candidato independentemente de ter padrão canônico.
        # Com padrão canônico é mais confiável; sem padrão (force=True) ainda é melhor
        # que nada, pois o domínio aceita qualquer endereço de qualquer forma.
        is_confirmed = True
        _canonical_forced = True

    log.info(
        "exec_discover_and_validate_email.identity",
        email=discovery_res.get("email"), score=_identity_score,
        verdict=_verdict, evidence=len(_evidence),
    )

    # Cliente cancelou/desconectou durante a validação → não persiste nada.
    # Garante que o "Cancelar" no frontend realmente pare de alterar emails.
    if await _is_cancelled():
        log.info("exec_discover_and_validate_email.cancelled", contact=contact_name, email=discovery_res.get("email"))
        return {"ok": False, "cancelled": True, "contact_name": contact_name}

    # Só salva automaticamente no banco/Pipedrive se o email foi CONFIRMADO
    recommended = discovery_res.get("email") if is_confirmed else None
    person_id = args.get("person_id")

    if is_confirmed and recommended:
        # Salva o padrão validado na organização para reutilização futura
        found_pattern = discovery_res.get("pattern")

        # Se o padrão retornado é genérico (web_harvested), tenta inferir o padrão real
        # a partir do email confirmado cruzado com todas as partes do nome completo.
        if found_pattern == "web_harvested" and valid_parts:
            from core.external.email_service import infer_pattern_from_email as _infer_patt
            _inferred = _infer_patt(recommended, valid_parts)
            if _inferred:
                found_pattern = _inferred
                log.info("exec_discover_and_validate_email.pattern_inferred_from_email",
                         email=recommended, pattern=found_pattern)

        # Salva se ainda não há padrão, ou se o existente é web_harvested (impreciso).
        # Com force=True, o usuário pediu redescoberta total → sobrescreve o padrão antigo
        # (corrige padrões obsoletos/errados salvos por validações anteriores).
        _no_real_pattern = not domain_pattern or domain_pattern == "web_harvested"
        if found_pattern and (_no_real_pattern or force):
            try:
                from core.infra.database import async_session as _as2
                from models.organization import Organization as _Org2
                from sqlalchemy import select as _sel2, or_ as _or2
                async with _as2() as _s2:
                    _cond2 = []
                    if _org_local_id:
                        _cond2.append(_Org2.id == _org_local_id)
                    elif domain:
                        _cond2.append(_Org2.domain == domain)
                    if _cond2:
                        _o = (await _s2.execute(_sel2(_Org2).where(_or2(*_cond2)).limit(1))).scalars().first()
                        _can_save = _o and (not _o.email_pattern or _o.email_pattern == "web_harvested" or force)
                        if _can_save and _o.email_pattern != found_pattern:
                            _old = _o.email_pattern
                            _o.email_pattern = found_pattern
                            await _s2.commit()
                            log.info("exec_discover_and_validate_email.pattern_saved", domain=domain, pattern=found_pattern, old=_old)
            except Exception as _se:
                log.warning("exec_discover_and_validate_email.pattern_save_failed", error=str(_se))

        if person_id:
            try:
                from modules.crm.service.pipedrive_service import pipedrive_service
                await pipedrive_service.update_person(
                    int(person_id),
                    {"email": [{"value": recommended, "primary": True, "label": "verified"}]}
                )

                from core.infra.database import async_session
                from models.people import Employee
                from sqlalchemy import select

                async with async_session() as session:
                    stmt = select(Employee).where(
                        (Employee.pipedrive_id == str(person_id)) | (Employee.id == int(person_id))
                    )
                    emp = (await session.execute(stmt)).scalar_one_or_none()
                    if emp:
                        # Não sobrescreve email já bypass-confirmado com resultado apenas catchall+canonical
                        _already_bypass = emp.email_verified and emp.email
                        if not _canonical_forced or not _already_bypass:
                            emp.email = recommended
                            emp.email_verified = not _canonical_forced
                            await session.commit()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Erro ao salvar email validado no BD/Pipedrive: {e}")

        return {
            "ok": True,
            "contact_name": contact_name,
            "domain": domain,
            "recommended": recommended,
            "smtp_result": smtp_result,
            "pattern": discovery_res.get("pattern"),
            "identity_score": _identity_score,
            "verdict": _verdict,
            "evidence": _evidence,
            "summary": f"E-mail confirmado para {contact_name}: {recommended}"
        }

    # Não confirmado — retorna sem sugestão (zero incerteza exposta ao usuário)
    return {
        "ok": False,
        "contact_name": contact_name,
        "domain": domain,
        "error": f"E-mail não encontrado para {contact_name} no domínio {domain}.",
        "smtp_result": smtp_result,
        "identity_score": _identity_score,
        "verdict": _verdict,
        "evidence": _evidence,
    }


async def exec_generate_dossier(args: dict) -> dict:
    """Sinaliza a fase de consolidação. Não faz chamada externa — apenas libera o agente para gerar o dossiê."""
    return {
        "ok": True,
        "summary": "Consolidação iniciada. Gere o dossiê final agora.",
    }

async def exec_update_prospecting_context(args: dict) -> dict:
    """Salva o contexto qualitativo e a temperatura do lead na base local."""
    org_id = args.get("org_id")
    person_id = args.get("person_id")
    temperature = args.get("temperature")
    context = args.get("context")

    if not org_id and not person_id:
        return {"ok": False, "error": "É necessário informar org_id ou person_id."}

    try:
        from core.infra.database import async_session
        from models.organization import Organization
        from models.people import Employee
        from sqlalchemy import select

        updated = []
        async with async_session() as session:
            # Atualiza organização
            if org_id:
                stmt = select(Organization).where(
                    (Organization.pipedrive_id == org_id) | (Organization.id == org_id)
                )
                org = (await session.execute(stmt)).scalar_one_or_none()
                if org:
                    if temperature:
                        org.temperature = temperature
                    if context:
                        # Append context to preserve history
                        if org.prospecting_context and context not in org.prospecting_context:
                            org.prospecting_context += f" | {context}"
                        else:
                            org.prospecting_context = context
                    updated.append(f"Organização '{org.name}'")
            
            # Atualiza pessoa
            if person_id:
                stmt = select(Employee).where(
                    (Employee.pipedrive_id == str(person_id)) | (Employee.id == person_id)
                )
                emp = (await session.execute(stmt)).scalar_one_or_none()
                if emp:
                    if temperature:
                        emp.temperature = temperature
                    if context:
                        if emp.prospecting_context and context not in emp.prospecting_context:
                            emp.prospecting_context += f" | {context}"
                        else:
                            emp.prospecting_context = context
                    updated.append(f"Contato '{emp.name}'")

            await session.commit()

        if updated:
            return {"ok": True, "summary": f"Contexto de prospecção atualizado para: {', '.join(updated)}"}
        else:
            return {"ok": False, "error": "Registro não encontrado no banco local para atualizar o contexto."}
    except Exception as e:
        return {"ok": False, "error": f"Erro ao atualizar contexto: {e}"}


async def exec_generate_prospecting_plan(args: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    Gera um Plano de Prospecção B2B detalhado (SPIN Selling) para a empresa.
    Cruza dados de decisores mapeados com o perfil do tenant para gerar um
    plano estruturado em Markdown e salvar no prospecting_context da organização.
    Se a empresa já tiver um plano de prospecção salvo, retorna-o diretamente
    para evitar chamadas de LLM redundantes e preservar edições.
    """
    from core.infra.database import async_session
    from models.organization import Organization
    from models.people.employee import Employee
    from sqlalchemy import select, or_
    from core.llm.router import ask_llm
    from core.llm.base import LLMTier
    from modules.ai.service.context.business_context_service import BusinessContextService

    org_id = args.get("org_id")
    force_regenerate = args.get("force_regenerate", False) in (True, "true", 1, "1")
    if not org_id:
        return {"ok": False, "error": "org_id é obrigatório para gerar o plano de prospecção."}

    # Tenta obter a representação em inteiro de org_id para resiliência no banco local
    org_id_int = None
    try:
        org_id_int = int(org_id)
    except (ValueError, TypeError):
        pass

    try:
        # 1. Carrega a organização e seus funcionários/decisores do banco local
        async with async_session() as session:
            conditions = [
                Organization.id == org_id,
                Organization.pipedrive_id == org_id
            ]
            if org_id_int is not None:
                conditions.append(Organization.id == org_id_int)
                conditions.append(Organization.pipedrive_id == org_id_int)

            res = await session.execute(select(Organization).where(or_(*conditions)))
            org = res.scalars().first()
            if not org:
                return {"ok": False, "error": f"Organização {org_id} não encontrada no banco local."}

            # Se já existir um plano no prospecting_context, reutiliza
            if not force_regenerate and org.prospecting_context and len(org.prospecting_context.strip()) > 100:
                log.info("exec_generate_prospecting_plan.existing_plan_found", org_id=org.id)
                return {
                    "ok": True,
                    "plan": org.prospecting_context,
                    "org_name": org.name,
                    "summary": f"Plano de prospecção existente retornado para {org.name}."
                }

            # Resolução resiliente de Pipedrive ID
            pd_id = org.pipedrive_id
            if not pd_id:
                try:
                    from ._utils import _pipedrive_find_org
                    _, resolved_id = await _pipedrive_find_org(org.name)
                    if resolved_id:
                        pd_id = resolved_id
                        org.pipedrive_id = resolved_id
                        await session.commit()
                except Exception as e:
                    log.warning("generate_prospecting_plan.resolve_pipedrive_failed", org_id=org.id, error=e)

            # Busca e-mails e WhatsApps do cache local
            from models.communication.contact_cache import ContactConversationCache
            stmt_cache = select(ContactConversationCache).where(
                or_(
                    ContactConversationCache.org_id == org.id,
                    ContactConversationCache.org_id == pd_id,
                    ContactConversationCache.org_name == org.name
                )
            )
            res_cache = await session.execute(stmt_cache)
            cached_convs = []
            for conv in res_cache.scalars().all():
                cached_convs.append({
                    "channel": conv.channel,
                    "contact_name": conv.contact_name,
                    "contact_identifier": conv.contact_identifier,
                    "messages": conv.get_messages()
                })

            res_emps = await session.execute(
                select(Employee).where(
                    Employee.company_id == org.id,
                    Employee.role.notin_(["Reprovado", "Análise Humana", "Erro no Processamento"])
                )
            )
            employees = res_emps.scalars().all()

        # 1.5. Busca dados do CRM (Pipedrive) em tempo real
        deals_list = []
        activities_list = []
        notes_list = []
        if pd_id:
            try:
                from modules.crm.service.pipedrive_service import pipedrive_service
                pd_details = await pipedrive_service.get_organization_details(pd_id)
                if isinstance(pd_details, dict):
                    deals_list = pd_details.get("deals") or []
                    activities_list = pd_details.get("activities") or []
                    notes_list = pd_details.get("notes") or []
            except Exception as pd_err:
                log.warning("generate_prospecting_plan.pipedrive_fetch_failed", org_id=org.id, error=pd_err)

        # Formata Deals do CRM
        STAGE_NAMES = {
            2: "Entrada (Novos Negócios)", 18: "Qualificação", 19: "Contatado", 
            4: "Reunião Agendada", 26: "Reunião Realizada", 27: "Proposta em Andamento", 28: "Em Negociação",
            14: "Entrada (Carteira)", 16: "Contato", 17: "Proposta", 32: "Programação"
        }
        deals_summary_lines = []
        for d in deals_list:
            title = d.get("title", "Sem título")
            status = d.get("status", "N/A")
            stage_val = d.get("stage_id")
            stage_name = STAGE_NAMES.get(stage_val, f"Etapa {stage_val}" if stage_val else "N/A")
            value = d.get("value", 0)
            currency = d.get("currency", "BRL")
            updated = (d.get("update_time") or "")[:10]
            deals_summary_lines.append(
                f"- Deal: '{title}' | Status: {status} | Etapa: {stage_name} | Valor: {value} {currency} | Atualizado: {updated}"
            )
        deals_summary_text = "\n".join(deals_summary_lines) if deals_summary_lines else "Nenhum negócio (deal) registrado no CRM."

        # Formata Atividades do CRM
        activities_summary_lines = []
        for a in activities_list:
            done_status = "Concluída" if a.get("done") else "Pendente"
            subject = a.get("subject", "Sem assunto")
            act_type = a.get("type", "Tarefa")
            due_date = a.get("due_date") or "sem prazo"
            note = a.get("note") or ""
            import re
            clean_note = re.sub(r'<[^>]*>', '', note).strip() if note else ""
            note_str = f" | Nota: {clean_note[:120]}..." if clean_note else ""
            activities_summary_lines.append(
                f"- [{done_status}] {act_type.upper()}: {subject} (Data: {due_date}){note_str}"
            )
        activities_summary_text = "\n".join(activities_summary_lines[:15]) if activities_summary_lines else "Nenhuma atividade (tarefa) registrada no CRM."

        # Formata Anotações do CRM
        notes_summary_lines = []
        for n in notes_list:
            content = n.get("content", "")
            add_time = (n.get("add_time") or "")[:10]
            import re
            clean_content = re.sub(r'<[^>]*>', '', content).strip() if content else ""
            if clean_content:
                notes_summary_lines.append(f"- [{add_time}]: {clean_content[:300]}")
        notes_summary_text = "\n".join(notes_summary_lines[:10]) if notes_summary_lines else "Nenhuma anotação registrada no CRM."

        # Formata Comunicações (E-mail e WhatsApp)
        comm_summary_lines = []
        for conv in cached_convs:
            channel_name = "WhatsApp" if conv["channel"] == "whatsapp" else "E-mail"
            contact_name = conv["contact_name"]
            identifier = conv["contact_identifier"]
            
            msgs = conv["messages"]
            if conv["channel"] == "email":
                msgs = list(reversed(msgs))  # Coloca cronológico antigo -> novo
                
            formatted_msgs = []
            for m in msgs[-15:]:  # últimas 15 mensagens
                sender = m.get("sender") or m.get("from") or ("Você" if m.get("fromMe") or m.get("direction") == "sent" else contact_name)
                body = m.get("body") or m.get("preview") or m.get("content") or ""
                import re
                clean_body = re.sub(r'<[^>]*>', '', body).strip()
                if clean_body:
                    formatted_msgs.append(f"  [{sender}]: {clean_body[:200]}")
            
            if formatted_msgs:
                comm_summary_lines.append(
                    f"### Conversa via {channel_name} com {contact_name} ({identifier}):\n" + "\n".join(formatted_msgs)
                )
        comm_summary_text = "\n\n".join(comm_summary_lines) if comm_summary_lines else "Nenhum histórico de e-mails ou WhatsApp encontrado no banco local."

        # 2. Carrega o contexto do tenant (nosso produto, ICP, etc.)
        business_ctx = await BusinessContextService.get_tenant_context()
        product_info = business_ctx.get("product_description", "Empresa B2B de alto valor.")
        company_name = business_ctx.get("company_name", "J.Ferres")
        icp_profile = business_ctx.get("icp_profile", "")
        differentials = business_ctx.get("differentials", "")

        # 3. Avalia os prospects usando a ferramenta centralizada
        eval_res = await exec_evaluate_prospects({"org_id": org.id})
        best_prospects_data = eval_res.get("best_prospects", []) if eval_res.get("ok") else []
        overall_strategy = eval_res.get("overall_strategy", "") if eval_res.get("ok") else ""

        # Monta o perfil de todos os decisores (para contexto adicional)
        decision_makers = []
        for emp in employees:
            dm = {
                "name": emp.name,
                "role": emp.role or "Cargo não informado",
                "department": getattr(emp, "department", "") or "",
                "seniority": getattr(emp, "seniority", 0) or 0,
                "linkedin": getattr(emp, "linkedin_url", "") or "",
                "email": getattr(emp, "email", "") or "",
                "evidence": getattr(emp, "evidence", "") or "",
                "matching_score": getattr(emp, "matching_score", 0) or 0,
            }
            decision_makers.append(dm)

        # Ordena por score desc
        decision_makers.sort(key=lambda x: x["matching_score"], reverse=True)

        # 4. Gera o plano via LLM
        import json
        prompt = f"""Gere um Plano de Prospecção B2B completo e detalhado para a empresa abaixo.
Use todo o histórico de interações (deals, atividades, notas e mensagens de e-mail/WhatsApp) para contextualizar o plano.
O plano deve levar em consideração o momento comercial atual e as tentativas ou conversas de prospecção já iniciadas pelo vendedor para evitar repetir abordagens cansativas ou inadequadas, adaptando a primeira mensagem pronta e a sequência de abordagem a esse histórico real.

## EMPRESA ALVO:
- Nome: {org.name}
- Domínio: {getattr(org, 'domain', '') or 'não informado'}
- CNPJ: {getattr(org, 'cnpj', '') or 'não informado'}
- Contexto salvo: {getattr(org, 'prospecting_context', '') or 'nenhum'}

## HISTÓRICO DE INTERAÇÕES E MOMENTO COMERCIAL (INVESTIGAÇÃO DO CRM E COMUNICAÇÕES):

### 1. Negócios (Deals) no CRM:
{deals_summary_text}

### 2. Histórico de Atividades (Tarefas) no CRM:
{activities_summary_text}

### 3. Anotações Gerais do CRM:
{notes_summary_text}

### 4. Histórico Recente de Comunicações (E-mails e WhatsApp):
{comm_summary_text}

## DECISORES MAPEADOS ({len(decision_makers)} pessoas):
{json.dumps(decision_makers, indent=2, ensure_ascii=False)}

## AVALIAÇÃO PRÉVIA DA IA (USE COMO BASE PARA O PLANO):
{json.dumps(best_prospects_data, indent=2, ensure_ascii=False) if best_prospects_data else "Nenhuma avaliação prévia disponível."}
Estratégia Geral Sugerida: {overall_strategy}

## NOSSO PRODUTO/SERVIÇO:
{product_info}

## ICP (Perfil de Cliente Ideal):
{icp_profile}

## NOSSOS DIFERENCIAIS:
{differentials}

## INSTRUÇÃO:
Gere um plano de prospecção SPIN Selling completo com as seguintes seções:

REGRAS CRÍTICAS DE AVALIAÇÃO:
- NUNCA invente ou presuma departamentos. Baseie-se ESTRITAMENTE nos cargos reais fornecidos.
- O DECISOR PRINCIPAL/PONTO DE ENTRADA IDEAL deve obrigatoriamente ser alguém da área de Suprimentos, Compras, Logística ou Supply Chain.
- PREFIRA SEMPRE cargos táticos/operacionais (ex: Comprador, Comprador Pleno, Analista de Suprimentos, Assistente de Compras) em vez de cargos C-Level ou Diretoria (ex: Diretor, VP, Head), pois os compradores lidam diretamente com o dia a dia e são a melhor porta de entrada. Portanto, se houver um 'Comprador' e um 'Diretor', escolha o 'Comprador' (ex: Julio).

REGRA CRÍTICA DE CONTINUIDADE DE NEGOCIAÇÃO (NÃO TROCAR DE DECISOR SEM MOTIVO REAL):
- Antes de recomendar um "Decisor Principal" diferente de quem já está em conversa, analise com cuidado a seção 4 (Histórico Recente de Comunicações) e as Atividades/Notas do CRM.
- Se já existe uma negociação com avanço real com algum contato (ele respondeu, trocou mensagens, pediu detalhes/proposta/amostra, fez perguntas, agendou algo, etc.), o plano DEVE manter esse mesmo contato como Decisor Principal — mesmo que a "AVALIAÇÃO PRÉVIA DA IA" indique outro decisor com cargo/score teoricamente melhor. Continuidade de relacionamento e progresso real valem mais que o cargo ideal.
- Só recomende migrar a abordagem para outro decisor quando o contato atual estiver claramente "esfriado"/sendo ignorado: nenhuma resposta após pelo menos 2 tentativas de follow-up genuínas (e-mail e/ou WhatsApp) em intervalo razoável. Nesse caso, deixe explícito no plano que a troca é motivada pela falta de resposta, não apenas por um cargo mais adequado.
- Em caso de dúvida sobre se a conversa avançou o suficiente para travar a troca, seja conservador e mantenha o contato atual.

1. **🎯 Análise da Conta** — Perfil da empresa, porte, segmento, potencial com base no histórico comercial/deals existentes e momento da prospecção
2. **👤 Decisor Principal Recomendado** — Nome, cargo, por que ele/ela é a melhor entrada, gancho personalizado adaptado ao histórico real de conversas/tentativas. RESPEITE A REGRA CRÍTICA DE CONTINUIDADE DE NEGOCIAÇÃO: se já há negociação em andamento com alguém, mantenha-o como decisor principal; só troque se ele estiver sendo ignorado.
3. **🔎 Dores Prováveis (Situação → Problema)** — 3-5 dores baseadas no segmento/cargo e conversas anteriores
4. **💡 Implicações das Dores** — O impacto de não resolver cada dor
5. **🚀 Sequência de Abordagem** — Canal 1 (qual canal, script inicial), Canal 2 (follow-up), Canal 3 (escalada), levando em consideração canais já utilizados
6. **📝 Primeira Mensagem Pronta** — Mensagem real, sem placeholders, pronta para enviar (adaptada ao momento: se for o primeiro contato, uma mensagem fria; se já há conversa, uma mensagem de acompanhamento ou retomada de contato baseada no último assunto discutido)
7. **⚡ Próximas Ações Concretas** — Lista de 3-5 ações com prazo

Formato: Markdown rico. Use o nome real do decisor e detalhes reais da empresa. Seja específico e executável."""

        result = await ask_llm(
            prompt=prompt,
            system=(
                f"Você é um Diretor Comercial B2B Sênior especialista em SPIN Selling. "
                f"Gere planos de prospecção altamente personalizados e executáveis para a empresa {company_name}."
            ),
            tier=LLMTier.DEEP,
            temperature=0.2,
        )

        plan_md = result.text or "Erro ao gerar plano."

        # 5. Salva o plano no prospecting_context da organização
        async with async_session() as session:
            res = await session.execute(select(Organization).where(Organization.id == org.id))
            org_to_update = res.scalars().first()
            if org_to_update:
                org_to_update.prospecting_context = plan_md
                await session.commit()

        return {
            "ok": True,
            "plan": plan_md,
            "org_name": org.name,
            "summary": (
                f"Plano SPIN Selling gerado e salvo para {org.name} com {len(decision_makers)} decisores. "
                f"O plano está visível na interface. Prossiga com suggest_next_actions."
            ),
        }

    except Exception as e:
        log.exception("exec_generate_prospecting_plan.failed")
        return {"ok": False, "error": str(e)}


async def exec_update_prospecting_plan(args: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """
    Atualiza e substitui o plano de prospecção existente de uma organização
    por um novo plano fornecido pelo agente.
    """
    from core.infra.database import async_session
    from models.organization import Organization
    from sqlalchemy import select, or_

    org_id = args.get("org_id")
    new_plan = args.get("new_plan", "")

    if not org_id:
        return {"ok": False, "error": "org_id é obrigatório."}
    if not new_plan:
        return {"ok": False, "error": "new_plan não pode estar vazio."}

    # Tenta obter a representação em inteiro de org_id para resiliência no banco local
    org_id_int = None
    try:
        org_id_int = int(org_id)
    except (ValueError, TypeError):
        pass

    try:
        async with async_session() as session:
            conditions = [
                Organization.id == org_id,
                Organization.pipedrive_id == org_id
            ]
            if org_id_int is not None:
                conditions.append(Organization.id == org_id_int)
                conditions.append(Organization.pipedrive_id == org_id_int)

            res = await session.execute(select(Organization).where(or_(*conditions)))
            org = res.scalars().first()
            if not org:
                return {"ok": False, "error": f"Organização {org_id} não encontrada."}

            org.prospecting_context = new_plan
            await session.commit()

        return {
            "ok": True,
            "summary": f"Plano de prospecção atualizado para {org.name}.",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def batch_discover_and_validate_org_emails(org_id: int):
    """
    Superteste em lote: Varrer todos os funcionários de uma organização,
    descobrir e validar e-mails, salvar válidos e deletar os inválidos do Pipedrive.
    """
    import asyncio
    import time
    from core.infra.database import async_session
    from models.people import Employee
    from models.organization import Organization
    from sqlalchemy import select
    from modules.crm.service.pipedrive_service import pipedrive_service
    
    async with async_session() as session:
        stmt = select(Organization).where(Organization.id == org_id)
        org = (await session.execute(stmt)).scalars().first()
        
        if not org or not org.domain:
            return {"ok": False, "error": "Organização não encontrada ou sem domínio"}
            
        stmt = select(Employee).where(Employee.company_id == org.id)
        employees = (await session.execute(stmt)).scalars().all()
        
    verified_pipedrive_ids = set()
    if org.pipedrive_id:
        try:
            details = await pipedrive_service.get_organization_details(int(org.pipedrive_id))
            persons = details.get("persons", [])
            for p in persons:
                if p.get("email"):
                    for e in p["email"]:
                        if e.get("label") == "verified":
                            verified_pipedrive_ids.add(str(p.get("id")))
                            break
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Erro ao buscar detalhes do Pipedrive: {e}")

    for emp in employees:
        if emp.pipedrive_id and str(emp.pipedrive_id) in verified_pipedrive_ids:
            import logging
            logging.getLogger(__name__).info(f"Pulando {emp.name}: E-mail já validado no Pipedrive.")
            continue
            
        await asyncio.sleep(2)  # Delay para evitar rate limit
        res = await exec_discover_and_validate_email({
            "contact_name": emp.name,
            "domain": org.domain,
            "job_title": emp.role or emp.department or "",
            "person_id": emp.id,
            "org_id": org.id,
        })
        
        # Se for inválido, remover do Pipedrive!
        if not res.get("ok"):
            if emp.pipedrive_id:
                try:
                    await pipedrive_service.delete_person(int(emp.pipedrive_id))
                    # Atualiza BD local
                    async with async_session() as s2:
                        e = (await s2.execute(select(Employee).where(Employee.id == emp.id))).scalars().first()
                        if e:
                            e.pipedrive_id = None
                            await s2.commit()
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Falha ao deletar fantasma do Pipedrive: {e}")

