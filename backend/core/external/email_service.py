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
    f = ''.join(c for c in unicodedata.normalize('NFD', f) if unicodedata.category(c) != 'Mn')
    l = ''.join(c for c in unicodedata.normalize('NFD', l) if unicodedata.category(c) != 'Mn')
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

async def discover_and_validate_email(
    first: str, last: str, domain: str,
    known_pattern=None,
    do_smtp: bool = True
) -> dict:
    """
    Full email discovery pipeline:
    1. Generates all patterns
    2. If known_pattern exists, puts it first
    3. Validates via MX + optional SMTP probe
    Returns dict with: email, pattern, confidence ('high'|'medium'|'low'), mx_valid, smtp_result
    """
    candidates = generate_all_patterns(first, last, domain)

    # Put known pattern first if provided
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

    # SMTP probe only the top candidates (max 3 to avoid being blocked)
    if do_smtp and mx_host:
        for email, pattern in candidates[:3]:
            result = await smtp_probe(email, mx_host)
            if result == 'valid':
                return {
                    "email": email, "pattern": pattern,
                    "confidence": "high", "mx_valid": True, "smtp_result": "valid",
                    "all_candidates": [e for e, _ in candidates]
                }
            if result == 'invalid':
                continue
            # 'unknown' — server is catch-all or blocked, use pattern heuristic
            best = candidates[0]
            return {
                "email": best[0], "pattern": best[1],
                "confidence": "medium", "mx_valid": True, "smtp_result": "unknown",
                "all_candidates": [e for e, _ in candidates]
            }

    # No SMTP — return best candidate with medium confidence
    best = candidates[0] if candidates else (f"{first}.{last}@{domain}", "first.last")
    return {
        "email": best[0], "pattern": best[1],
        "confidence": "medium" if mx_valid else "low",
        "mx_valid": mx_valid, "smtp_result": "skipped",
        "all_candidates": [e for e, _ in candidates]
    }
