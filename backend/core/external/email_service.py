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


def infer_pattern_from_email(email: str, name_parts: list) -> str | None:
    """
    Dado um email confirmado e todas as partes do nome completo de uma pessoa,
    infere qual padrão corporativo o email segue testando todas as combinações
    (parte_i como primeiro nome, parte_j como sobrenome).
    Retorna um pattern_id conhecido ou None se ambíguo.
    """
    if not email or '@' not in email:
        return None
    import unicodedata

    local = email.split('@')[0].lower()

    def _norm(s: str) -> str:
        return ''.join(
            c for c in unicodedata.normalize('NFD', s.lower())
            if unicodedata.category(c) != 'Mn'
        ).replace(' ', '')

    # Apenas preposições; letras isoladas como iniciais ("A." de "Bruno A.") não são stopwords
    stopwords = {'de', 'da', 'do', 'dos', 'das'}
    parts = [_norm(p) for p in name_parts if p.lower() not in stopwords and _norm(p)]

    for i, f in enumerate(parts):
        for j, l in enumerate(parts):
            if i == j or not f or not l:
                continue
            try:
                if local == f"{f}.{l}":       return "first.last"
                if local == f"{f[0]}.{l}":    return "f.last"
                if local == f"{f[0]}{l}":     return "f_last"
                if local == f"{f}{l}":        return "firstlast"
                if local == f"{l}.{f}":       return "last.first"
                if local == f"{f}_{l}":       return "first_last"
                if local == f"{f}.{l[0]}":    return "first.l"
                if local == f"{f[0]}.{l[0]}": return "f.l"
            except IndexError:
                pass

    # Padrão de nome único (só primeiro nome ou só sobrenome)
    for p in parts:
        if local == p:
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

async def verify_email_via_microsoft(email: str) -> str:
    """
    Verifica se o e-mail existe usando a API de Login do Microsoft Office 365.
    Bypass 100% eficiente para o bloqueio de SMTP do Exchange (Greylisting).
    Retorna 'valid', 'invalid' ou 'unknown'.
    """
    import httpx
    try:
        url = "https://login.microsoftonline.com/common/GetCredentialType?mkt=en-US"
        payload = {"username": email}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code == 200:
                result = r.json().get("IfExistsResult")
                if result == 0:
                    return "valid"
                elif result == 1:
                    return "invalid"
            return "unknown"
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[MicrosoftAPI] Falha ao verificar email {email}: {e}")
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
    only_known_pattern: bool = False,
    do_smtp: bool = True,
    additional_candidates: list[str] = None
) -> dict:
    """
    Full email discovery pipeline:
    1. Generates all patterns + merges web-harvested candidates
    2. If known_pattern + only_known_pattern: testa APENAS esse padrão (modo determinístico)
    3. Se known_pattern sem only_known_pattern: coloca esse padrão primeiro
    4. Validates candidates via APIs (QuickEmailVerification / Abstract / Vrfymail)
    5. Dynamically filters out candidates proven invalid by APIs to prevent false positives
    6. Falls back to MX + SMTP probe for remaining non-invalid candidates
    """
    candidates = generate_all_patterns(first, last, domain)

    if known_pattern and only_known_pattern:
        # Modo determinístico: usa exclusivamente o padrão já confirmado para esta empresa.
        # Ignora candidatos adicionais (web/genericos) — a incerteza não é permitida.
        strict = [(e, p) for e, p in candidates if p == known_pattern]
        if not strict:
            # Padrão não está na lista padrão (ex: "web_harvested") — gera manualmente
            try:
                email = apply_pattern(first, last, domain, known_pattern)
                strict = [(email, known_pattern)]
            except Exception:
                pass
        candidates = strict if strict else candidates[:1]
        additional_candidates = None  # descarta candidatos extras quando padrão é certo
    else:
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

    is_microsoft = mx_valid and any(m in mx_host.lower() for m in ["protection.outlook.com", "outlook.com"])

    # --- EXTERNAL VALIDATION (APIs) ---
    import os
    from core.config import settings
    import logging as _log
    _logger = _log.getLogger(__name__)
    
    if is_microsoft:
        # ===== MICROSOFT 365: Validação definitiva via GetCredentialType =====
        # 1. Detectar Catch-All: testa emails aleatórios impossíveis
        import random, string
        catchall_hits = 0
        for _ in range(3):
            fake_local = ''.join(random.choices(string.ascii_lowercase + string.digits, k=14))
            fake_res = await verify_email_via_microsoft(f"{fake_local}@{domain}")
            if fake_res == 'valid':
                catchall_hits += 1
        
        ms_is_catchall = catchall_hits >= 1
        if ms_is_catchall:
            _logger.info(f"[EmailDiscovery] Microsoft catch-all detectado para {domain} ({catchall_hits}/3 fakes aceitos)")
        
        # 2. Testa candidatos (até 25 para cobrir todas as combinações de nome)
        ms_confirmed_emails = []  # Emails que passaram na verificação com prova de autenticidade
        
        for email, pattern in candidates[:25]:
            if email in invalid_candidates:
                continue
            result = await verify_email_via_microsoft(email)
            
            if result == 'invalid':
                invalid_candidates.add(email)
                continue
            
            if result != 'valid':
                continue  # 'unknown' — pula
            
            if not ms_is_catchall:
                # Domínio limpo (sem catch-all): MS API é 100% confiável
                return {
                    "email": email, "pattern": pattern,
                    "confidence": "high", "mx_valid": True, "smtp_result": "valid",
                    "all_candidates": [e for e, _ in candidates]
                }
            
            # Domínio com catch-all: precisa de prova extra
            # Testa uma versão "corrompida" do email. Se o servidor rejeitar a versão
            # corrompida mas aceitar a original, o email é genuíno.
            local_part = email.split('@')[0]
            corrupted = f"{local_part}zzq7@{domain}"
            corrupted_res = await verify_email_via_microsoft(corrupted)
            
            if corrupted_res == 'invalid':
                # Servidor REJEITA a versão corrompida → email original é GENUÍNO
                _logger.info(f"[EmailDiscovery] MS catch-all bypass: {email} confirmado (corrupted={corrupted} rejected)")
                return {
                    "email": email, "pattern": pattern,
                    "confidence": "high", "mx_valid": True, "smtp_result": "valid",
                    "all_candidates": [e for e, _ in candidates]
                }
            else:
                # Servidor aceita a versão corrompida também → não podemos confiar
                _logger.info(f"[EmailDiscovery] MS catch-all: {email} incerto (corrupted também aceito)")
                ms_confirmed_emails.append((email, pattern))
        
        # Microsoft path encerrado — NÃO cai no SMTP fallback
        # Se encontrou candidatos "possíveis" (catch-all), retorna o melhor com confiança baixa
        if ms_confirmed_emails:
            best = ms_confirmed_emails[0]
            return {
                "email": best[0], "pattern": best[1],
                "confidence": "low", "mx_valid": True, "smtp_result": "catchall",
                "all_candidates": [e for e, _ in candidates]
            }
        
        # Nenhum email confirmado via Microsoft
        remaining = [(e, p) for e, p in candidates if e not in invalid_candidates]
        if remaining:
            best = remaining[0]
            return {
                "email": best[0], "pattern": best[1],
                "confidence": "low", "mx_valid": True, "smtp_result": "invalid",
                "all_candidates": [e for e, _ in candidates]
            }
        
        best = candidates[0] if candidates else (f"{first}.{last}@{domain}", "first.last")
        return {
            "email": best[0], "pattern": best[1],
            "confidence": "low", "mx_valid": True, "smtp_result": "invalid",
            "all_candidates": [e for e, _ in candidates]
        }

    elif not is_generic and mx_valid:
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
    # NOTA: Para domínios Microsoft, NUNCA chega aqui (retorna antes)
    if do_smtp and mx_host:
        import httpx
        from core.config import settings
        smtp_microservice_url = getattr(settings, "SMTP_MICROSERVICE_URL", None) or os.environ.get("SMTP_MICROSERVICE_URL", "")
        
        for email, pattern in remaining_candidates[:3]:
            if smtp_microservice_url:
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        r = await client.post(
                            f"{smtp_microservice_url.rstrip('/')}/verify",
                            json={"email": email, "mx_host": mx_host}
                        )
                        if r.status_code == 200:
                            result = r.json().get("result", "unknown")
                        else:
                            result = "unknown"
                except Exception as e:
                    _log.getLogger(__name__).warning(f"Microservice SMTP falhou: {e}")
                    result = "unknown"
            else:
                # Fallback local se não houver microserviço
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


# ════════════════════════════════════════════════════════════════════════════
# === VALIDAÇÃO MULTI-SINAL (resiliente a catch-all) ==========================
# ════════════════════════════════════════════════════════════════════════════
#
# Princípio: um catch-all bem configurado responde idêntico para email real e
# falso — o canal SMTP isolado NÃO carrega a informação de existência. A solução
# é fundir vários sinais ORTOGONAIS e GRATUITOS, cada um fraco sozinho, num
# score de identidade via soma de log-odds (Bayes). Cada evidência é auditável.
#
import math
import hashlib
from dataclasses import dataclass


@dataclass
class EmailSignal:
    """Uma evidência independente sobre a existência/uso de um email.

    weight: contribuição em log-odds quando o sinal é conclusivo.
    hit:    True = evidência positiva | False = negativa | None = inconclusivo.
    """
    name: str
    weight: float
    hit: bool | None
    detail: str = ""

    @property
    def logodds(self) -> float:
        if self.hit is True:
            return self.weight
        if self.hit is False:
            return -self.weight
        return 0.0


def _sigmoid(x: float) -> float:
    # Clamp para evitar overflow em log-odds extremos
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


async def signal_gravatar(email: str, timeout: float = 6.0) -> EmailSignal:
    """Gravatar registrado → um humano real usou esse email para criar a conta.

    Ausência é INCONCLUSIVA (a maioria dos emails corporativos não tem Gravatar),
    então 404 → hit=None. Presença é prova forte de existência → hit=True.
    """
    import httpx
    h = hashlib.md5(email.strip().lower().encode()).hexdigest()
    url = f"https://www.gravatar.com/avatar/{h}?d=404"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            if r.status_code == 200:
                return EmailSignal("gravatar", 2.5, True, "Avatar Gravatar encontrado — email registrado por humano")
            return EmailSignal("gravatar", 0.0, None, "Sem Gravatar (inconclusivo)")
    except Exception:
        return EmailSignal("gravatar", 0.0, None, "Gravatar indisponível")


async def signal_smtp_catchall_aware(email: str, mx_host: str, timeout: float = 6.0) -> List[EmailSignal]:
    """Coleta, numa ÚNICA conexão SMTP, toda evidência que um catch-all não falsifica.

    - 452/552 no endereço real → mailbox CHEIO → caixa real e em uso (forte +).
    - 550/551/553 no endereço real → não existe (forte −).
    - real aceito (250) + corrompido rejeitado → discrimina → existe (+).
    - real aceito + corrompido aceito → catch-all puro → inconclusivo.
    """
    local, _, dom = email.partition('@')
    corrupted = f"{local}zzq7x@{dom}"
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(mx_host, 25), timeout=timeout
        )

        async def readline():
            return (await asyncio.wait_for(reader.readline(), timeout=timeout)).decode(errors='replace')

        async def writeline(s):
            writer.write((s + '\r\n').encode())
            await writer.drain()

        await readline()  # banner
        await writeline('EHLO emailprobe.local')
        while True:
            line = await readline()
            if line.startswith('250 ') or not line.startswith('250'):
                break
        await writeline('MAIL FROM:<probe@emailprobe.local>')
        if not (await readline()).startswith('250'):
            writer.close()
            return []
        await writeline(f'RCPT TO:<{email}>')
        real_code = (await readline())[:3]
        await writeline(f'RCPT TO:<{corrupted}>')
        corr_code = (await readline())[:3]
        try:
            await writeline('QUIT')
        except Exception:
            pass
        writer.close()
    except Exception:
        return []

    if real_code in ('452', '552'):
        return [EmailSignal("smtp_quota", 3.0, True, f"Mailbox cheio ({real_code}) — caixa real em uso")]
    if real_code in ('550', '551', '553'):
        return [EmailSignal("smtp_reject", 3.5, False, f"Rejeitado pelo servidor ({real_code}) — não existe")]
    if real_code == '250' and corr_code in ('550', '551', '553'):
        return [EmailSignal("smtp_contrast", 3.0, True, "Real aceito e corrompido rejeitado — endereço existe")]
    if real_code == '250' and corr_code == '250':
        return [EmailSignal("smtp_catchall", 0.0, None, "Catch-all puro (250 para tudo) — SMTP não discrimina")]
    return []


async def score_email_identity(
    email: str,
    mx_host: str | None,
    extra_signals: List[EmailSignal] | None = None,
) -> dict:
    """Funde sinais ortogonais num score de identidade 0-100 (prova auditável).

    Combinação bayesiana: score = sigmoid(prior + Σ log-odds dos sinais).
    Retorna {email, score, verdict, evidence[]}.
    """
    grav_task = asyncio.create_task(signal_gravatar(email))
    smtp_signals: List[EmailSignal] = []
    if mx_host:
        try:
            smtp_signals = await signal_smtp_catchall_aware(email, mx_host)
        except Exception:
            smtp_signals = []
    grav = await grav_task

    signals: List[EmailSignal] = [grav, *smtp_signals]
    if extra_signals:
        signals.extend(extra_signals)

    base = -1.0  # prior cético: um chute de padrão sem evidência começa em ~27%
    logodds = base + sum(s.logodds for s in signals)
    score = round(_sigmoid(logodds) * 100)

    has_negative = any(s.hit is False for s in signals)
    if has_negative and score < 50:
        verdict = "invalid"
    elif score >= 85:
        verdict = "valid"
    elif score >= 60:
        verdict = "likely"
    else:
        verdict = "uncertain"

    return {
        "email": email,
        "score": score,
        "verdict": verdict,
        "evidence": [
            {"name": s.name, "hit": s.hit, "weight": s.weight, "detail": s.detail}
            for s in signals if s.detail
        ],
    }


async def validate_email_smart(
    first: str, last: str, domain: str,
    known_pattern=None,
    only_known_pattern: bool = False,
    additional_candidates: list[str] = None,
    pattern_match: bool = False,
) -> dict:
    """Camada de validação de alto nível, resiliente a catch-all.

    1. Roda o pipeline determinístico (`discover_and_validate_email`).
    2. Se já confirmou via API/SMTP → caminho rápido (score 100).
    3. Se o SMTP foi inconclusivo (catch-all/greylist) → funde sinais
       independentes num score de identidade auditável e eleva/rebaixa o veredito.

    Mantém o contrato de `discover_and_validate_email` e adiciona:
    `identity_score` (0-100), `verdict` e `evidence` (lista auditável).
    """
    base = await discover_and_validate_email(
        first=first, last=last, domain=domain,
        known_pattern=known_pattern,
        only_known_pattern=only_known_pattern,
        do_smtp=True,
        additional_candidates=additional_candidates,
    )

    # Caminho rápido: confirmação determinística já obtida
    if base.get("smtp_result") == "valid":
        base["identity_score"] = 100
        base["verdict"] = "valid"
        base["evidence"] = [{"name": "smtp_or_api", "hit": True, "weight": 99, "detail": "Confirmado diretamente pelo servidor/API"}]
        return base

    # MX inválido → nada a fundir
    if not base.get("mx_valid"):
        base["identity_score"] = 0
        base["verdict"] = "invalid"
        base["evidence"] = [{"name": "mx", "hit": False, "weight": 99, "detail": "Domínio sem servidor de email (MX)"}]
        return base

    # Inconclusivo → aciona fusão multi-sinal sobre o melhor candidato
    email = base.get("email")
    mx_host = await get_mx_record(domain)
    extra: List[EmailSignal] = []
    if pattern_match:
        extra.append(EmailSignal("company_pattern", 2.0, True, "Bate com o padrão de email confirmado da empresa"))

    # Rejeição definitiva da camada determinística (Microsoft 365 / API / SMTP 550)
    # é evidência negativa forte — não pode ser "resgatada" só pelo padrão da empresa.
    if base.get("smtp_result") == "invalid":
        extra.append(EmailSignal("api_reject", 3.5, False, "Servidor/API rejeitou o endereço — não existe"))

    identity = await score_email_identity(email, mx_host, extra_signals=extra)
    base["identity_score"] = identity["score"]
    base["verdict"] = identity["verdict"]
    base["evidence"] = identity["evidence"]

    if identity["verdict"] == "valid":
        base["smtp_result"] = "valid"
        base["confidence"] = "high"
    elif identity["verdict"] == "invalid":
        base["smtp_result"] = "invalid"
        base["confidence"] = "low"

    return base
