"""
Ferramentas de comunicação (WhatsApp + Email) do Agente V2.
"""
from __future__ import annotations

import asyncio
import httpx
from typing import Any, Dict
from core.observability.logging_config import get_logger
from ._constants import WA_BASE, EMAIL_SERVICE_BASE, JFERRES_DOMAIN
from ._utils import (
    _chat_id_str,
    _resolve_wa_chat,
    _pipedrive_find_org,
    _pipedrive_phone_for_contact,
    _pipedrive_email_for_contact,
    _extract_org_domain,
    _log_activity_bg,
)
from ._message_cache import cache_wa_messages, cache_email_messages

log = get_logger(__name__)


async def exec_whatsapp_get_messages(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    import re as _re
    contact = args.get("contact", "")
    # Rejeita buscas com valores inválidos que o LLM às vezes gera ao perder o contexto
    if not contact or contact.strip().lower() in ("none", "null", "undefined", "n/a", ""):
        return {"ok": False, "error": "Nome de contato inválido — forneça o nome real da pessoa ou empresa."}
    limit = int(args.get("limit", 60))
    async with httpx.AsyncClient() as client:
        try:
            st = await client.get(f"{WA_BASE}/status", timeout=5.0)
            st_data = st.json() if st.status_code == 200 else {}
            if not (st_data.get("isReady") or st_data.get("authenticated")):
                return {"ok": False, "error": "WhatsApp desconectado"}
        except Exception:
            return {"ok": False, "error": "WhatsApp inacessível"}

        # Se o phone for um LID (>13 dígitos), tenta buscar mensagens diretamente via
        # {LID}@lid — as conversas com contatos LID ficam sob esse ID, não sob o número.
        phone_arg = args.get("phone") or ""
        phone_digits_arg = _re.sub(r'\D', '', phone_arg) if phone_arg else ""
        if phone_digits_arg and len(phone_digits_arg) > 13:
            lid_chat_id = f"{phone_digits_arg}@lid"

            # Verifica cache ANTES de chamar o WA service — poupa round-trip externo
            from ._message_cache import get_cached_messages
            from models.communication.contact_cache import CHANNEL_WHATSAPP
            cached_lid = await get_cached_messages(lid_chat_id, CHANNEL_WHATSAPP)
            if cached_lid is not None:
                fmt_cached = []
                for m in cached_lid:
                    body = m.get("body") or m.get("text") or m.get("content") or ""
                    sender = "Você" if m.get("fromMe") else contact
                    fmt_cached.append(f"[{sender}]: {body[:300]}")
                return {
                    "ok": True,
                    "contact": contact,
                    "phone": "",
                    "messages": fmt_cached,
                    "count": len(fmt_cached),
                    "summary": (
                        f"{len(fmt_cached)} mensagens com {contact} (recuperadas do cache local)"
                        " — ATENÇÃO: este contato usa ID interno do WhatsApp;"
                        " para enviar mensagens use o telefone cadastrado no Pipedrive"
                    ),
                }

            try:
                r_lid = await client.get(
                    f"{WA_BASE}/chats/{lid_chat_id}/messages",
                    params={"limit": limit},
                    timeout=10.0,
                )
                if r_lid.status_code == 200:
                    msgs_lid = r_lid.json()
                    if isinstance(msgs_lid, dict):
                        msgs_lid = msgs_lid.get("messages") or msgs_lid.get("data") or []
                    if msgs_lid:
                        fmt = []
                        for m in msgs_lid:
                            body = m.get("body") or m.get("text") or m.get("content") or ""
                            if not body or (len(body) > 100 and " " not in body):
                                continue
                            sender = "Você" if m.get("fromMe") else contact
                            fmt.append(f"[{sender}]: {body[:300]}")
                        # Persiste o histórico LID no cache (usa chat_id como identifier).
                        # Aguarda o commit (em vez de create_task fire-and-forget) para garantir
                        # que generate_prospecting_plan, ao ler o cache logo depois, já o encontre.
                        await cache_wa_messages(
                            contact_identifier=lid_chat_id,
                            contact_name=contact,
                            org_id=org_id,
                            org_name=args.get("org_name") or None,
                            chat_id=lid_chat_id,
                            raw_messages=list(msgs_lid),
                        )
                        return {
                            "ok": True,
                            "contact": contact,
                            "phone": "",  # LID — não expor ao LLM
                            "messages": fmt,
                            "count": len(fmt),
                            "summary": (
                                f"{len(fmt)} mensagens com {contact}"
                                " — ATENÇÃO: este contato usa ID interno do WhatsApp;"
                                " para enviar mensagens use o telefone cadastrado no Pipedrive"
                            ),
                        }
            except Exception:
                pass
            # LID não retornou mensagens — tenta pelo número real do Pipedrive via _resolve
            phone_arg = ""

        # Sempre busca o número real no Pipedrive quando possível — ignora o que o LLM passou
        # para evitar contaminação de contexto de sessões anteriores (ex: Gabriel/Walsywa).
        org_name_arg = args.get("org_name", "")
        if contact and org_name_arg:
            try:
                _verified_phone = await _pipedrive_phone_for_contact(contact, org_name_arg)
                if _verified_phone:
                    phone_digits_arg = _verified_phone
            except Exception:
                pass

        if phone_digits_arg and len(phone_digits_arg) <= 13:
            if len(phone_digits_arg) in (10, 11) and not phone_digits_arg.startswith("55"):
                phone_digits_arg = f"55{phone_digits_arg}"
            pd_chat_id = f"{phone_digits_arg}@c.us"
            found_name = contact
        else:
            pd_chat_id = None

        if pd_chat_id:
            chat_id = pd_chat_id
        else:
            chat_id, found_name = await _resolve_wa_chat(
                client,
                contact,
                phone_arg,
                org_name=args.get("org_name", "")
            )
            if not chat_id:
                return {"ok": False, "error": f"Contato '{contact}' não encontrado no WhatsApp"}

        # ─── Cache check ───
        # Verifica se já temos as mensagens no cache local e se não estão expiradas (stale)
        phone_val = chat_id.split("@")[0] if "@" in chat_id else chat_id
        is_lid = "@lid" in chat_id or (phone_val.isdigit() and len(phone_val) > 13)
        pipedrive_phone = _re.sub(r'\D', '', phone_arg) if phone_arg else ""
        canonical_phone = pipedrive_phone if (pipedrive_phone and len(pipedrive_phone) <= 13) else ("" if is_lid else phone_val)
        # Normaliza DDI: números brasileiros sempre com 55 (evita cache miss por formato diferente)
        if canonical_phone and canonical_phone.isdigit() and not canonical_phone.startswith("55") and len(canonical_phone) in (10, 11):
            canonical_phone = f"55{canonical_phone}"
        _cache_id = canonical_phone or chat_id


        from ._message_cache import get_cached_messages
        from models.communication.contact_cache import CHANNEL_WHATSAPP
        cached_msgs = await get_cached_messages(_cache_id, CHANNEL_WHATSAPP)
        if cached_msgs is not None:
            formatted = []
            for m in cached_msgs:
                body = m.get("body") or m.get("text") or m.get("content") or ""
                sender = "Você" if m.get("fromMe") else (found_name or contact)
                formatted.append(f"[{sender}]: {body[:300]}")
            return {
                "ok": True,
                "contact": found_name or contact,
                "phone": canonical_phone,
                "messages": formatted,
                "count": len(formatted),
                "summary": f"{len(formatted)} mensagens com {found_name or contact} (recuperadas do cache local)"
                           + (" — ATENÇÃO: este contato usa ID interno do WhatsApp; para enviar mensagens use o telefone cadastrado no Pipedrive" if is_lid else ""),
            }

        r = await client.get(f"{WA_BASE}/chats/{chat_id}/messages", params={"limit": limit}, timeout=10.0)
        if r.status_code != 200:
            # HTTP 500 por "No LID for user": contato usa LID interno do WhatsApp.
            # Tenta resolver por nome via _resolve_wa_chat antes de desistir.
            if r.status_code == 500 and chat_id == pd_chat_id:
                try:
                    chat_id_lid, found_name_lid = await _resolve_wa_chat(
                        client, contact, "", org_name=args.get("org_name", "")
                    )
                    if chat_id_lid:
                        r2 = await client.get(
                            f"{WA_BASE}/chats/{chat_id_lid}/messages",
                            params={"limit": limit}, timeout=10.0
                        )
                        if r2.status_code == 200:
                            r = r2
                            chat_id = chat_id_lid
                            found_name = found_name_lid
                        else:
                            return {"ok": False, "error": f"Contato '{contact}' encontrado mas sem conversa ativa no WhatsApp"}
                    else:
                        return {"ok": False, "error": f"Contato '{contact}' não possui conversa ativa no WhatsApp (sem LID)"}
                except Exception:
                    return {"ok": False, "error": f"Contato '{contact}' não encontrado no WhatsApp (sem LID)"}
            else:
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

        # O campo phone sempre usa o número do Pipedrive (args["phone"]), nunca o chat_id
        # retornado pelo bridge — o bridge pode ter dados inconsistentes.
        phone_val = chat_id.split("@")[0] if "@" in chat_id else chat_id
        is_lid = "@lid" in chat_id or (phone_val.isdigit() and len(phone_val) > 13)
        # Número canônico: preferência ao Pipedrive, fallback ao chat_id se não for LID
        pipedrive_phone = _re.sub(r'\D', '', phone_arg) if phone_arg else ""
        canonical_phone = pipedrive_phone if (pipedrive_phone and len(pipedrive_phone) <= 13) else ("" if is_lid else phone_val)

        # Normaliza DDI brasileiro: garante que o número sempre começa com 55
        # Evita duplicatas no cache por números "19..." vs "5519..." referentes ao mesmo contato
        if canonical_phone and canonical_phone.isdigit() and not canonical_phone.startswith("55") and len(canonical_phone) in (10, 11):
            canonical_phone = f"55{canonical_phone}"

        # Persiste no cache para a UI de mensagens e para generate_prospecting_plan.
        # Aguarda o commit (em vez de create_task fire-and-forget) para evitar que o plano
        # de prospecção seja gerado antes do histórico recém-buscado estar salvo no banco.
        _cache_id = canonical_phone or chat_id
        _org_name = args.get("org_name") or None
        await cache_wa_messages(
            contact_identifier=_cache_id,
            contact_name=found_name or contact,
            org_id=org_id,
            org_name=_org_name,
            chat_id=chat_id,
            raw_messages=list(msgs_raw or []),
        )


        return {
            "ok": True,
            "contact": found_name or contact,
            "phone": canonical_phone,
            "messages": formatted,
            "count": len(formatted),
            "summary": f"{len(formatted)} mensagens com {found_name or contact}"
                       + (" — ATENÇÃO: este contato usa ID interno do WhatsApp; para enviar mensagens use o telefone cadastrado no Pipedrive" if is_lid else ""),
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


async def exec_whatsapp_send_message(args: dict, messages: list | None = None, org_id: int | None = None, attachment_path: str | None = None) -> dict:
    """Envia uma mensagem de WhatsApp para um contato resolvido por nome, telefone ou empresa."""
    import re as _re
    from modules.communication.service.whatsapp.integration import WhatsAppIntegration

    contact = args.get("contact")
    phone = args.get("phone") or ""
    org_name = args.get("org_name")
    message = args.get("message")

    if not message:
        return {"ok": False, "error": "Mensagem vazia."}
    if not contact:
        return {"ok": False, "error": "Falta o parâmetro obrigatório 'contact' para envio de WhatsApp."}

    # O número do Pipedrive é a fonte de verdade — usa diretamente quando disponível.
    phone_digits = _re.sub(r'\D', '', phone)

    # Se for LID (>13 dígitos), tenta buscar o número real no Pipedrive
    if phone_digits and len(phone_digits) > 13 and org_name:
        pd_phone = await _pipedrive_phone_for_contact(contact, org_name)
        if pd_phone:
            log.info(f"wa_send.lid_replaced phone_orig={phone_digits} pipedrive={pd_phone}")
            phone_digits = pd_phone
        else:
            phone_digits = ""

    # Resolve o Chat ID: se temos número real do Pipedrive, usa direto sem resolução por nome
    chat_id = None
    resolved_name = contact

    if contact and "@" in contact:
        chat_id = contact
        resolved_name = contact
    elif phone_digits and len(phone_digits) <= 13:
        # Número real do Pipedrive → chat_id direto, sem busca por nome
        chat_id = f"{phone_digits}@c.us"
        resolved_name = contact
    else:
        async with httpx.AsyncClient(timeout=15.0) as client:
            chat_id, resolved_name = await _resolve_wa_chat(client, contact, phone=phone, org_name=org_name)

    if not chat_id:
        # Tenta uma última vez buscando no histórico da própria conversa se o agente já achou o ID
        if messages:
            import re
            for msg in reversed(messages):
                content = str(msg.get("content", ""))
                # Captura IDs: @c.us, @lid ou numérico puro entre parênteses vindo do whatsapp_get_messages
                # Formatos: 'chat_id': '123...', (123@c.us), (1234567890)
                # Evita capturar apenas telefones listados no Pipedrive (que podem não ter DDI)
                match = (
                    re.search(r"chat_id':\s*'([^']+)'", content) or
                    re.search(r"\(([^)]+@(?:c\.us|lid))\)", content) or
                    re.search(r"ID:\s*([^)\s]+@(?:c\.us|lid))\)", content)
                )
                if match:
                    chat_id = match.group(1)
                    log.info("wa_send_message.recovered_id_from_history", chat_id=chat_id)
                    break

    if not chat_id:
        return {"ok": False, "error": f"Contato '{contact}' não encontrado (mesmo com telefone/empresa se fornecidos)."}

    # Executa o envio via integração centralizada
    res = await WhatsAppIntegration.send_message(chat_id, message, attachment_path=attachment_path)
    if res.get("ok"):
        return {"ok": True, "result": f"Mensagem enviada com sucesso para {resolved_name or contact} (ID: {chat_id})"}

    # Se falhou e o chat_id parece ser um ID interno (LID-like), tenta via lookup de contato
    # para obter o número de telefone real registrado no WhatsApp.
    cid_num = chat_id.split("@")[0] if "@" in chat_id else chat_id
    if cid_num.isdigit() and len(cid_num) > 13:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                c_resp = await client.get(
                    f"{WA_BASE}/contacts/search",
                    params={"name": resolved_name or contact, "minSimilarity": 0.8},
                    timeout=5.0
                )
                if c_resp.status_code == 200:
                    c_list = c_resp.json()
                    c_list = c_list if isinstance(c_list, list) else (c_list.get("contacts") or [])
                    for c in c_list:
                        real_num = c.get("number") or ""
                        if real_num.isdigit() and len(real_num) <= 15:
                            fallback_jid = f"{real_num}@c.us"
                            res2 = await WhatsAppIntegration.send_message(fallback_jid, message, attachment_path=attachment_path)
                            if res2.get("ok"):
                                log.info(f"wa_send.lid_fallback_success chat_id={chat_id} fallback={fallback_jid}")
                                return {"ok": True, "result": f"Mensagem enviada com sucesso para {resolved_name or contact} (via número real: {fallback_jid})"}
        except Exception as e:
            log.warning(f"wa_send.lid_fallback_error: {e}")

    # Fallback Pipedrive: quando phone é LID E temos org_name, tenta o número real do Pipedrive
    if org_name and contact:
        try:
            import re as _re
            from modules.crm.service.pipedrive_service import pipedrive_service
            _, pd_org_id = await _pipedrive_find_org(org_name)
            if pd_org_id:
                details = await pipedrive_service.get_organization_details(pd_org_id)
                persons = details.get("persons", []) if isinstance(details, dict) else []
                contact_lower = contact.lower()
                for p in persons:
                    pname = (p.get("name") or "").lower()
                    if contact_lower in pname or pname in contact_lower:
                        phone_list = p.get("phone", [])
                        pd_phone = next(
                            (x.get("value") for x in phone_list if x.get("value")),
                            None
                        ) if isinstance(phone_list, list) else None
                        if pd_phone:
                            pd_digits = _re.sub(r'\D', '', pd_phone)
                            if pd_digits:
                                if not pd_digits.startswith("55"):
                                    pd_digits = f"55{pd_digits}"
                                pd_jid = f"{pd_digits}@c.us"
                                res_pd = await WhatsAppIntegration.send_message(pd_jid, message, attachment_path=attachment_path)
                                if res_pd.get("ok"):
                                    log.info(f"wa_send.pipedrive_fallback_success jid={pd_jid}")
                                    return {"ok": True, "result": f"Mensagem enviada para {contact} via telefone do Pipedrive ({pd_jid})"}
        except Exception as _e:
            log.warning(f"wa_send.pipedrive_fallback_error: {_e}")

    return {"ok": False, "error": f"Erro ao enviar mensagem para {chat_id}: {res.get('error')}"}


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
                    }
                    for m in messages[:limit]
                ]
                return {"ok": True, "emails": results, "count": len(results), "summary": f"{len(results)} e-mails encontrados"}
        except httpx.TimeoutException as e:
            if attempt < max_retries:
                await asyncio.sleep(1)
                continue
            return {"ok": False, "error": f"Timeout ao acessar serviço de e-mail (tentativa {attempt}/{max_retries}): {e}"}
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(1)
                continue
            return {"ok": False, "error": f"Erro ao acessar e-mail (tentativa {attempt}/{max_retries}): {e}"}


async def exec_email_get_contact_history(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    log.info("exec_email_get_contact_history", tool_args=args, org_id=org_id)
    from modules.ai.service.context.business_context_service import BusinessContextService
    ctx = await BusinessContextService.get_tenant_context()
    seller_email = ctx.get("seller_email", "")
    seller_domain = seller_email.split("@")[1].lower() if "@" in seller_email else JFERRES_DOMAIN

    contact_name = (args.get("contact_name") or "").lower()
    contact_email = (args.get("contact_email") or "").lower()
    org_name = (args.get("org_name") or "").strip()
    # Rejeita buscas com valores inválidos gerados pelo LLM ao perder contexto
    invalid = {"none", "null", "undefined", "n/a"}
    if contact_name.strip() in invalid:
        contact_name = ""
    if contact_email.strip() in invalid:
        contact_email = ""
    if not contact_name and not contact_email and not org_name:
        return {"ok": False, "error": "Nenhum parâmetro válido — forneça contact_name, contact_email ou org_name."}
    explicit_domain = (args.get("domain") or "").strip().lower().replace("www.", "").replace("http://", "").replace("https://", "")
    limit = int(args.get("limit", 25))
    term = contact_name or contact_email or explicit_domain
    if not term and not org_name and not org_id:
        return {"ok": False, "error": "Informe contact_name, contact_email, domain, org_name ou org_id"}

    max_retries = 1

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

            # OTIMIZAÇÃO: Se temos o nome mas não o email, tentamos resolver o email no Pipedrive antes da busca.
            # Isso evita falhas de substring no Outlook (ex: "Matheus Muniz" vs "matheus.muniz@...")
            if contact_name and not contact_email and (org_name or org_id):
                try:
                    pd_email = await _pipedrive_email_for_contact(contact_name, org_name or "", org_id=org_id)
                    if pd_email:
                        log.info("email_search.contact_email_resolved", contact=contact_name, email=pd_email)
                        contact_email = pd_email
                except Exception:
                    pass

            search_query = contact_email or contact_name
            if not search_query:
                if domain and domain != JFERRES_DOMAIN:
                    search_query = domain
                else:
                    import unicodedata
                    import re
                    clean_org = ''.join(c for c in unicodedata.normalize('NFD', org_name) if unicodedata.category(c) != 'Mn').lower()
                    words = re.findall(r'\b\w+\b', clean_org)
                    stopwords = {"grupo", "cia", "ltda", "sistemas", "comercio", "industria", "servicos", "brasil", "do", "de", "da"}
                    # Exige ≥ 5 chars para evitar termos genéricos como "flex", "top", "plus"
                    specific_word = next((w for w in words if len(w) >= 5 and w not in stopwords), None)
                    if not specific_word:
                        return {"ok": False, "error": f"Nome '{org_name}' muito genérico para busca segura de e-mails. Sem e-mails encontrados."}
                    search_query = specific_word

            if not search_query:
                return {"ok": False, "error": "Não foi possível determinar um termo de busca válido"}

            # ─── Cache check ───
            # Prioriza o banco de dados (cache): se temos dados, usamos eles imediatamente
            # para evitar chamadas lentas ao Outlook. O TriggerService garante que o banco esteja ok.
            _email_id = contact_email or search_query
            if _email_id:
                from ._message_cache import get_cached_messages
                from models.communication.contact_cache import CHANNEL_EMAIL
                # max_age_minutes=None -> Ignora TTL e confia no que está no banco
                cached_emails = await get_cached_messages(_email_id, CHANNEL_EMAIL, max_age_minutes=None)
                if cached_emails:
                    log.info("email_search.cache_hit_priority", contact=_email_id, count=len(cached_emails))
                    return {
                        "ok": True,
                        "contact": contact_name or contact_email or org_name,
                        "domain": domain,
                        "emails": cached_emails,
                        "count": len(cached_emails),
                        "summary": f"{len(cached_emails)} e-mails encontrados para {contact_name or contact_email or org_name} (recuperados do banco de dados local)",
                    }

            # Calcula fallback por primeira palavra do org_name (usado se busca por domínio retornar 0)
            _fallback_query = None
            if org_name and search_query.startswith("@"):
                import unicodedata as _uc_fb
                import re as _re_fb
                _clean = "".join(c for c in _uc_fb.normalize("NFD", org_name) if _uc_fb.category(c) != "Mn").lower()
                _words = _re_fb.findall(r"\b\w+\b", _clean)
                _sw = {"grupo", "cia", "ltda", "sistemas", "comercio", "industria", "servicos", "energia", "eletrica"}
                _fallback_query = next((w for w in _words if len(w) > 3 and w not in _sw), _words[0] if _words else None)

            async with httpx.AsyncClient(timeout=60.0) as client:
                # "conversations" varre TODAS as pastas do Outlook recursivamente
                all_r = await client.get(f"{EMAIL_SERVICE_BASE}/messages", params={"folder": "conversations", "limit": limit * 2, "q": search_query})

                # 503 = email service ainda inicializando (Outlook COM não pronto).
                # Aguarda 25s e retenta uma vez — Outlook demora ~30s para inicializar.
                if all_r.status_code == 503:
                    if attempt < max_retries:
                        log.info("email_get_contact_history.outlook_not_ready_waiting",
                                 attempt=attempt, wait_sec=25)
                        await asyncio.sleep(25)
                        continue
                    label = contact_name or contact_email or org_name
                    return {
                        "ok": True,
                        "contact": label,
                        "emails": [],
                        "count": 0,
                        "summary": f"Serviço de e-mail ainda inicializando — sem histórico disponível para {label} no momento.",
                    }

                all_messages = []
                if all_r.status_code == 200:
                    all_messages.extend(all_r.json().get("messages", []))

                # Retry com primeira palavra do nome da empresa se busca não achou nada
                if not all_messages and _fallback_query and _fallback_query != search_query:
                    fb_r = await client.get(f"{EMAIL_SERVICE_BASE}/messages", params={"folder": "conversations", "limit": limit * 2, "q": _fallback_query})
                    if fb_r.status_code == 200:
                        all_messages.extend(fb_r.json().get("messages", []))
                    if all_messages:
                        search_query = _fallback_query

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
                                from core.infra.database import async_session
                                from models.organization import Organization
                                from models.people.employee import Employee
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

                # Fallback: se não achou por nome, tenta pelo email real do Pipedrive.
                # DEVE ficar dentro do `async with client` — client já fechado fora daqui.
                if not all_messages and contact_name and not contact_email and (org_name or org_id):
                    try:
                        _pd_email = await _pipedrive_email_for_contact(contact_name, org_name or "", org_id=org_id)
                        if _pd_email and _pd_email.lower() not in (search_query, contact_name):
                            _em_r = await client.get(f"{EMAIL_SERVICE_BASE}/messages", params={"folder": "conversations", "limit": limit * 2, "q": _pd_email})
                            if _em_r.status_code == 200:
                                all_messages.extend(_em_r.json().get("messages", []))
                            if all_messages:
                                search_query = _pd_email
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

            label = contact_name or contact_email or org_name

            # Monta lista normalizada COM entryId para o cache (dedup exige o campo)
            def _fmt_email(m: dict) -> dict:
                return {
                    "entryId": m.get("entryId", ""),
                    "from": m.get("sender", ""),
                    "to": m.get("to", ""),
                    "subject": m.get("subject", ""),
                    "date": (m.get("date") or "")[:10],
                    "preview": (m.get("body") or "")[:200].strip(),
                    "direction": "sent" if seller_domain in (m.get("sender") or "").lower() else "received",
                }

            cache_emails = [_fmt_email(m) for m in unique_messages if m.get("entryId")]
            results = cache_emails[:10]  # LLM recebe no máximo 10

            # Persiste TODOS no banco (não só os 10 do LLM) para a UI de mensagens
            _email_id = contact_email or search_query
            # Normaliza domínio: garante formato @domain.com (ex: "dva.com" → "@dva.com")
            if _email_id and "@" not in _email_id and "." in _email_id and " " not in _email_id:
                _email_id = "@" + _email_id
            if _email_id and cache_emails:
                await cache_email_messages(
                    contact_identifier=_email_id,
                    contact_name=label,
                    org_id=org_id,
                    org_name=org_name,
                    emails=cache_emails,
                )
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
                await asyncio.sleep(1)  # Backoff rápido: 1s
                continue
            # Fallback: tentar email_get_inbox com filtro
            if contact_name:
                return await exec_email_get_inbox({"from_name": contact_name, "limit": limit})
            return {"ok": False, "error": f"Timeout ao acessar serviço de e-mail (tentativa {attempt}/{max_retries}): {e}"}
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(1)
                continue
            # Fallback: tentar email_get_inbox com filtro
            if contact_name:
                return await exec_email_get_inbox({"from_name": contact_name, "limit": limit})
            return {"ok": False, "error": f"Erro ao acessar e-mail (tentativa {attempt}/{max_retries}): {e}"}


async def exec_batch_communication_search(args: Dict[str, Any], org_id: int | None = None) -> Dict[str, Any]:
    """
    Realiza buscas em lote (WhatsApp + Email) para uma lista de contatos e para a própria empresa.
    WhatsApp: busca por contato individual (precisa de número).
    Email: busca única por domínio da empresa (cobre todos os contatos de uma vez).
    """
    contacts = args.get("contacts", [])
    org_name = args.get("org_name", "")
    limit_wa = int(args.get("limit_wa", 40))
    limit_email = int(args.get("limit_email", 25))

    if not org_name and not contacts:
        return {"ok": False, "error": "Forneça org_name ou uma lista de contacts."}

    tasks = []

    # 1. WhatsApp: busca por contato individual (requer número de telefone)
    for p in contacts[:7]:
        p_name = p.get("name")
        p_phone = p.get("phone")
        if p_name and p_phone:
            tasks.append(exec_whatsapp_get_messages({
                "contact": p_name,
                "phone": p_phone,
                "org_name": org_name,
                "limit": limit_wa
            }, org_id=org_id))

    # WhatsApp para o nome da empresa (cobre grupos e chats da empresa)
    if org_name:
        tasks.append(exec_whatsapp_get_messages({
            "contact": org_name,
            "org_name": org_name,
            "limit": limit_wa
        }, org_id=org_id))

    # 2. Email: uma única busca por domínio da empresa — cobre todos os contatos
    if org_name:
        tasks.append(exec_email_get_contact_history({
            "org_name": org_name,
            "limit": limit_email
        }, org_id=org_id))

    # Executa tudo em paralelo
    all_res = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Processa resultados bem-sucedidos
    successful_results = []
    summaries = []
    
    for r in all_res:
        if isinstance(r, Exception):
            log.warning(f"batch_search.task_failed: {r}")
            print(f"Exception in batch_search: {r}")
            continue
        if r and r.get("ok"):
            # Apenas inclui no relatório final se houver histórico real (count > 0)
            if r.get("count", 0) > 0:
                successful_results.append(r)
                summaries.append(r.get("summary", ""))
            
    if not successful_results:
        return {
            "ok": True,
            "results": [],
            "count": 0,
            "summary": f"Nenhum histórico de comunicação encontrado no WhatsApp ou Email para {org_name} e seus contatos."
        }
        
    return {
        "ok": True,
        "results": successful_results,
        "count": len(successful_results),
        "summary": "✅ Busca em lote concluída. Históricos encontrados:\n- " + "\n- ".join(summaries)
    }
