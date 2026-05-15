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
from core.logging_config import get_logger
log = get_logger(__name__)

WA_BASE = "http://localhost:8001/api/whatsapp"
EMAIL_SERVICE_BASE = "http://localhost:8002/api/email"
JFERRES_DOMAIN = "jferres.com.br"


# ─── Helpers ──────────────────────────────────────────────────────────────────

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
    from services.pipedrive.pipedrive_service import pipedrive_service
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
    from services.pipedrive.pipedrive_service import pipedrive_service
    orgs = await pipedrive_service.list_organizations()
    match = next((o for o in (orgs or []) if o.get("id") == org_id), None)
    return match



# ─── Executores: READ ─────────────────────────────────────────────────────────

async def exec_whatsapp_get_messages(args: Dict[str, Any]) -> Dict[str, Any]:
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
        phone_arg = args.get("phone", "")
        phone_digits_arg = _re.sub(r'\D', '', phone_arg)
        if phone_digits_arg and len(phone_digits_arg) > 13:
            lid_chat_id = f"{phone_digits_arg}@lid"
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
    log.info("exec_email_get_contact_history", tool_args=args, org_id=org_id)
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
                    search_query = f"@{domain}"
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
                # "conversations" varre TODAS as pastas do Outlook recursivamente
                all_r = await client.get(f"{EMAIL_SERVICE_BASE}/messages", params={"folder": "conversations", "limit": limit * 2, "q": search_query})

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


async def exec_find_company_contact(args: dict) -> dict:
    """Busca contato da empresa via Receita Federal (BrasilAPI) e web search."""
    import re as _re
    org_name = args.get("org_name", "")
    cnpj_raw = args.get("cnpj", "")
    cnpj_clean = _re.sub(r"\D", "", cnpj_raw or "")

    # Se não veio CNPJ válido, tenta buscar no banco de dados pelo org_name
    if len(cnpj_clean) != 14 and org_name:
        try:
            from core.database import async_session
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
            from services.hierarchy.cnpj_resolver import fetch_company_data_by_cnpj, build_full_address
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


async def _pipedrive_email_for_contact(contact: str, org_name: str, org_id: int | None = None) -> str:
    """Busca o email real de um contato no Pipedrive. Retorna string vazia se não encontrado."""
    try:
        from services.pipedrive.pipedrive_service import pipedrive_service
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
        from services.pipedrive.pipedrive_service import pipedrive_service
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


async def exec_whatsapp_send_message(args: dict, messages: list | None = None, org_id: int | None = None) -> dict:
    """Envia uma mensagem de WhatsApp para um contato resolvido por nome, telefone ou empresa."""
    import re as _re
    from services.whatsapp_integration import WhatsAppIntegration

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
    res = await WhatsAppIntegration.send_message(chat_id, message)
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
                            res2 = await WhatsAppIntegration.send_message(fallback_jid, message)
                            if res2.get("ok"):
                                log.info(f"wa_send.lid_fallback_success chat_id={chat_id} fallback={fallback_jid}")
                                return {"ok": True, "result": f"Mensagem enviada com sucesso para {resolved_name or contact} (via número real: {fallback_jid})"}
        except Exception as e:
            log.warning(f"wa_send.lid_fallback_error: {e}")

    # Fallback Pipedrive: quando phone é LID E temos org_name, tenta o número real do Pipedrive
    if org_name and contact:
        try:
            import re as _re
            from services.pipedrive.pipedrive_service import pipedrive_service
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
                                res_pd = await WhatsAppIntegration.send_message(pd_jid, message)
                                if res_pd.get("ok"):
                                    log.info(f"wa_send.pipedrive_fallback_success jid={pd_jid}")
                                    return {"ok": True, "result": f"Mensagem enviada para {contact} via telefone do Pipedrive ({pd_jid})"}
        except Exception as _e:
            log.warning(f"wa_send.pipedrive_fallback_error: {_e}")

    return {"ok": False, "error": f"Erro ao enviar mensagem para {chat_id}: {res.get('error')}"}


async def exec_generate_dossier(args: dict) -> dict:
    """Sinaliza a fase de consolidação. Não faz chamada externa — apenas libera o agente para gerar o dossiê."""
    return {
        "ok": True,
        "summary": "Consolidação iniciada. Gere o dossiê final agora.",
    }


async def exec_generate_sales_message(args: dict, messages: list | None = None, org_id: int | None = None) -> dict:
    """Gera uma mensagem comercial: o LLM decide o modo (follow-up leve vs. venda ativa) com base no histórico e objetivo."""
    from services.ai.business_context_service import BusinessContextService
    from services.ai.llm.router import ask_llm
    from services.ai.llm.base import LLMTier
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
            from services.pipedrive.pipedrive_service import pipedrive_service
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


async def exec_evaluate_prospects(args: dict, org_id: int | None = None) -> dict:
    org_name = args.get("org_name", "")
    if not org_id and args.get("org_id"):
        try:
            org_id = int(args["org_id"])
        except (ValueError, TypeError):
            pass

    try:
        from core.database import async_session
        from models.organization import Organization
        from models.employee import Employee
        from services.ai.business_context_service import BusinessContextService
        from services.ai.llm import LLMTier, ask_llm
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


# ─── Registry ─────────────────────────────────────────────────────────────────

TOOLS: Dict[str, Dict[str, Any]] = {
    # ── WhatsApp ──────────────────────────────────────────────────────────────
    "whatsapp_get_messages": {
        "description": "Busca mensagens recentes do WhatsApp de um contato. Retorna as últimas N mensagens (padrão 60, máx 100). É OBRIGATÓRIO passar o 'phone' se você tiver essa informação, e o 'org_name' (nome da empresa) para garantir que encontremos o contato correto mesmo que o telefone falhe.",
        "args_schema": {
            "contact": "string (NOME EXATO DA PESSOA com quem você quer falar)",
            "phone": "string recomendado (telefone com DDD)",
            "org_name": "string recomendado (nome da empresa investigada para evitar homônimos)",
            "limit": "int (padrão 60, máx 100)"
        },
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
        "description": "Envia uma mensagem de WhatsApp para um contato. É ALTAMENTE RECOMENDADO passar o 'phone' e o 'org_name' para garantir que a mensagem chegue ao destinatário correto, evitando homônimos.",
        "args_schema": {
            "contact": "string (OBRIGATÓRIO: nome do contato para quem a mensagem será enviada)",
            "message": "string (texto completo da mensagem — escreva de forma profissional e personalizada)",
            "phone": "string opcional (telefone com DDD)",
            "org_name": "string opcional (nome da empresa investigada)",
        },
        "type": "write",
        "executor": exec_whatsapp_send_message,
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
        "description": "Busca TODO o histórico de e-mails (caixa de entrada e enviados). ÚNICA ferramenta permitida para investigar e-mails de uma empresa ou contato. IMPORTANTE: Se você tiver o e-mail do contato (encontrado em pipedrive_get_persons), é OBRIGATÓRIO passar o 'contact_email' para garantir a precisão da busca. Se a empresa NÃO tiver contatos cadastrados, passe o 'domain' ou 'org_name'.",
        "args_schema": {
            "contact_name": "string opcional (nome do contato)",
            "contact_email": "string opcional (e-mail do contato — USE SEMPRE QUE TIVER)",
            "org_name": "string opcional (nome da empresa — ajuda no fallback)",
            "domain": "string opcional (domínio do site/email da empresa. Ex: 'empresa.com.br')",
            "limit": "int (padrão 25)",
        },
        "type": "read",
        "executor": exec_email_get_contact_history,
    },
    "email_send": {
        "description": (
            "Envia um e-mail NOVO para um destinatário. Requer confirmação. "
            "Use email_reply para responder a um thread existente. "
            "Para enviar com anexo, use attachment_name com um dos valores pré-configurados: "
            "'apresentacao_linkb2b' (apresentação LINKB2B em PDF)."
        ),
        "args_schema": {
            "to": "string (e-mail do destinatário)",
            "subject": "string (assunto do e-mail)",
            "body": "string (corpo completo — escreva profissionalmente com saudação e assinatura)",
            "contact_name": "string opcional (nome do destinatário para o log)",
            "attachment_name": "string opcional — nome do anexo pré-configurado. Valores aceitos: 'apresentacao_linkb2b'",
        },
        "type": "write",
        "executor": None,
        "confirm_label": lambda args: (
            f"E-mail para {args.get('to')} — {args.get('subject', '')}"
            + (f" (+ anexo: {args.get('attachment_name')})" if args.get("attachment_name") else "")
        ),
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
        "args_schema": {
            "org_name": "string (nome da empresa — use quando souber o nome)",
            "org_id": "int opcional (ID da organização no Pipedrive — use quando souber o ID numérico mas não o nome)",
        },
        "type": "read",
        "executor": exec_pipedrive_get_org,
    },
    "pipedrive_get_persons": {
        "description": "Busca todos os contatos (pessoas) de uma organização no Pipedrive com telefone, e-mail e canais disponíveis. Use para identificar com quem falar.",
        "args_schema": {
            "org_name": "string (nome da empresa — use quando souber o nome)",
            "org_id": "int opcional (ID da organização no Pipedrive — use quando souber o ID numérico mas não o nome)",
        },
        "type": "read",
        "executor": exec_pipedrive_get_persons,
    },
    "pipedrive_get_deals": {
        "description": "Busca deals de uma organização com detalhes: título, status, valor, etapa e notas recentes. Use para entender o estado comercial.",
        "args_schema": {
            "org_name": "string (nome da empresa — use quando souber o nome)",
            "org_id": "int opcional (ID da organização no Pipedrive — use quando souber o ID numérico mas não o nome)",
        },
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
            "task_type": "string (call | meeting | task | deadline — use 'call' para ligações, 'task' para tarefas genéricas)",
            "due_date": "string opcional (data no formato YYYY-MM-DD)",
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

    # ── Busca de Contato na Internet ──────────────────────────────────────────
    "find_company_contact": {
        "description": (
            "Busca dados de contato de uma empresa via Receita Federal (BrasilAPI) e web search. "
            "Use quando: (1) o mapeamento de hierarquia não encontrou nenhum contato com telefone/email; "
            "ou (2) o contato existe mas não tem canal cadastrado. "
            "Retorna telefone(s) da Receita Federal, email cadastrado, endereço e snippets de web. "
            "Se encontrar dados, use pipedrive_create_person para salvar o contato."
        ),
        "args_schema": {
            "org_name": "string — nome da empresa",
            "cnpj": "string opcional — CNPJ da empresa (14 dígitos, com ou sem formatação)",
        },
        "type": "read",
        "executor": exec_find_company_contact,
    },

    # ── Geração de Scripts ─────────────────────────────────────────────────────
    "generate_call_script": {
        "description": (
            "Gera script de ligação. "
            "CONDIÇÕES OBRIGATÓRIAS para chamar (TODAS devem ser verdadeiras):\n"
            "  1. A descrição da tarefa é EXPLICITAMENTE uma ligação (contém 'ligar', 'ligação', 'chamada', 'call').\n"
            "     PROIBIDO chamar se a tarefa for 'cobrar retorno', 'follow-up', 'acompanhamento' ou similar — "
            "     nesses casos use email_reply ou whatsapp_send_message após ler o histórico.\n"
            "  2. Você JÁ executou TODOS os 6 passos da Fase 1: pipedrive_get_org, pipedrive_get_persons, "
            "     pipedrive_get_deals, pipedrive_get_activities, whatsapp_get_messages, email_get_contact_history.\n"
            "  3. pipedrive_get_persons retornou um telefone REAL para o contato (não placeholder, não inventado).\n"
            "NÃO chame se qualquer condição não for atendida."
        ),
        "args_schema": {
            "contact_name": "string — nome do contato que será ligado",
            "phone": "string — telefone real retornado por pipedrive_get_persons",
        },
        "type": "read",
        "executor": exec_generate_call_script,
    },
    "generate_sales_message": {
        "description": "Usa o Coach de Vendas Sênior para gerar um rascunho de mensagem (WhatsApp ou E-mail) altamente estratégico baseado no histórico real. Use quando identificar que o canal preferido de contato é digital (WhatsApp/Email).",
        "args_schema": {
            "contact_name": "string (nome da pessoa)",
            "channel": "string ('whatsapp' ou 'email')",
            "goal": "string (o que você quer alcançar com essa mensagem, ex: 'cobrar retorno da cotação x')",
        },
        "type": "read",
        "executor": exec_generate_sales_message,
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
    "open_hierarchy_drawer": {
        "description": (
            "Abre o mapeador de hierarquia para uma empresa, solicitando ao usuário que inicie o mapeamento de contatos e decisores. "
            "REGRA DE OURO: ANTES de chamar esta ferramenta, você DEVE OBRIGATORIAMENTE concluir as buscas no Pipedrive (org, persons, deals, activities) e o histórico de comunicações (whatsapp_get_messages e email_get_contact_history). "
            "Só chame open_hierarchy_drawer se, APÓS concluir essas buscas, constatar que: (1) não há contatos cadastrados; ou (2) os contatos existentes não possuem telefone/e-mail válido nem histórico de comunicação relevante que resolva a tarefa."
        ),
        "args_schema": {
            "org_name": "string (nome da empresa)",
            "org_id": "int opcional (ID da empresa no Pipedrive)",
            "deal_id": "int opcional (ID do deal associado)",
            "activity_id": "int opcional (ID da atividade original relacionada)",
            "pre_task_id": "int opcional (ID da tarefa 'Encontrar decisor' criada no Pipedrive antes de abrir o mapeador — será marcada como concluída após o mapeamento)",
        },
        "type": "read",
        "executor": exec_open_hierarchy_drawer,
    },
    "suggest_next_actions": {
        "description": (
            "Gera um conjunto personalizado de próximos passos executáveis baseados no contexto REAL do negócio. "
            "O serviço analisa automaticamente o histórico da conversa (dados do Pipedrive, WhatsApp, Email) e "
            "gera 5-8 sugestões cobrindo TODAS as categorias: mensagens, tarefas CRM, agendamento de reuniões, "
            "atualização de deals, estratégias. "
            "QUANDO CHAMAR: após qualquer investigação concluída, ao final de um follow-up enviado, "
            "ou quando o usuário pede próximos passos. "
            "PODE passar 'actions' como array vazio [] — o serviço extrai contexto do histórico automaticamente. "
            "IMPORTANTE: inclua no array 'actions' apenas se você já sabe as ações específicas com IDs; "
            "caso contrário, passe [] e o serviço gerará as sugestões com base no histórico."
        ),
        "args_schema": {
            "actions": "array (pode ser vazio []) — o serviço gera sugestões automaticamente a partir do histórico. Se quiser pré-definir alguma ação específica com IDs concretos, inclua objetos com 'label' e 'prompt'."
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
    "evaluate_prospects": {
        "description": "Analisa todos os contatos aprovados e mapeados no banco de dados local para uma organização e identifica quais pessoas ou grupos são as melhores opções para prospectar com base no produto oferecido.",
        "args_schema": {
            "org_name": "string (nome da empresa)",
            "org_id": "int opcional (ID da empresa no Pipedrive)"
        },
        "type": "read",
        "executor": exec_evaluate_prospects,
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
        result = await exec_whatsapp_send_message(args, org_id=org_id)
        if result.get("ok"):
            await _log_activity_bg(
                "whatsapp_sent",
                {
                    "to_name": args.get("contact_name") or args.get("contact", ""),
                    "to_phone": args.get("phone", ""),
                    "message_preview": args.get("message", "")[:200],
                },
                org_id=org_id,
            )
        return result

    # ── Email: envio novo ──────────────────────────────────────────────────────
    elif tool_name == "email_send":
        import os as _os
        to = args.get("to", "")
        subject = args.get("subject", "")
        body = args.get("body", "")

        # Resolve attachment_name → caminho absoluto via settings
        attachment_paths: list[str] = []
        att_name = args.get("attachment_name", "")
        if att_name:
            try:
                from core.config import settings as _s
                _ATTACHMENT_MAP = {
                    "apresentacao_linkb2b": getattr(_s, "LINKB2B_PRESENTATION_PATH", ""),
                }
                path = _ATTACHMENT_MAP.get(att_name, "")
                if path and _os.path.exists(path):
                    attachment_paths.append(path)
                elif path:
                    import logging as _log
                    _log.warning(f"[email_send] Anexo '{att_name}' configurado mas arquivo não encontrado: {path}")
            except Exception:
                pass

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    f"{EMAIL_SERVICE_BASE}/send",
                    json={"to_email": to, "subject": subject, "body": body, "attachment_paths": attachment_paths or None},
                )
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
        # "task_type" é o nome canônico (renomeado de "type" para evitar conflito com JSON Schema)
        task_type = args.get("task_type") or args.get("type", "task")
        due_date = args.get("due_date", "")
        note = args.get("note", "")
        deal_id = args.get("deal_id")
        org_name = args.get("org_name", "")

        type_map = {"tarefa": "task", "ligação": "call", "ligar": "call", "reunião": "meeting", "prazo": "deadline"}
        task_type = type_map.get(str(task_type).lower(), task_type)

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
