"""
Rate limiter do Agente: trackers de RPM/TPM/RPD, persistência de estado, helpers de espera.
"""
from __future__ import annotations
import time as _time
import json as _json
import os as _os
from collections import deque

# Modelos Groq que suportam tool calling — testados e confirmados em 2026-05-07
_GROQ_TOOL_MODELS = [
    "llama-3.3-70b-versatile",                    # 70B — melhor qualidade
    "meta-llama/llama-4-scout-17b-16e-instruct",   # Llama 4 Scout — alta performance
    "qwen/qwen3-32b",                              # Qwen 3 — excelente p/ coding/logic
    "llama-3.1-8b-instant",                        # 8B — rápido e estável
]

# Cache de rate limit por modelo (compartilhado entre iterações do mesmo processo)
# Mapeia "provider:model" → timestamp até quando está bloqueado

_RATE_STATE_FILE = _os.path.join(_os.path.dirname(__file__), ".rate_state.json")
_agent_rate_limited_until: dict[str, float] = {}


def _load_rate_state() -> None:
    """Carrega estado de rate limit persistido — evita bater no limite logo após restart."""
    try:
        if not _os.path.exists(_RATE_STATE_FILE):
            return
        with open(_RATE_STATE_FILE, "r") as f:
            data = _json.load(f)
        now = _time.monotonic()
        wall_now = _time.time()
        saved_wall = data.get("saved_at", wall_now)
        elapsed = wall_now - saved_wall  # segundos desde o último save

        # Restaura RPM tracker: converte wall clock → monotônico corretamente
        rpm = data.get("rpm_tracker", {})
        for model, timestamps in rpm.items():
            # Filtra entradas com menos de 60s e converte para tempo monotônico atual
            adjusted = [now - (wall_now - t) for t in timestamps if wall_now - t < 60]
            if adjusted:
                _rpm_tracker[model] = deque(adjusted)

        # Restaura TPM tracker
        tpm = data.get("tpm_tracker", {})
        for model, entries in tpm.items():
            adjusted = [(now - (wall_now - t), tokens) for t, tokens in entries if wall_now - t < 60]
            if adjusted:
                _tpm_tracker[model] = deque(adjusted)

        # Restaura cooldowns individuais
        cooldowns = data.get("cooldowns", {})
        for key, until_wall in cooldowns.items():
            remaining = until_wall - wall_now
            if remaining > 0:
                _agent_rate_limited_until[key] = now + remaining

        # Restaura RPD (somente se for o mesmo dia UTC)
        from datetime import datetime, timezone
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if data.get("rpd_date") == today_utc:
            _rpd_tracker.update(data.get("rpd_tracker", {}))
    except Exception:
        pass


def _save_rate_state() -> None:
    """Persiste estado de rate limit para sobreviver a restarts."""
    try:
        from datetime import datetime, timezone
        now = _time.monotonic()
        wall_now = _time.time()
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        rpm = {}
        for model, dq in _rpm_tracker.items():
            valid = [t for t in dq if now - t < 60]
            if valid:
                rpm[model] = [wall_now - (now - t) for t in valid]

        tpm = {}
        for model, dq in _tpm_tracker.items():
            valid = [(t, tokens) for t, tokens in dq if now - t < 60]
            if valid:
                tpm[model] = [(wall_now - (now - t), tokens) for t, tokens in valid]

        cooldowns = {}
        for key, until_mono in _agent_rate_limited_until.items():
            remaining = until_mono - now
            if remaining > 0:
                cooldowns[key] = wall_now + remaining

        with open(_RATE_STATE_FILE, "w") as f:
            _json.dump({
                "saved_at": wall_now,
                "rpm_tracker": rpm,
                "tpm_tracker": tpm,
                "cooldowns": cooldowns,
                "rpd_tracker": _rpd_tracker,
                "rpd_date": today_utc,
            }, f)
    except Exception:
        pass

# ── Limites de contexto por modelo (tokens) ──────────────────────────────────
_MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # Groq
    "llama-3.3-70b-versatile":                   131_072,
    "llama-3.1-8b-instant":                      131_072,
    "meta-llama/llama-4-scout-17b-16e-instruct": 131_072,
    "qwen/qwen3-32b":                            131_072,
    "llama-3.2-11b-vision-preview":              131_072,
    # Claude
    "claude-3-5-sonnet-latest":                  200_000,
    "claude-3-5-haiku-latest":                   200_000,
    # Cerebras
    "llama3.1-8b":                               8_192,
    "llama-3.3-70b":                             8_192,
    # SambaNova
    "Meta-Llama-3.3-70B-Instruct":               128_000,
    "Llama-4-Scout-17B-16E-Instruct":            128_000,
    # DeepSeek
    "deepseek-chat":                             64_000,
    # Gemini
    "gemini-2.5-pro":                            1_048_576,
    "gemini-2.5-flash":                          1_048_576,
    "gemini-2.5-flash-lite":                     1_048_576,
    "gemini-2.0-flash":                          1_048_576,
    "gemini-2.0-flash-lite":                     1_048_576,
    # Gemini 3.x — adicione o ID de API aqui quando disponível (implementação já compatível)
    # Ollama (local — sem limite real)
    "qwen2.5:14b":                               128_000,
    "llama3.2":                                  128_000,
    "llama3":                                    8_192,
}

# ── RPM, TPM e RPD por modelo (todos os providers) ───────────────────────────
# RPD = Requests Per Day (resets à meia-noite UTC)
# None = sem limite conhecido / ilimitado

_MODEL_LIMITS: dict[str, dict] = {
    # ── Groq free tier ───────────────────────────────────────────────────────
    # Fonte: console.groq.com/docs/rate-limits
    "llama-3.3-70b-versatile": {
        "rpm": 30, "tpm": 12_000, "rpd": 1_000, "tpd": 100_000,
    },
    "llama-3.1-8b-instant": {
        "rpm": 30, "tpm": 6_000, "rpd": 14_400, "tpd": 500_000,
    },
    "meta-llama/llama-4-scout-17b-16e-instruct": {
        "rpm": 30, "tpm": 30_000, "rpd": 1_000, "tpd": 500_000,
    },
    "qwen/qwen3-32b": {
        "rpm": 60, "tpm": 6_000, "rpd": 1_000, "tpd": 500_000,
    },
    "llama-3.2-11b-vision-preview": {
        "rpm": 30, "tpm": 7_000, "rpd": 7_000, "tpd": 500_000,
    },
    # ── Claude (Anthropic API — tier 1) ──────────────────────────────────────
    # Fonte: platform.claude.com/docs/en/api/rate-limits
    # ITPM = input tokens/min | OTPM = output tokens/min | sem RPD
    "claude-3-5-sonnet-latest": {
        "rpm": 50, "tpm": 38_000, "rpd": None,   # 30k ITPM + 8k OTPM
    },
    "claude-3-5-haiku-latest": {
        "rpm": 50, "tpm": 60_000, "rpd": None,   # 50k ITPM + 10k OTPM
    },
    # ── Cerebras free tier ────────────────────────────────────────────────────
    # Fonte: inference-docs.cerebras.ai/support/rate-limits
    # ATENÇÃO: llama-3.3-70b foi DEPRECIADO em fev/2026
    "llama3.1-8b": {
        "rpm": 30, "tpm": 60_000, "rpd": 14_400, "tpd": 1_000_000,
    },
    # ── SambaNova free tier ───────────────────────────────────────────────────
    # Fonte: docs.sambanova.ai/docs/en/models/rate-limits
    # ATENÇÃO: RPD free = apenas 20 req/dia — extremamente restrito
    "Meta-Llama-3.3-70B-Instruct": {
        "rpm": 20, "tpm": None, "rpd": 20, "tpd": 200_000,
    },
    "Llama-4-Scout-17B-16E-Instruct": {
        "rpm": 20, "tpm": None, "rpd": 20, "tpd": 200_000,
    },
    # ── DeepSeek ──────────────────────────────────────────────────────────────
    # Fonte: api-docs.deepseek.com/quick_start/rate_limit
    # Sem limites fixos — concorrência dinâmica baseada na carga do servidor
    # Retorna 429 quando servidor está sobrecarregado; sem RPM/TPM/RPD publicados
    "deepseek-chat": {
        "rpm": None, "tpm": None, "rpd": None,
    },
    # ── Gemini free tier ──────────────────────────────────────────────────────
    # Fonte: ai.google.dev/gemini-api/docs/rate-limits (maio 2026)
    "gemini-2.5-flash-lite": {
        "rpm": 15, "tpm": 1_000_000, "rpd": 1_000,
    },
    "gemini-2.5-flash": {
        "rpm": 10, "tpm": 1_000_000, "rpd": 250,
    },
    "gemini-2.5-pro": {
        "rpm": 5, "tpm": 1_000_000, "rpd": 100,
    },
    "gemini-2.0-flash": {
        "rpm": 15, "tpm": 1_000_000, "rpd": 1_500,
    },
    "gemini-2.0-flash-lite": {
        "rpm": 30, "tpm": 1_000_000, "rpd": 1_500,
    },
    # ── Ollama (local/Colab — sem limites) ────────────────────────────────────
    # (ausência no dict = sem limite aplicado)
}

# Helpers de acesso rápido (retrocompat)
def _get_rpm(model: str) -> int | None:
    return _MODEL_LIMITS.get(model, {}).get("rpm")

def _get_tpm(model: str) -> int | None:
    return _MODEL_LIMITS.get(model, {}).get("tpm")

def _get_rpd(model: str) -> int | None:
    return _MODEL_LIMITS.get(model, {}).get("rpd")

def _get_tpd(model: str) -> int | None:
    return _MODEL_LIMITS.get(model, {}).get("tpd")

# Trackers em memória
_rpm_tracker: dict[str, deque] = {}           # model → deque[timestamp]
_tpm_tracker: dict[str, deque] = {}           # model → deque[(timestamp, tokens)]
_rpd_tracker: dict[str, int]   = {}           # model → count (hoje UTC)
_rpd_date:    str               = ""           # data UTC atual — reset ao mudar

# Carrega estado persistido ao iniciar (sobrevive a restarts)
_load_rate_state()


def _count_tokens(messages: list, tools: list | None = None) -> int:
    """Conta tokens reais usando tiktoken (cl100k_base — compatível com Llama 3)."""
    import json
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        total = 0
        for msg in messages:
            content = msg.get("content") or ""
            if isinstance(content, list):
                text = " ".join(str(b.get("text") or b.get("content") or "") for b in content)
            else:
                text = str(content)
            total += len(enc.encode(text)) + 4  # +4 overhead por mensagem
        if tools:
            total += len(enc.encode(json.dumps(tools)))
        return total
    except Exception:
        # Fallback se tiktoken falhar
        total = sum(len(str(m.get("content") or "")) for m in messages)
        if tools:
            total += len(json.dumps(tools))
        return total // 4


def _rpd_today() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _check_rpd(model: str) -> tuple[bool, str]:
    """
    Verifica cota diária (RPD e TPD).
    Retorna (pode_prosseguir, motivo_bloqueio_ou_vazio).
    """
    global _rpd_date, _rpd_tracker
    today = _rpd_today()
    if _rpd_date != today:
        _rpd_tracker = {}
        _rpd_date = today

    rpd_limit = _get_rpd(model)
    if rpd_limit and _rpd_tracker.get(f"{model}:req", 0) >= rpd_limit:
        used = _rpd_tracker.get(f"{model}:req", 0)
        return False, f"RPD esgotado ({used}/{rpd_limit} req hoje)"

    tpd_limit = _get_tpd(model)
    if tpd_limit and _rpd_tracker.get(f"{model}:tok", 0) >= tpd_limit:
        used = _rpd_tracker.get(f"{model}:tok", 0)
        return False, f"TPD esgotado ({used:,}/{tpd_limit:,} tokens hoje)"

    return True, ""


def _rpd_used(model: str) -> dict:
    """Retorna uso diário: {req, tokens}."""
    return {
        "req": _rpd_tracker.get(f"{model}:req", 0),
        "tokens": _rpd_tracker.get(f"{model}:tok", 0),
    }


def _rpm_wait(model: str) -> float:
    limit = _get_rpm(model)
    if not limit:
        return 0.0
    now = _time.monotonic()
    dq = _rpm_tracker.setdefault(model, deque())
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= limit:
        return max(0.0, 60.0 - (now - dq[0]) + 0.1)
    return 0.0


def _tpm_wait(model: str, tokens_needed: int) -> float:
    limit = _get_tpm(model)
    if not limit:
        return 0.0
    now = _time.monotonic()
    dq = _tpm_tracker.setdefault(model, deque())
    while dq and now - dq[0][0] > 60:
        dq.popleft()
    tokens_used = sum(t for _, t in dq)
    if tokens_used + tokens_needed > limit:
        return max(0.0, 60.0 - (now - dq[0][0]) + 0.1) if dq else 0.0
    return 0.0


def _pre_call_check(
    model: str,
    estimated_tokens: int,
    pending_events: list | None,
    rl_key: str,
    provider: str | None = None,
) -> tuple[bool, float]:
    """
    Bypassed as requested — no longer limits locally or forces wait sleeps.
    """
    return True, 0.0


def _post_call_record(model: str, actual_tokens: int = 0) -> None:
    """Registra uma requisição bem-sucedida nos trackers (RPM, TPM, RPD)."""
    global _rpd_date, _rpd_tracker
    now = _time.monotonic()
    _rpm_tracker.setdefault(model, deque()).append(now)
    if actual_tokens > 0:
        _tpm_tracker.setdefault(model, deque()).append((now, actual_tokens))
    today = _rpd_today()
    if _rpd_date != today:
        _rpd_tracker = {}
        _rpd_date = today
    _rpd_tracker[model] = _rpd_tracker.get(model, 0) + 1
    _save_rate_state()


def _on_429(model: str, rl_key: str, retry_after: int) -> None:
    """Atualiza trackers quando recebe 429 — preenche RPM e persiste."""
    cooldown = retry_after or 60
    _agent_rate_limited_until[rl_key] = _time.monotonic() + cooldown
    rpm_limit = _get_rpm(model) or 15
    dq = _rpm_tracker.setdefault(model, deque())
    while len(dq) < rpm_limit:
        dq.appendleft(_time.monotonic())
    _save_rate_state()


# ── Chamada via router — mesmo fluxo do V1 ───────────────────────────────────
