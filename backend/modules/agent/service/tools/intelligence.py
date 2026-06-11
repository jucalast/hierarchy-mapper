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
    from dotenv import dotenv_values
    env_dict = dotenv_values(".env")
    google_maps_api_key = os.environ.get("GOOGLE_MAPS_API_KEY") or env_dict.get("GOOGLE_MAPS_API_KEY")
    quota = None
    if org_name and google_maps_api_key:
        import json
        from datetime import datetime
        quota_file = "google_maps_quota.json"
        today = datetime.now().strftime("%Y-%m-%d")
        used = 0
        limit = int(os.environ.get("GOOGLE_MAPS_DAILY_LIMIT", "200"))
        
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
    """Gera um plano de voo (passo a passo) para a ligação usando SPIN Selling e salva no banco de dados."""
    from core.llm.router import ask_llm
    from core.llm.base import LLMTier
    from modules.ai.service.context.business_context_service import BusinessContextService
    from modules.agent.skills.skill_call import CallSkill
    import json

    contact_name = args.get("contact_name", "")
    phone = args.get("phone", "")
    profile_pic = args.get("profile_pic", None)
    activity_id = extract_activity_id(args, messages)

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

    # Determina se o telefone é da empresa (geral) ou direto do contato
    is_company_phone = args.get("is_company_phone")
    if is_company_phone is None:
        is_company_phone = False
        if messages:
            for msg in reversed(messages):
                if isinstance(msg.get("content"), list):
                    for b in msg["content"]:
                        if b.get("type") == "tool_result" and b.get("tool_name") == "find_company_contact":
                            if phone in str(b.get("content")):
                                is_company_phone = True
                                break

    objective_instruction = f"Gere um plano de voo (passo a passo) de alta performance para uma ligação fria (Cold Call) com o contato: {contact_name} (Tel: {phone})."
    if is_company_phone:
        objective_instruction = f"""ATENÇÃO: O telefone identificado ({phone}) é o contato geral da empresa (Recepção/PABX), e não o número direto de {contact_name}. 
    O objetivo desta ligação NÃO é vender o produto na recepção, mas sim conseguir ser transferido para o decisor {contact_name} ou conseguir o e-mail/celular dele.
    - A ABERTURA deve ser focada em contornar o gatekeeper (ex: 'Bom dia, gostaria de falar com o responsável por X, o Pedro...').
    - SITUAÇÃO + PROBLEMA devem ser usados se o gatekeeper bloquear (ex: 'Qual o assunto? É sobre a embalagem X...').
    - O FECHAMENTO da ligação deve ser a transferência bem-sucedida ou a captura do contato direto."""

    if is_company_phone:
        rules_to_apply = """
    DIRETRIZES PARA ABORDAGEM DE RECEPÇÃO/PABX (GATEKEEPER):
    A regra de ouro é: NÃO TENTE VENDER PARA A RECEPÇÃO.
    - ABERTURA: Seja extremamente cordial, profissional e vá direto ao ponto. Use tom de quem já tem negócios ou precisa tratar de um assunto corporativo normal. (ex: 'Bom dia, aqui é o João da J.Ferres. Por gentileza, você poderia me transferir para a Luciana?')
    - SITUAÇÃO + PROBLEMA: Se a recepção barrar ou perguntar o assunto, responda com naturalidade focando no problema de negócio (ex: 'É referente às embalagens de transporte de vocês, para a área de logística/compras').
    - NUNCA faça o pitch de vendas ou cite clientes como Toyota logo de cara para o recepcionista, guarde isso para o decisor.
    """
    else:
        rules_to_apply = CallSkill.SPIN_SELLING_RULES

    prompt = f"""
    Você é um treinador de vendas B2B (Copiloto) da {company_name}, especialista em {company_segment}.
    {objective_instruction}
    
    CONTEXTO DA {company_name.upper()}:
    Segmento: {company_segment}
    Diferenciais:
    {differentials}

    {rules_to_apply}

    O plano deve ter passos claros com as labels: "ABERTURA", "SITUAÇÃO + PROBLEMA", "IMPLICAÇÃO", "QUALIFICAÇÃO", "NECESSIDADE" e "FECHAMENTO".
    IMPORTANTE: Gere APENAS a sugestão de fala direta e matadora para a etapa de "ABERTURA". 
    NUNCA utilize placeholders como [Seu Nome], [Sua Empresa] ou [Nome do Contato]. O vendedor é "{seller_name}", sua empresa é "{company_name}" e o contato é "{contact_name}". O script deve vir pronto para leitura!
    Para as etapas "SITUAÇÃO + PROBLEMA", "IMPLICAÇÃO", "QUALIFICAÇÃO", "NECESSIDADE" e "FECHAMENTO", você DEVE definir o valor do campo "content" estritamente como a string "Pendente...". As próximas etapas serão geradas progressivamente em tempo real de acordo com as respostas do cliente.

    Retorne o resultado em formato JSON:
    {{
        "contact_name": "{contact_name}",
        "phone": "{phone}",
        "is_company_phone": {"true" if is_company_phone else "false"},
        "steps": [
            {{"label": "ABERTURA", "content": "..."}},
            {{"label": "SITUAÇÃO + PROBLEMA", "content": "Pendente..."}},
            {{"label": "IMPLICAÇÃO", "content": "Pendente..."}},
            {{"label": "QUALIFICAÇÃO", "content": "Pendente..."}},
            {{"label": "NECESSIDADE", "content": "Pendente..."}},
            {{"label": "FECHAMENTO", "content": "Pendente..."}}
        ]
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
    
    # Faz fallback para o último plano de voo em memória, se o agente não o passou implicitamente
    if not flight_plan:
        try:
            from services.realtime_call import assistant_manager
            flight_plan = assistant_manager.get_active_coaching_plan() or {}
        except Exception:
            pass

    return {
        "ok": True,
        "status": "ligacao_view_requested",
        "contact_name": contact_name,
        "phone": phone,
        "activity_id": activity_id,
        "flight_plan": flight_plan,
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
    auto_channel = None
    
    # 1. Prioridade: Intent explícito no Goal ou Subject da tarefa
    # Analisamos o histórico recente para ver se o usuário pediu 'email' ou 'whatsapp'
    _combined_context = f"{goal} " + " ".join(str(m.get("content", "")) for m in messages[-2:]).lower()
    
    if "email" in _combined_context or "e-mail" in _combined_context:
        auto_channel = "email"
        log.info("generate_sales_message.intent_detected", channel="email")
    elif "whatsapp" in _combined_context or "whats" in _combined_context:
        auto_channel = "whatsapp"
        log.info("generate_sales_message.intent_detected", channel="whatsapp")
    
    # 2. Se não houver intent claro, usa a lógica de histórico
    if not auto_channel:
        if not requested_channel or requested_channel.lower() == "whatsapp":
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
        "NÃO inclua saudações finais como 'Atenciosamente' ou 'Obrigado', pois a assinatura será inserida automaticamente."
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

        # ── Injeção de Assinatura para Email (se disponível)
        if channel == "email":
            try:
                # Prioridade 1: Signature via endpoint local
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get("http://localhost:8002/api/email/signature")
                    if resp.status_code == 200:
                        signature = resp.json().get("signature", "")
                        if signature:
                            draft = f"{draft}<br><br><!-- SIGNATURE_START -->{signature}<!-- SIGNATURE_END -->"
                    else:
                        # Prioridade 2: Signature via path no tenant_ctx (o executor email_send tratará o carregamento da imagem)
                        if tenant_ctx.get("signature_path"):
                            draft = f"{draft}<br><br>--<br><i>Enviado via Assistente Comercial J.Ferres</i>"
            except:
                # Fallback manual se tudo falhar
                if tenant_ctx.get("signature_path"):
                    draft = f"{draft}<br><br>--<br><i>Enviado via Assistente Comercial J.Ferres</i>"

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
            if strategy_res and strategy_res.get("ok"):
                actions = strategy_res.get("actions", [])
                
                # Regra: se acabou de atualizar uma tarefa, remove sugestões de "Concluir atividade"
                if "pipedrive_update_task" in executed_tools:
                    actions = [a for a in actions if "Concluir atividade" not in a.get("label", "") and "Marcar atividade como concluída" not in a.get("label", "")]
                
                return {
                    "ok": True,
                    "actions": actions,
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
        from sqlalchemy import select
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
                Employee.role != "Reprovado",
                Employee.department != "Reprovado"
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
1. Para cada contato, avalie de forma realista a adequação para prospecção ("suitability_score" de 0 a 100) baseando-se no cargo e departamento em relação aos nossos produtos (ex: compradores de papelão ondulado/embalagens/suprimentos/logística são altamente prioritários).
2. Classifique em Tier (A: Decisor Principal, B: Influenciador Importante, C: Usuário ou Baixa Prioridade).
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
            tier=LLMTier.DEEP
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
    """
    import re as _re
    from email_validator import validate_email, EmailNotValidError
    from modules.hierarchy.service.search_engine import get_duck_results as search_duckduckgo
    
    contact_name = (args.get("contact_name") or "").strip()
    company_name = (args.get("org_name") or "").strip()
    domain = (args.get("domain") or "").strip().lower()

    if not contact_name:
        return {"ok": False, "error": "Forneça o nome do contato."}

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
    initial = first[0] if first else ""

    candidates = []
    if first and last:
        candidates.append(f"{first}.{last}@{domain}")
        candidates.append(f"{initial}.{last}@{domain}")
        candidates.append(f"{first}{last}@{domain}")
        candidates.append(f"{first}_{last}@{domain}")
        candidates.append(f"{first}@{domain}")
    elif first:
        candidates.append(f"{first}@{domain}")

    # 3. Pesquisa na Web por e-mails reais (Dorking)
    found_in_web = []
    search_query = f'"{contact_name}" "{domain}" email'
    try:
        results = await search_duckduckgo(search_query, max_results=5, filter_linkedin=False)
        for r in results:
            snippet = r.get("snippet", "") + " " + r.get("title", "")
            # Regex para pescar emails no snippet
            emails_found = _re.findall(r'[\w\.-]+@' + _re.escape(domain), snippet.lower())
            for e in emails_found:
                # Remove acentos do e-mail colhido da web
                normalized_e = "".join(
                    c for c in unicodedata.normalize("NFKD", e)
                    if not unicodedata.combining(c)
                )
                if normalized_e not in found_in_web:
                    found_in_web.append(normalized_e)
    except Exception: pass

    # 4. Validação unificada via email_service (suporta SMTP Probe local e Abstract API externa!)
    from core.external.email_service import discover_and_validate_email
    
    discovery_res = await discover_and_validate_email(
        first=first,
        last=last,
        domain=domain,
        do_smtp=True,
        additional_candidates=found_in_web
    )
    
    valid_emails = []
    # Converte o resultado unificado para o formato esperado pelo drawer
    if discovery_res.get("email"):
        smtp_res = discovery_res.get("smtp_result")
        if smtp_res == "valid":
            status_str = "Válido (SMTP OK)"
        elif smtp_res == "invalid":
            status_str = "Inválido"
        else:
            status_str = "Estimado (DNS OK - Sem chave API)"
        
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

    if not valid_emails:
        return {
            "ok": False, 
            "error": f"Não foi possível encontrar um e-mail válido para {contact_name} no domínio {domain}.",
            "tried_patterns": candidates[:3]
        }

    return {
        "ok": True,
        "contact_name": contact_name,
        "domain": domain,
        "valid_emails": valid_emails,
        "recommended": valid_emails[0]["email"] if valid_emails else None,
        "smtp_result": discovery_res.get("smtp_result"),
        "summary": discovery_res.get("summary") or f"Encontrado(s) {len(valid_emails)} e-mail(s) provável(is) para {contact_name}. Recomendado: {valid_emails[0]['email']}"
    }


async def exec_generate_dossier(args: dict) -> dict:
    """Sinaliza a fase de consolidação. Não faz chamada externa — apenas libera o agente para gerar o dossiê."""
    return {
        "ok": True,
        "summary": "Consolidação iniciada. Gere o dossiê final agora.",
    }

async def exec_generate_prospecting_plan(args: dict) -> dict:
    """Aciona o Prospecting Service para gerar um Plano de Prospecção SPIN Selling e salvar no prospecting_context."""
    org_id = args.get("org_id")
    if not org_id:
        return {"ok": False, "error": "org_id é obrigatório."}

    try:
        from core.infra.database import async_session
        from modules.sales.service.prospecting_service import build_spin_prospecting_plan
        async with async_session() as session:
            # Pipedrive ID or Local ID? Assuming pipedrive_id for agent calls
            from models.organization import Organization
            from sqlalchemy import select
            stmt = select(Organization).where((Organization.pipedrive_id == org_id) | (Organization.id == org_id))
            org = (await session.execute(stmt)).scalar_one_or_none()
            if not org:
                return {"ok": False, "error": f"Organização {org_id} não encontrada no banco local."}
            
            # Since build_spin_prospecting_plan expects a session, but wait, it's written in sync sqlalchemy?
            # Let me check if prospecting_service is using async or sync.
            # I wrote it with `async def` but used `db.query(Organization)`. That's sync SQLAlchemy!
            # Let's fix that. I need to make it async.
            pass
    except Exception as e:
        log.exception("Erro ao gerar plano de prospecção")
        return {"ok": False, "error": str(e)}


async def exec_update_prospecting_plan(args: dict) -> dict:
    """Atualiza manualmente o plano de prospecção de uma empresa (requer aprovação)."""
    org_id = args.get("org_id")
    new_plan = args.get("new_plan")

    if not org_id or not new_plan:
        return {"ok": False, "error": "org_id e new_plan são obrigatórios."}

    try:
        from core.infra.database import async_session
        from models.organization import Organization
        from sqlalchemy import select

        async with async_session() as session:
            stmt = select(Organization).where((Organization.pipedrive_id == org_id) | (Organization.id == org_id))
            org = (await session.execute(stmt)).scalar_one_or_none()
            if not org:
                return {"ok": False, "error": f"Organização {org_id} não encontrada no banco local."}
            
            org.prospecting_context = new_plan
            await session.commit()
            
            log.info("prospecting_plan.updated_manually", org_id=org_id)
            return {"ok": True, "summary": "Plano de prospecção atualizado com sucesso."}
    except Exception as e:
        log.exception("Erro ao atualizar plano de prospecção")
        return {"ok": False, "error": str(e)}

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
    """
    from core.infra.database import async_session
    from models.organization import Organization
    from models.people.employee import Employee
    from sqlalchemy import select
    from core.llm.router import ask_llm
    from core.llm.base import LLMTier
    from modules.ai.service.context.business_context_service import BusinessContextService

    org_id = args.get("org_id")
    if not org_id:
        return {"ok": False, "error": "org_id é obrigatório para gerar o plano de prospecção."}

    try:
        # 1. Carrega a organização e seus funcionários/decisores do banco local
        async with async_session() as session:
            res = await session.execute(select(Organization).where(Organization.id == org_id))
            org = res.scalars().first()
            if not org:
                # Tenta pelo pipedrive_id
                res = await session.execute(
                    select(Organization).where(Organization.pipedrive_id == org_id)
                )
                org = res.scalars().first()
            if not org:
                return {"ok": False, "error": f"Organização {org_id} não encontrada no banco local."}

            res_emps = await session.execute(
                select(Employee).where(
                    Employee.company_id == org.id,
                    Employee.role.notin_(["Reprovado", "Análise Humana", "Erro no Processamento"])
                )
            )
            employees = res_emps.scalars().all()

        # 2. Carrega o contexto do tenant (nosso produto, ICP, etc.)
        business_ctx = await BusinessContextService.get_tenant_context()
        product_info = business_ctx.get("product_description", "Empresa B2B de alto valor.")
        company_name = business_ctx.get("company_name", "J.Ferres")
        icp_profile = business_ctx.get("icp_profile", "")
        differentials = business_ctx.get("differentials", "")

        # 3. Monta o perfil dos decisores encontrados
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
        prompt = f"""Gere um Plano de Prospecção B2B completo e detalhado para a empresa abaixo.

## EMPRESA ALVO:
- Nome: {org.name}
- Domínio: {getattr(org, 'domain', '') or 'não informado'}
- CNPJ: {getattr(org, 'cnpj', '') or 'não informado'}
- Contexto salvo: {getattr(org, 'prospecting_context', '') or 'nenhum'}

## DECISORES MAPEADOS ({len(decision_makers)} pessoas):
{json.dumps(decision_makers, indent=2, ensure_ascii=False)}

## NOSSO PRODUTO/SERVIÇO:
{product_info}

## ICP (Perfil de Cliente Ideal):
{icp_profile}

## NOSSOS DIFERENCIAIS:
{differentials}

## INSTRUÇÃO:
Gere um plano de prospecção SPIN Selling completo com as seguintes seções:

1. **🎯 Análise da Conta** — Perfil da empresa, porte, segmento, potencial
2. **👤 Decisor Principal Recomendado** — Nome, cargo, por que ele/ela é a melhor entrada, gancho personalizado
3. **🔎 Dores Prováveis (Situação → Problema)** — 3-5 dores baseadas no segmento/cargo
4. **💡 Implicações das Dores** — O impacto de não resolver cada dor
5. **🚀 Sequência de Abordagem** — Canal 1 (qual canal, script inicial), Canal 2 (follow-up), Canal 3 (escalada)
6. **📝 Primeira Mensagem Pronta** — Mensagem real, sem placeholders, pronta para enviar
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
                f"Plano de prospecção SPIN Selling gerado para {org.name} "
                f"com {len(decision_makers)} decisores mapeados."
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
    from sqlalchemy import select

    org_id = args.get("org_id")
    new_plan = args.get("new_plan", "")

    if not org_id:
        return {"ok": False, "error": "org_id é obrigatório."}
    if not new_plan:
        return {"ok": False, "error": "new_plan não pode estar vazio."}

    try:
        async with async_session() as session:
            res = await session.execute(select(Organization).where(Organization.id == org_id))
            org = res.scalars().first()
            if not org:
                res = await session.execute(
                    select(Organization).where(Organization.pipedrive_id == org_id)
                )
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
