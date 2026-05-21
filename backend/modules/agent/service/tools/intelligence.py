"""
Ferramentas de inteligência (web search, IA, scripts, etc.) do Agente V2.
"""
from __future__ import annotations

import json
import httpx
from typing import Any, Dict
from core.observability.logging_config import get_logger
from ._constants import WA_BASE, EMAIL_SERVICE_BASE, JFERRES_DOMAIN
from ._utils import (
    _pipedrive_find_org,
    _pipedrive_get_org_by_id,
    _fix_llama_corrupted_name,
)

log = get_logger(__name__)


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
    """Busca contato da empresa via Receita Federal (BrasilAPI) e web search."""
    import re as _re
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

    # 1. Receita Federal via BrasilAPI / MinhReceita / ReceitaWS
    if len(cnpj_clean) == 14:
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
                address = build_full_address(data)
        except Exception:
            pass

    # 2. Web search via DuckDuckGo Instant Answer
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
        parts.append("📞 Telefones (Receita Federal): " + " | ".join(p["value"] for p in phones))
    else:
        parts.append("📞 Nenhum telefone encontrado na Receita Federal.")
    if emails:
        parts.append("📧 E-mail (Receita Federal): " + " | ".join(e["value"] for e in emails))
    else:
        parts.append("📧 Nenhum e-mail encontrado na Receita Federal.")
    if address:
        parts.append(f"📍 Endereço: {address}")
    if web_snippets:
        parts.append("🌐 Web: " + " | ".join(web_snippets[:2]))

    can_create = bool(phones or emails)
    if can_create:
        parts.append(
            "✅ Dados suficientes para criar contato no Pipedrive. "
            "Use pipedrive_create_person com os dados acima para salvar o contato."
        )
    else:
        parts.append("⚠️ Nenhum contato encontrado. Informe o usuário e finalize.")

    return {
        "ok": True,
        "phones": phones,
        "emails": emails,
        "address": address,
        "web_snippets": web_snippets,
        "can_create_contact": can_create,
        "summary": "\n".join(parts),
    }


async def exec_generate_call_script(args: dict) -> dict:
    """Sinaliza que a investigação terminou e o agente deve gerar o script de ligação."""
    import re as _re
    contact_name = args.get("contact_name", "")
    phone = args.get("phone", "")
    digits = _re.sub(r"\D", "", phone or "")
    if len(digits) < 8:
        return {
            "ok": False,
            "error": (
                "Nenhum telefone válido confirmado na investigação. "
                "PRÓXIMO PASSO: use find_company_contact (com org_name e cnpj se disponível) "
                "para buscar telefone/email da empresa via Receita Federal e web. "
                "NÃO chame open_hierarchy_drawer novamente — o mapeamento já foi feito. NÃO invente dados."
            ),
        }
    return {
        "ok": True,
        "contact_name": contact_name,
        "phone": phone,
        "summary": (
            f"Investigação concluída. Gere agora o SCRIPT DE LIGAÇÃO para {contact_name} ({phone}). "
            "Siga EXATAMENTE o formato especificado. "
            "PROIBIDO repetir contexto de investigação — escreva apenas o script."
        ),
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

    # Carrega diferenciais e contexto configurados no sistema
    business_context = await BusinessContextService.get_tenant_context()
    biz_data_str = json.dumps(business_context, indent=2, ensure_ascii=False) if business_context else "Sem contexto configurado."

    channel_tone = (
        "CANAL: WhatsApp — seja direto, natural e conversacional. Parágrafos curtos. "
        f"Comece SEMPRE com '{greeting_hint}, [Nome]'. "
        "PROIBIDO incluir assinaturas formais (ex: 'Att. João', 'Atenciosamente', etc). "
        "A mensagem deve terminar de forma natural ou com um CTA, sem assinatura de e-mail."
        if channel == "whatsapp" else
        "CANAL: Email — pode ter mais profundidade técnica. Linha de assunto impactante. Evite parágrafos longos. "
        f"Comece com '{greeting_hint}, [Nome]'. "
        "Escreva o corpo do e-mail de forma profissional. "
        "NÃO inclua saudações finais como 'Atenciosamente' ou 'Obrigado', pois a assinatura será inserida automaticamente."
    )

    system_prompt = (
        "Você é um redator comercial B2B sênior. "
        "Sua ÚNICA tarefa é escrever UMA mensagem comercial completa e pronta para envio. "
        "Não faça diagnóstico, não liste opções, não explique sua estratégia. Escreva apenas a mensagem.\n\n"
        f"## CONTEXTO DA NOSSA EMPRESA (disponível se necessário):\n{biz_data_str}\n\n"
        "## INTELIGÊNCIA DE CONTEXTO — LEIA O HISTÓRICO E DECIDA O MODO:\n\n"
        "**MODO 1 — FOLLOW-UP SIMPLES**\n"
        "Use quando: o objetivo é cobrar retorno/resposta/confirmação E o histórico não mostra objeções ativas.\n"
        "→ Mensagem curta (máx. 3-4 linhas). Referencie o que ficou pendente. Tom humano, sem pressão. CTA único.\n"
        "→ PROIBIDO: diferenciais técnicos, laboratório, certificações, TCO, pitch de vendas. "
        "Inserir argumentos de venda num follow-up simples passa despreparo e é invasivo.\n\n"
        "**MODO 2 — FOLLOW-UP COM OBJEÇÃO**\n"
        "Use quando: o objetivo é dar continuidade MAS o histórico mostra uma objeção clara e não respondida "
        "(ex: 'está caro', 'estou com outro fornecedor', 'preciso pensar', reclamação de qualidade, prazo).\n"
        "→ Mensagem moderada (4-6 linhas). Reconheça o contexto brevemente, depois endereço a objeção "
        "com UM argumento cirúrgico e baseado em dados reais do histórico. Não faça lista de diferenciais — "
        "escolha o argumento mais relevante para aquela objeção específica. Feche com CTA claro.\n\n"
        "**MODO 3 — VENDA ATIVA**\n"
        "Use quando: primeiro contato, reativação de lead frio, apresentação de proposta, "
        "rebate de concorrente direto, criação de urgência comercial.\n"
        "→ Use os diferenciais técnicos e contexto da empresa acima. CHALLENGER SALE: ensine algo que o cliente "
        "ainda não sabe. SPIN SELLING: mencione dores reais do histórico. DATA-DRIVEN: cite itens reais "
        "(códigos, preços, datas). NUNCA use placeholders.\n\n"
        "## REGRAS UNIVERSAIS:\n"
        "- ANTI-GENÉRICO: JAMAIS comece com 'Prezado', 'Espero que esteja bem', 'Tudo bem?', 'Como vai?'\n"
        "- ZERO REDUNDÂNCIA: não pergunte o que já foi respondido no histórico\n"
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
        "1. O que está pendente/em aberto\n"
        "2. Se há objeções não respondidas do cliente\n"
        "3. Qual é o momento real da negociação\n\n"
        "Depois escolha o modo correto e escreva a mensagem:\n"
        "- Sem objeções ativas → MODO 1 (follow-up simples, breve)\n"
        "- Com objeção não respondida → MODO 2 (follow-up + argumento cirúrgico)\n"
        "- Primeiro contato / venda ativa → MODO 3 (diferenciais + SPIN + dados reais)"
    )

    try:
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
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get("http://localhost:8002/api/email/signature")
                    if resp.status_code == 200:
                        signature = resp.json().get("signature", "")
                        if signature:
                            draft = f"{draft}<br><br><!-- SIGNATURE_START -->{signature}<!-- SIGNATURE_END -->"
            except:
                pass

        return {
            "ok": True,
            "contact_name": contact_name,
            "channel": channel,
            "recommended_message": draft,
            "summary": f"Estratégia e rascunho para {channel} gerados com sucesso para {contact_name}. O rascunho está disponível em 'recommended_message'."
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
    if messages:
        try:
            from modules.sales.service.strategy import sales_strategy_service
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
Nome: {org_real_name}

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
        return {
            "ok": True,
            "org_name": org_real_name,
            "best_prospects": data.get("best_prospects", []),
            "overall_strategy": data.get("overall_strategy", "Nenhuma estratégia retornada."),
            "summary": f"Análise de adequação de prospecção concluída para {org_real_name} com {len(data.get('best_prospects', []))} perfis mapeados."
        }

    except Exception as e:
        log.exception("exec_evaluate_prospects.failed")
        return {"ok": False, "error": str(e)}


async def exec_generate_dossier(args: dict) -> dict:
    """Sinaliza a fase de consolidação. Não faz chamada externa — apenas libera o agente para gerar o dossiê."""
    return {
        "ok": True,
        "summary": "Consolidação iniciada. Gere o dossiê final agora.",
    }
