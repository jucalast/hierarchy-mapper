"""
core.external.email_service
===========================
Descoberta e validacao de e-mails corporativos brasileiros.

Gera combinacoes de padrao nome+dominio (12 padroes: first.last, flast, etc.)
e valida via MX record + SMTP probe sem autenticacao.

Funcoes publicas:
    discover_and_validate_email(first, last, domain, known_pattern, smtp) -> dict
    generate_all_patterns(first, last, domain) -> list[str]
    apply_pattern(first, last, domain, pattern) -> str
    get_mx_record(domain) -> str | None
    smtp_probe(email, mx_host, timeout) -> str
"""
import re
import socket
import smtplib
from typing import List

def verify_email(email: str) -> bool:
    """
    Validação de email genérica sem dependências de APIs externas.
    Usa validação sintática + verificação de domínio + SMTP check (opcional).
    """
    if not email or '@' not in email:
        return False
    
    # Validação sintática básica
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    
    domain = email.split('@')[1]
    
    try:
        # Verifica se o domínio existe
        socket.gethostbyname(domain)
        # ⚠️ Verificação SMTP foi removida pois gerava Timeout e gargalos no processamento em lote
        return True
            
    except socket.gaierror:
        return False
    
    return True

def get_permutations(first: str, last: str, domain: str) -> List[tuple]:
    """Retorna formatos possíveis e seu identificador de padrão."""
    return [
        (f"{first}.{last}@{domain}", "first.last"),
        (f"{first[0]}{last}@{domain}", "f_last"),
        (f"{first}{last}@{domain}", "firstlast"),
        (f"{first}@{domain}", "first")
    ]

def apply_pattern(first: str, last: str, domain: str, pattern: str) -> str:
    """Aplica o padrão vencedor a um novo funcionário."""
    if pattern == "first.last": return f"{first}.{last}@{domain}"
    if pattern == "f_last": return f"{first[0]}{last}@{domain}"
    if pattern == "firstlast": return f"{first}{last}@{domain}"
    if pattern == "first": return f"{first}@{domain}"
    return f"{first}.{last}@{domain}" # default


# === EMAIL DISCOVERY ENGINE ===

import asyncio
import dns.resolver  # dnspython — already in venv

# 10+ patterns covering Brazilian corporate email conventions
_ALL_PATTERNS = [
    ("first.last",      lambda f, l, d: f"{f}.{l}@{d}"),
    ("f.last",          lambda f, l, d: f"{f[0]}.{l}@{d}"),
    ("f_last",          lambda f, l, d: f"{f[0]}{l}@{d}"),
    ("firstlast",       lambda f, l, d: f"{f}{l}@{d}"),
    ("first",           lambda f, l, d: f"{f}@{d}"),
    ("last.first",      lambda f, l, d: f"{l}.{f}@{d}"),
    ("last",            lambda f, l, d: f"{l}@{d}"),
    ("first_last",      lambda f, l, d: f"{f}_{l}@{d}"),
    ("first.l",         lambda f, l, d: f"{f}.{l[0]}@{d}"),
    ("flast",           lambda f, l, d: f"{f}{l}@{d}"),   # alias
    ("f.l",             lambda f, l, d: f"{f[0]}.{l[0]}@{d}"),
]

def generate_all_patterns(first: str, last: str, domain: str):
    """Returns list of (email, pattern_id) for all patterns."""
    f = first.lower().strip()
    l = last.lower().strip()
    # Remove accents for email
    import unicodedata
    f = ''.join(c for c in unicodedata.normalize('NFD', f) if unicodedata.category(c) != 'Mn').replace(" ", "")
    l = ''.join(c for c in unicodedata.normalize('NFD', l) if unicodedata.category(c) != 'Mn').replace(" ", "")
    seen = set()
    results = []
    for pid, fn in _ALL_PATTERNS:
        try:
            email = fn(f, l, domain)
            if email not in seen:
                seen.add(email)
                results.append((email, pid))
        except IndexError:
            pass
    return results

def detect_domain_pattern(known_emails: list, domain: str):
    """
    Given a list of known valid emails for a domain, infer the email pattern.
    Returns pattern_id string or None.
    """
    for email in known_emails:
        if not email or '@' not in email:
            continue
        local = email.split('@')[0].lower()
        # Try to match against pattern templates using heuristics
        if '.' in local:
            parts = local.split('.')
            if len(parts) == 2 and len(parts[0]) > 1 and len(parts[1]) > 1:
                return "first.last"
            if len(parts) == 2 and len(parts[0]) == 1:
                return "f.last"
        if '_' in local:
            return "first_last"
        if len(local) <= 6:
            return "first"
    return None

async def get_mx_record(domain: str):
    """Returns the primary MX hostname for a domain, or None."""
    try:
        loop = asyncio.get_event_loop()
        records = await loop.run_in_executor(
            None, lambda: dns.resolver.resolve(domain, 'MX', lifetime=5)
        )
        # Sort by preference, return first
        mx_records = sorted(records, key=lambda r: r.preference)
        return str(mx_records[0].exchange).rstrip('.')
    except Exception:
        return None

async def smtp_probe(email: str, mx_host: str, timeout: float = 5.0) -> str:
    """
    Non-blocking SMTP probe. Returns 'valid', 'invalid', or 'unknown'.
    'unknown' = server refused to answer definitively (catch-all, greylisting, etc.)
    """
    import asyncio
    domain = email.split('@')[0] if '@' in email else 'probe'
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(mx_host, 25),
            timeout=timeout
        )
        async def readline():
            return (await asyncio.wait_for(reader.readline(), timeout=timeout)).decode(errors='replace')
        async def writeline(s):
            writer.write((s + '\r\n').encode())
            await writer.drain()

        await readline()  # banner
        await writeline('EHLO emailprobe.local')
        # Read all EHLO lines
        while True:
            line = await readline()
            if line.startswith('250 ') or not line.startswith('250'):
                break
        await writeline('MAIL FROM:<probe@emailprobe.local>')
        resp_mail = await readline()
        if not resp_mail.startswith('250'):
            writer.close()
            return 'unknown'
        await writeline(f'RCPT TO:<{email}>')
        resp_rcpt = await readline()
        writer.close()
        code = resp_rcpt[:3]
        if code == '250':
            return 'valid'
        if code in ('550', '551', '552', '553', '554', '450', '451', '452'):
            return 'invalid'
        return 'unknown'
    except Exception:
        return 'unknown'

_GENERIC_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "uol.com.br", "bol.com.br", "terra.com.br", "ig.com.br", "yahoo.com.br",
    "outlook.com.br", "hotmail.com.br", "icloud.com", "aol.com"
}

async def verify_email_via_quickemailverification(email: str, api_key: str) -> str:
    """
    Verifica um e-mail através da API QuickEmailVerification.
    Retorna 'valid', 'invalid', 'rate_limited' ou 'unknown'.
    """
    import httpx
    try:
        url = "https://api.quickemailverification.com/v1/verify"
        params = {"apikey": api_key, "email": email}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                data = r.json()
                res = (data.get("result") or "").lower()
                if res == "valid":
                    return "valid"
                elif res == "invalid":
                    return "invalid"
            elif r.status_code in (401, 402, 403, 429):
                return "rate_limited"
            return "unknown"
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[QuickEmailVerification] Falha ao verificar email {email}: {e}")
        return "unknown"

async def verify_email_via_abstract_api(email: str, api_key: str) -> str:
    """
    Verifica um e-mail através da Abstract API.
    Retorna 'valid', 'invalid', 'rate_limited' ou 'unknown'.
    """
    import httpx
    try:
        url = "https://emailvalidation.abstractapi.com/v1/"
        params = {"api_key": api_key, "email": email}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                data = r.json()
                deliverability = (data.get("deliverability") or "").lower()
                if deliverability == "deliverable":
                    return "valid"
                elif deliverability == "undeliverable":
                    return "invalid"
            elif r.status_code in (401, 402, 403, 429):
                return "rate_limited"
            return "unknown"
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[AbstractAPI] Falha ao verificar email {email}: {e}")
        return "unknown"

async def verify_email_via_vrfymail(email: str, api_key: str) -> str:
    """
    Verifica um e-mail através da API verifymail.io (Vrfymail).
    Retorna 'valid', 'invalid', 'rate_limited' ou 'unknown'.
    """
    import httpx
    try:
        url = f"https://verifymail.io/api/{email}"
        params = {"key": api_key}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                data = r.json()
                if data.get("deliverable_email") is True:
                    return "valid"
                elif data.get("deliverable_email") is False:
                    return "invalid"
            elif r.status_code in (401, 402, 403, 429):
                return "rate_limited"
            return "unknown"
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[Vrfymail] Falha ao verificar email {email}: {e}")
        return "unknown"

def parse_api_keys(key_string: str) -> List[str]:
    """Separa chaves por vírgula, limpa espaços e barras invertidas."""
    if not key_string:
        return []
    keys = []
    for k in key_string.split(','):
        cleaned = k.rstrip("\\").strip()
        if cleaned:
            keys.append(cleaned)
    return keys

async def discover_and_validate_email(
    first: str, last: str, domain: str,
    known_pattern=None,
    do_smtp: bool = True,
    additional_candidates: list[str] = None
) -> dict:
    """
    Full email discovery pipeline:
    1. Generates all patterns + merges web-harvested candidates
    2. If known_pattern exists, puts it first (economiza créditos validando apenas 1 candidato)
    3. Validates candidates via APIs (QuickEmailVerification / Abstract / Vrfymail)
    4. Dynamically filters out candidates proven invalid by APIs to prevent false positives
    5. Falls back to MX + SMTP probe for remaining non-invalid candidates
    """
    candidates = generate_all_patterns(first, last, domain)

    if additional_candidates:
        all_emails = list(dict.fromkeys(additional_candidates + [e for e, _ in candidates]))
        candidates_map = {e: p for e, p in candidates}
        candidates = [(e, candidates_map.get(e, "web_harvested")) for e in all_emails]

    # Put known pattern first if provided to achieve maximum credit efficiency (tests just 1 credit if valid)
    if known_pattern:
        reordered = [(e, p) for e, p in candidates if p == known_pattern]
        reordered += [(e, p) for e, p in candidates if p != known_pattern]
        candidates = reordered

    # MX check (domain level, done once)
    mx_host = await get_mx_record(domain)
    mx_valid = mx_host is not None

    if not mx_valid:
        # Domain has no mail server — all emails are invalid
        best = candidates[0] if candidates else (f"{first}.{last}@{domain}", "first.last")
        return {
            "email": best[0], "pattern": best[1],
            "confidence": "low", "mx_valid": False, "smtp_result": "invalid",
            "all_candidates": [e for e, _ in candidates]
        }

    # Evita desperdício de créditos para provedores de e-mail genéricos/públicos (ex: gmail)
    is_generic = domain in _GENERIC_DOMAINS
    invalid_candidates = set()

    # --- EXTERNAL VALIDATION (APIs) ---
    import os
    from core.config import settings
    
    if not is_generic and mx_valid:
        # 1. Tenta QuickEmailVerification (Altíssimo volume: 100 créditos/dia grátis)
        qev_keys = parse_api_keys(os.environ.get("QUICKEMAIL_API_KEY", ""))
        if qev_keys:
            current_key_idx = 0
            for email, pattern in candidates[:6]:
                if email in invalid_candidates:
                    continue
                
                while current_key_idx < len(qev_keys):
                    key = qev_keys[current_key_idx]
                    result = await verify_email_via_quickemailverification(email, key)
                    if result == 'rate_limited':
                        current_key_idx += 1
                        continue
                    elif result == 'valid':
                        return {
                            "email": email, "pattern": pattern,
                            "confidence": "high", "mx_valid": True, "smtp_result": "valid",
                            "all_candidates": [e for e, _ in candidates]
                        }
                    elif result == 'invalid':
                        invalid_candidates.add(email)
                        break
                    else:
                        break

        # 2. Tenta Abstract API (Alta precisão: 100 créditos/mês)
        abstract_keys = parse_api_keys(getattr(settings, "EMAIL_API_KEY", None) or os.environ.get("EMAIL_API_KEY", ""))
        if abstract_keys:
            current_key_idx = 0
            for email, pattern in candidates[:3]:
                if email in invalid_candidates:
                    continue
                    
                while current_key_idx < len(abstract_keys):
                    key = abstract_keys[current_key_idx]
                    result = await verify_email_via_abstract_api(email, key)
                    if result == 'rate_limited':
                        current_key_idx += 1
                        continue
                    elif result == 'valid':
                        return {
                            "email": email, "pattern": pattern,
                            "confidence": "high", "mx_valid": True, "smtp_result": "valid",
                            "all_candidates": [e for e, _ in candidates]
                        }
                    elif result == 'invalid':
                        invalid_candidates.add(email)
                        break
                    else:
                        break

        # 3. Tenta Vrfymail (Fallback final: 3 créditos/dia)
        vrfy_keys = parse_api_keys(os.environ.get("VRFYMAIL_API_KEY", ""))
        if vrfy_keys:
            current_key_idx = 0
            for email, pattern in candidates[:6]:
                if email in invalid_candidates:
                    continue
                
                while current_key_idx < len(vrfy_keys):
                    key = vrfy_keys[current_key_idx]
                    result = await verify_email_via_vrfymail(email, key)
                    if result == 'rate_limited':
                        current_key_idx += 1
                        continue
                    elif result == 'valid':
                        return {
                            "email": email, "pattern": pattern,
                            "confidence": "high", "mx_valid": True, "smtp_result": "valid",
                            "all_candidates": [e for e, _ in candidates]
                        }
                    elif result == 'invalid':
                        invalid_candidates.add(email)
                        break
                    else:
                        break

    # Filtra e-mails comprovadamente inválidos
    remaining_candidates = [(e, p) for e, p in candidates if e not in invalid_candidates]

    if not remaining_candidates:
        # Todos os candidatos possíveis foram testados pelas APIs e são comprovadamente inválidos
        best = candidates[0] if candidates else (f"{first}.{last}@{domain}", "first.last")
        return {
            "email": best[0], "pattern": best[1],
            "confidence": "low", "mx_valid": True, "smtp_result": "invalid",
            "all_candidates": [e for e, _ in candidates]
        }

    # --- INTERNAL VALIDATION (SMTP Probe Fallback) ---
    # Testa apenas os candidatos restantes (máximo 3) para evitar bloqueios de IP
    if do_smtp and mx_host:
        for email, pattern in remaining_candidates[:3]:
            result = await smtp_probe(email, mx_host)
            if result == 'valid':
                return {
                    "email": email, "pattern": pattern,
                    "confidence": "high", "mx_valid": True, "smtp_result": "valid",
                    "all_candidates": [e for e, _ in candidates]
                }
            elif result == 'invalid':
                invalid_candidates.add(email)
                continue
            
            # 'unknown' — servidor deu greylisting ou bloqueou porta 25.
            # Retorna o primeiro candidato restante que NÃO é comprovadamente inválido
            best = remaining_candidates[0]
            return {
                "email": best[0], "pattern": best[1],
                "confidence": "medium", "mx_valid": True, "smtp_result": "unknown",
                "all_candidates": [e for e, _ in candidates]
            }

    # Sem SMTP e sem resposta positiva de API — retorna o melhor candidato restante como estimativa
    best = remaining_candidates[0]
    return {
        "email": best[0], "pattern": best[1],
        "confidence": "medium" if mx_valid else "low",
        "mx_valid": mx_valid, "smtp_result": "skipped",
        "all_candidates": [e for e, _ in candidates]
    }
