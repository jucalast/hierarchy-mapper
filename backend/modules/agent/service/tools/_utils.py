"""
Helpers privados das ferramentas do Agente V2.
"""
from __future__ import annotations

import httpx
from typing import Any, Dict
from core.observability.logging_config import get_logger
from ._constants import WA_BASE, EMAIL_SERVICE_BASE, JFERRES_DOMAIN

log = get_logger(__name__)


def _chat_id_str(chat: dict) -> str:
    cid = chat.get("id", "")
    if isinstance(cid, dict):
        return cid.get("_serialized", "") or cid.get("user", "")
    return str(cid) if cid else ""


async def _resolve_wa_chat(client: httpx.AsyncClient, contact: str, phone: str = "", org_name: str = "") -> tuple[str | None, str]:
    """Retorna (chat_id, nome_encontrado). Busca pelo telefone primeiro, depois por nome mais recente com fallback em contatos."""
    import re
    phone_digits = re.sub(r'\D', '', phone) if phone else ""
    # Normaliza org_name removendo espaços E acentos para comparar com nomes colados
    # (ex: "Master Sense" → "mastersense" para bater com "mastersense" no nome do chat)
    org_clean = _remove_diacritics(org_name).replace(" ", "") if org_name else ""

    try:
        r = await client.get(f"{WA_BASE}/chats", timeout=10.0)
        if r.status_code == 200:
            body = r.json()
            all_chats = body if isinstance(body, list) else (body.get("chats") or body.get("data") or [])

            # 1. Prioridade absoluta: buscar pelo número de telefone (se fornecido)
            # IMPORTANTE: IDs internos do WhatsApp têm >13 dígitos — ignoramos para evitar
            # que o LLM passe o chat_id como telefone e cause erro 404 ao enviar.
            if phone_digits and len(phone_digits) > 13:
                print(f"[WA Resolver] phone '{phone_digits}' parece ID interno (>{13} dígitos). Ignorando e resolvendo por nome.")
                phone_digits = ""
            if phone_digits:
                # Pega os últimos 8 dígitos (corpo principal do número no Brasil)
                phone_suffix = phone_digits[-8:] if len(phone_digits) >= 8 else phone_digits
                for c in all_chats:
                    cid = _chat_id_str(c).split("@")[0]
                    # Match se os últimos 8 dígitos batem (ignora 55, DDD e o 9 extra)
                    if cid.endswith(phone_suffix):
                        return _chat_id_str(c), c.get("name", contact)

                # Se passou telefone e não achou nos chats ativos, tenta busca direta por número
                # Tenta variações (com e sem o 9 extra se for Brasil 55)
                phones_to_try = []
                if phone_digits.startswith("55") or len(phone_digits) >= 10:
                    base = phone_digits if phone_digits.startswith("55") else f"55{phone_digits}"
                    phones_to_try.append(base)
                    # Se tem 13 dígitos (55 + DDD + 9 + 8), tenta sem o 9
                    if len(base) == 13:
                        phones_to_try.append(base[:4] + base[5:])
                    # Se tem 12 dígitos (55 + DDD + 8), tenta com o 9 (adiciona 9 após DDD)
                    elif len(base) == 12:
                        phones_to_try.append(base[:4] + "9" + base[4:])
                else:
                    phones_to_try.append(phone_digits)

                for p in phones_to_try:
                    try:
                        c_resp = await client.get(f"{WA_BASE}/contacts/by-number/{p}", timeout=4.0)
                        if c_resp.status_code == 200:
                            best_contact = c_resp.json()
                            if best_contact and not best_contact.get("error"):
                                # Valida nome: rejeita se o bridge retornou um contato cujo nome
                                # não tem nenhuma palavra em comum com o contato esperado.
                                # Evita falsos positivos (ex: retornar "Gabriel" ao buscar "Mariana Ruiz").
                                returned_name = (best_contact.get("name") or "").lower().strip()
                                contact_words = {w for w in contact.lower().split() if len(w) >= 3}
                                if returned_name and contact_words and not any(w in returned_name for w in contact_words):
                                    print(f"[WA Resolver] by-number({p}) retornou '{returned_name}' mas esperava '{contact}' — rejeitando nome divergente.")
                                    continue
                                cid = _chat_id_str(best_contact)
                                # Sempre usa o número do Pipedrive (phone_digits) como JID,
                                # não o que o bridge retornou — o bridge pode ter dados errados.
                                cid = f"{p}@c.us"
                                return cid, best_contact.get("name") or contact
                    except Exception: continue

                # Se falhou por telefone, mas o nome é COMPOSTO ou temos nome da empresa,
                # permitimos o fallback por nome com regras estritas para evitar homônimos.
                is_specific_name = len(contact.strip().split()) >= 2
                if not (is_specific_name or org_name):
                    print(f"[WA Resolver] Telefone ({phone_digits}) não encontrado e nome '{contact}' é muito genérico. Encerrando para evitar homônimos.")
                    return None, ""

                print(f"[WA Resolver] Telefone ({phone_digits}) não encontrado. Tentando fallback por nome '{contact}'...")

            # 2. Busca por nome (em chats ativos)
            term = contact.lower()
            matches = [c for c in all_chats if term in (c.get("name") or "").lower()]

            def _name_has_org(name: str) -> bool:
                """Verifica se o nome do chat contém o org_clean (sem espaços para cobrir variações)."""
                return org_clean in _remove_diacritics(name).replace(" ", "")

            # Se temos nome da empresa, prioriza quem tem o nome da empresa no chat
            if org_clean and matches:
                org_matches = [c for c in matches if _name_has_org(c.get("name") or "")]
                if org_matches: matches = org_matches

            if matches:
                # Se org_name foi fornecido e nenhum match nos chats contém o nome da empresa,
                # há risco de homônimo. Faz contacts search com threshold menor para tentar
                # encontrar a versão específica (ex: "Mariana Ruiz - Compras MasterSense")
                # antes de aceitar o match genérico dos chats ativos.
                if org_clean and not any(_name_has_org(c.get("name") or "") for c in matches):
                    try:
                        c_resp_org = await client.get(
                            f"{WA_BASE}/contacts/search",
                            params={"name": contact, "minSimilarity": 0.6},
                            timeout=5.0,
                        )
                        if c_resp_org.status_code == 200:
                            c_data_org = c_resp_org.json()
                            cl_org = c_data_org if isinstance(c_data_org, list) else (c_data_org.get("contacts") or [])
                            org_specific = [c for c in cl_org if _name_has_org(c.get("name") or "")]
                            if org_specific:
                                best_specific = org_specific[0]
                                chat_id_s = _chat_id_str(best_specific)
                                cid_s = chat_id_s.split("@")[0] if "@" in chat_id_s else chat_id_s
                                is_lid_s = "@lid" in chat_id_s or (cid_s.isdigit() and len(cid_s) > 13)
                                # Para leitura: mantém o LID — mensagens ficam armazenadas sob ele.
                                if is_lid_s and "@" not in chat_id_s:
                                    chat_id_s = f"{cid_s}@lid"
                                return chat_id_s, best_specific.get("name") or contact
                    except Exception:
                        pass
                    # Nenhum contato org-específico encontrado — não aceita match de homônimo.
                    # Retorna vazio para evitar enviar/ler mensagens do contato errado.
                    return None, ""

                exact_matches = [c for c in matches if term == (c.get("name") or "").lower()]
                if exact_matches:
                    matches = exact_matches
                best = max(
                    matches,
                    key=lambda c: (c.get("lastMessage", {}) or {}).get("timestamp", 0)
                    if isinstance(c.get("lastMessage"), dict) else 0,
                )
                return _chat_id_str(best), best.get("name", contact)

        # 🔍 Fallback: Busca nos CONTATOS cadastrados por nome
        try:
            c_resp = await client.get(f"{WA_BASE}/contacts/search", params={"name": contact, "minSimilarity": 0.8}, timeout=5.0)
            if c_resp.status_code == 200:
                c_data = c_resp.json()
                contacts_list = c_data if isinstance(c_data, list) else c_data.get("contacts") or []

                if org_clean:
                    org_contacts = [c for c in contacts_list if _name_has_org(c.get("name") or "")]
                    if org_contacts: contacts_list = org_contacts

                if contacts_list:
                    best_contact = contacts_list[0]
                    chat_id = _chat_id_str(best_contact)

                    cid_num = chat_id.split("@")[0] if "@" in chat_id else chat_id
                    is_lid_like = "@lid" in chat_id or (cid_num.isdigit() and len(cid_num) > 13)
                    if is_lid_like:
                        # Contato usa LID — mantém @lid para leitura.
                        # Mensagens ficam armazenadas sob o LID, não sob o número @c.us.
                        if "@" not in chat_id:
                            chat_id = f"{cid_num}@lid"
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
        from core.infra.database import async_session
        from api.v1.routers.conversations import log_activity
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


def _fix_llama_corrupted_name(name: str) -> str:
    """Corrige nomes corrompidos pelo tokenizador Llama (ex: 'Colch9es', 'Colch43 147453541' -> 'Colchões')."""
    if not name:
        return name
    import re
    # 1. Caso com "es" no final (ex: 'Colch9es' -> 'Colchões')
    name = re.sub(r'Colch\d+(\s+\d+)?es', 'Colchões', name, flags=re.IGNORECASE)
    # 2. Caso geral sem "es" ou com espaços (ex: 'Colch43 147453541' -> 'Colchões')
    name = re.sub(r'Colch\d+(\s+\d+)?', 'Colchões', name, flags=re.IGNORECASE)
    # 3. Caso genérico para outras palavras terminadas em \d+es (ex: 'Solu9es' -> 'Solucoes')
    name = re.sub(r'([a-zA-Z]+)\d+es', r'\1oes', name)
    return name


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
    org_name = _fix_llama_corrupted_name(org_name)
    from modules.crm.service.pipedrive_service import pipedrive_service
    import unicodedata
    import re

    orgs = await pipedrive_service.list_organizations()
    if not orgs:
        return None, None

    term = org_name.lower().strip()
    term_clean = _remove_diacritics(org_name)
    term_norm = _normalize_org_name(org_name)
    term_norm_clean = _remove_diacritics(term_norm)

    # 🚀 UNIVERSAL DETECTOR: Cria regex dinâmico para curar QUALQUER corrupção do Llama
    words = org_name.split()
    has_corruption = False
    pattern_parts = []
    for w in words:
        if re.search(r'[a-zA-Z]\d+[a-zA-Z]', w):
            has_corruption = True
            part = re.sub(r'\d+', '.*', w.lower())
            pattern_parts.append(part)
        elif re.search(r'[a-zA-Z]\d+$', w):
            has_corruption = True
            part = re.sub(r'\d+', '.*', w.lower())
            pattern_parts.append(part)
        elif re.match(r'^\d+$', w) and len(pattern_parts) > 0:
            pattern_parts.append(r'.*')
        else:
            pattern_parts.append(re.escape(w.lower()))
    corruption_regex = r'\s+'.join(pattern_parts) if has_corruption else None

    matches = []
    for o in orgs:
        name_raw = o.get("name") or ""
        name_lower = name_raw.lower()
        name_clean = _remove_diacritics(name_raw)
        name_norm = _normalize_org_name(name_raw)
        name_norm_clean = _remove_diacritics(name_norm)

        score = 0
        is_match = False

        # 0. Match Universal para Corrupções do Llama (ex: 'colch9es' -> 'colchões', 'solu9es' -> 'soluções')
        if corruption_regex:
            if re.search(corruption_regex, name_lower) or re.search(corruption_regex, name_clean):
                score += 95
                is_match = True

        # 1. Matching por substring (com e sem acento)
        if not is_match:
            if term in name_lower:
                score += 100
                is_match = True
            elif term_clean in name_clean:
                score += 80
                is_match = True
            elif len(name_clean) >= 6 and name_clean in term_clean:
                # Substring invertida: o nome curto cadastrado no banco (ex: "Flex Do") está contido na busca longa ("Flex do Brasil Colchões")
                score += 75
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

        # 3b. Matching de subconjunto de palavras (se todas as palavras do nome no banco estão na busca)
        if not is_match:
            name_words = [w for w in name_clean.split() if len(w) >= 3]
            if name_words and all(w in term_clean for w in name_words):
                score += 70
                is_match = True

        # 4. Matching Fuzzy / Difflib SequenceMatcher (para erros de digitação, ex: "Flex do Brasil" vs "Fex do Brasil")
        if not is_match:
            import difflib
            ratio = difflib.SequenceMatcher(None, term_clean, name_clean).ratio()
            if ratio > 0.75:
                score += int(ratio * 80)
                is_match = True
            else:
                clean_term_words = [w for w in term_clean.split() if w not in ("colchoes", "colchao", "colchaes")]
                clean_name_words = [w for w in name_clean.split() if w not in ("colchoes", "colchao", "colchaes")]
                term_subset = " ".join(clean_term_words)
                name_subset = " ".join(clean_name_words)
                if term_subset and name_subset:
                    sub_ratio = difflib.SequenceMatcher(None, term_subset, name_subset).ratio()
                    if sub_ratio > 0.80:
                        score += int(sub_ratio * 75)
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
    from modules.crm.service.pipedrive_service import pipedrive_service
    orgs = await pipedrive_service.list_organizations()
    match = next((o for o in (orgs or []) if o.get("id") == org_id), None)
    return match


async def _extract_org_domain(org_name: str, org_id: int | None = None) -> str | None:
    """Busca o domínio de e-mail de uma empresa no banco local ou no Pipedrive."""
    INVALID_DOMAINS = {
        "gmail.com", "hotmail.com", "yahoo.com", "yahoo.com.br", "outlook.com", 
        "icloud.com", "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br",
        "hunter.io", "mail.hunter.io", "lusha.com", "zoominfo.com", "pipedrive.com", "snov.io"
    }
    try:
        from core.infra.database import async_session
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
                domain_clean = domain.lower().replace("www.", "").strip()
                if domain_clean and domain_clean not in INVALID_DOMAINS:
                    return domain_clean

        # 2. Verifica o campo domain do próprio org no Pipedrive (ex: "apice.com.br")
        if match is None:
            match = await _pipedrive_get_org_by_id(org_id)
        if match:
            pd_domain = (match.get("domain") or "").lower().replace("www.", "").strip()
            if pd_domain and not pd_domain.endswith(JFERRES_DOMAIN) and pd_domain not in INVALID_DOMAINS:
                return pd_domain

        # 3. Fallback: Busca via contatos no Pipedrive
        from modules.crm.service.pipedrive_service import pipedrive_service
        details = await pipedrive_service.get_organization_details(org_id)
        for p in (details.get("persons") or []):
            for em in (p.get("email") or []):
                val = (em.get("value") or "").strip()
                if val and "@" in val and not val.endswith(JFERRES_DOMAIN):
                    extracted = val.split("@")[1].lower()
                    if extracted and extracted not in INVALID_DOMAINS:
                        return extracted
    except Exception:
        pass
    return None


async def _pipedrive_email_for_contact(contact: str, org_name: str, org_id: int | None = None) -> str:
    """Busca o email real de um contato no Pipedrive. Retorna string vazia se não encontrado."""
    try:
        from modules.crm.service.pipedrive_service import pipedrive_service
        if org_id:
            details = await pipedrive_service.get_organization_details(org_id)
        else:
            _, pd_org_id = await _pipedrive_find_org(org_name)
            if not pd_org_id:
                return ""
            details = await pipedrive_service.get_organization_details(pd_org_id)
        persons = details.get("persons", []) if isinstance(details, dict) else []
        contact_lower = contact.lower()
        for p in persons:
            pname = (p.get("name") or "").lower()
            if contact_lower in pname or pname in contact_lower:
                email_list = p.get("email", [])
                pd_email = next(
                    (x.get("value") for x in email_list if x.get("value")),
                    None
                ) if isinstance(email_list, list) else None
                if pd_email:
                    return pd_email.lower()
    except Exception as _e:
        log.debug(f"_pipedrive_email_for_contact error: {_e}")
    return ""


async def _pipedrive_phone_for_contact(contact: str, org_name: str) -> str:
    """Busca o telefone real de um contato no Pipedrive. Retorna string vazia se não encontrado."""
    try:
        import re as _re
        from modules.crm.service.pipedrive_service import pipedrive_service
        _, pd_org_id = await _pipedrive_find_org(org_name)
        if not pd_org_id:
            return ""
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
                    return _re.sub(r'\D', '', pd_phone)
    except Exception as _e:
        log.debug(f"_pipedrive_phone_for_contact error: {_e}")
    return ""
