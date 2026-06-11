"""
Caller LLM do Agente: _call_with_tools com suporte a Claude, Groq, Gemini, Cerebras,
SambaNova, DeepSeek e Ollama com fallback automático e rate limiting.
"""
from __future__ import annotations
import asyncio
import json
import uuid
import time

from modules.agent.service.llm.adapters import (
    _tools_to_openai, _messages_to_openai, _response_from_openai,
    _tools_to_gemini, _messages_to_gemini, _response_from_gemini,
    _messages_to_ollama_native,
)
from modules.agent.service.llm.rate_limiter import (
    _GROQ_TOOL_MODELS, _MODEL_CONTEXT_LIMITS, _MODEL_LIMITS,
    _agent_rate_limited_until, _rpm_tracker, _tpm_tracker, _rpd_tracker, _rpd_date,
    _count_tokens, _pre_call_check, _post_call_record, _on_429, _save_rate_state,
    _get_rpm, _get_tpm, _get_rpd, _get_tpd,
)
from core.observability.logging_config import get_logger

log = get_logger(__name__)

async def _call_with_tools(
    system: str,
    messages: list,
    tools: list,
    preferred: str | None = None,
    strict_mode: bool | None = None,
    pending_events: list | None = None,
    force_tool_call: bool = False,        # se True, usa mode=ANY no Gemini
    allowed_tool_names: list | None = None,  # restringe quais tools o Gemini pode chamar
) -> dict:
    """
    Usa get_router().chain() exatamente como o V1 usa ask_llm:
    - Respeita preferência de modelo via get_preferred_model()
    - Respeita strict_mode via get_strict_mode_preference()
    - Usa a mesma ordem de providers e fallbacks da v1
    - Ordena modelos dentro de cada provider com o preferido primeiro
    Suporta Claude (Anthropic nativo) e Groq (OpenAI-compat) com tools.
    """
    import time
    from core.config import settings
    from core.infra.http_client import get_http_client
    from core.llm.router import get_router, get_preferred_model, get_strict_mode_preference

    router = get_router()
    preferred = preferred or get_preferred_model()
    # Só aplica preferência global quando strict_mode não foi explicitamente passado (None)
    if strict_mode is None:
        strict_mode = get_strict_mode_preference()
    else:
        strict_mode = bool(strict_mode)

    if strict_mode and preferred:
        target_provider = None
        if preferred in router._providers:
            target_provider = preferred
        elif preferred in (settings.ai_gemini_models_list or []):
            target_provider = "gemini"
        elif preferred in (settings.ai_groq_models_list or []):
            target_provider = "groq"
        elif preferred in (settings.ai_claude_models_list or []):
            target_provider = "claude"
        elif preferred in (settings.ai_sambanova_models_list or []):
            target_provider = "sambanova"
        elif preferred in (settings.ai_deepseek_models_list or []):
            target_provider = "deepseek"
        elif preferred in (settings.ai_cerebras_models_list or []):
            target_provider = "cerebras"

        if strict_mode and target_provider and target_provider in router._providers:
            # strict_mode: APENAS o provider preferido — sem fallback para outros providers.
            # Fallback interno entre modelos do mesmo provider continua permitido.
            providers = [router._providers[target_provider]]
        else:
            # Sem strict: cadeia completa começando pelo preferido
            providers = router.chain(preferred=preferred)
    else:
        providers = router.chain(preferred=preferred)

    # Estima tokens gerais para ordenação adaptativa de provedores se não for strict_mode
    if not strict_mode:
        from core.llm.router import _estimate_tokens
        from core.llm.base import LLMMessage
        general_msgs = [LLMMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in messages if isinstance(m, dict)]
        general_est_tokens = _estimate_tokens(general_msgs)

        base_prov_names = [p.name for p in providers]
        if general_est_tokens < 15_000:
            # Menos tokens -> Prioriza provedores com modelos pequenos, rápidos e leves
            lightweight = ["gemini", "groq", "cerebras"]
            sorted_prov_names = [p for p in lightweight if p in base_prov_names] + [p for p in base_prov_names if p not in lightweight]
            providers = [router._providers[name] for name in sorted_prov_names if name in router._providers]
        elif general_est_tokens > 100_000:
            # Mais de 100k tokens -> Prioriza provedores com contextos massivos
            heavyweight = ["gemini", "claude", "sambanova"]
            sorted_prov_names = [p for p in heavyweight if p in base_prov_names] + [p for p in base_prov_names if p not in heavyweight]
            providers = [router._providers[name] for name in sorted_prov_names if name in router._providers]

    client = get_http_client()
    last_err = "nenhum provider disponível"
    
    log.info("agent.llm.chain", providers=[p.name for p in providers], preferred=preferred, strict_mode=strict_mode)

    for provider in providers:
        if not provider.available:
            continue

        # Skip rápido se o provider foi rate-limitado recentemente no router
        from core.llm.router import _provider_rate_limited_until
        cooldown_until = _provider_rate_limited_until.get(provider.name, 0)
        if time.monotonic() < cooldown_until:
            # Se for o provider preferido ou se estivermos em strict_mode, NÃO pula!
            is_preferred = False
            if preferred:
                if preferred == provider.name:
                    is_preferred = True
                elif provider.name == "gemini" and "gemini" in preferred:
                    is_preferred = True
                elif provider.name == "groq" and preferred in (settings.ai_groq_models_list or []):
                    is_preferred = True
                elif provider.name == "claude" and preferred in (settings.ai_claude_models_list or []):
                    is_preferred = True
                elif provider.name in ("sambanova", "deepseek", "cerebras", "ollama") and preferred in (settings.ai_sambanova_models_list or settings.ai_deepseek_models_list or settings.ai_cerebras_models_list or settings.ai_ollama_models_list or []):
                    is_preferred = True

            if not strict_mode and not is_preferred:
                remaining = round(cooldown_until - time.monotonic())
                log.info("agent.llm.provider.skipped_cooldown", provider=provider.name, remaining_sec=remaining)
                continue

        # ── Claude ────────────────────────────────────────────────────────
        if provider.name == "claude":
            key = settings.ANTHROPIC_API_KEY
            if not key:
                continue
            # Seleção de modelos inteligente com ordenação adaptativa de tamanho
            all_models = settings.ai_claude_models_list or ["claude-sonnet-4-5", "claude-3-5-haiku-latest"]
            
            headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                       "content-type": "application/json"}
            _claude_msgs_for_count = [{"role": "system", "content": system}] + \
                                     [{"role": m.get("role","user"), "content": str(m.get("content",""))}
                                      for m in messages if isinstance(m, dict)]
            estimated_tokens = _count_tokens(_claude_msgs_for_count, tools)

            from core.llm.router import get_model_size, get_model_context_limit
            
            valid_models = []
            for m in all_models:
                ctx_limit = get_model_context_limit(m)
                if estimated_tokens > ctx_limit:
                    log.warning("agent.claude.context_limit_skipped", model=m, estimated=estimated_tokens, limit=ctx_limit)
                    continue
                valid_models.append(m)
                
            if not valid_models:
                valid_models = all_models

            def _claude_size_sort_key(m: str) -> int:
                sz = get_model_size(m)
                if estimated_tokens < 15_000:
                    return sz
                elif estimated_tokens < 100_000:
                    if sz == 2: return 0
                    if sz == 1: return 1
                    return 2
                else:
                    return -sz

            if preferred and preferred in valid_models:
                other_models = [m for m in valid_models if m != preferred]
                other_models.sort(key=_claude_size_sort_key)
                models = [preferred] + other_models
            else:
                valid_models.sort(key=_claude_size_sort_key)
                models = valid_models

            for model in models:
                _rl_key = f"claude:{model}"

                ctx_limit = _MODEL_CONTEXT_LIMITS.get(model)
                if ctx_limit and estimated_tokens > ctx_limit:
                    last_err = f"{model} contexto muito grande ({estimated_tokens} > {ctx_limit})"
                    if pending_events is not None:
                        pending_events.append({"type": "context_overflow", "provider": "claude", "model": model,
                                               "estimated_tokens": estimated_tokens, "limit": ctx_limit})
                    continue

                can_go, wait = _pre_call_check(model, estimated_tokens, pending_events, _rl_key, provider="claude")
                if not can_go:
                    last_err = f"rate_limit {model} (RPD esgotado)"
                    continue
                if wait > 0:
                    import asyncio
                    await asyncio.sleep(wait)

                max_retries = 3 if strict_mode else 1
                for attempt in range(1, max_retries + 1):
                    try:
                        resp = await client.post(
                            "https://api.anthropic.com/v1/messages",
                            json={"model": model, "max_tokens": 4096, "temperature": 0.1,
                                  "system": system, "messages": messages, "tools": tools},
                            headers=headers, timeout=120.0 if strict_mode else 20.0,
                        )
                    except Exception as e:
                        last_err = str(e)
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(2 * attempt)
                            continue
                        break

                    if resp.status_code == 200:
                        _agent_rate_limited_until.pop(_rl_key, None)
                        data = resp.json()
                        real_tokens = (data.get("usage") or {}).get("input_tokens", 0) + \
                                      (data.get("usage") or {}).get("output_tokens", 0)
                        _post_call_record(model, real_tokens)
                        if pending_events is not None:
                            pending_events.append({"type": "model_active", "provider": "claude", "model": model})
                        data["_successful_provider"] = "claude"
                        data["_successful_model"] = model
                        return data

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("retry-after", 0) or 0)
                        _on_429(model, _rl_key, retry_after)
                        last_err = f"rate_limit {model}"
                        if attempt < max_retries:
                            import asyncio
                            _wait = min(retry_after or 15, 15)
                            log.warning("agent.llm.retry_wait", provider="claude", model=model,
                                        wait_sec=_wait, attempt=attempt)
                            if pending_events is not None:
                                pending_events.append({"type": "rate_wait", "provider": "claude", "model": model, "wait_sec": _wait, "reason": "RPM"})
                            await asyncio.sleep(_wait)
                            continue
                        break

                    if resp.status_code in (401, 402, 403):
                        last_err = f"claude sem crédito/chave (HTTP {resp.status_code})"
                        break

                    last_err = f"claude HTTP {resp.status_code}"
                    break

                if strict_mode and "rate_limit" in last_err:
                    break

            # Se todos os modelos falharam para Claude, coloca o provedor em cooldown
            from core.llm.router import _provider_rate_limited_until
            _provider_rate_limited_until["claude"] = time.monotonic() + 300.0  # 5 min cooldown
            log.warning("agent.llm.provider.cooldown_triggered", provider="claude", reason=f"all_models_failed (last: {last_err})")

        # ── Groq ──────────────────────────────────────────────────────────
        elif provider.name == "groq":
            key = settings.GROQ_API_KEY
            if not key:
                continue
            # _GROQ_TOOL_MODELS define a ordem — modelos testados e confirmados.
            # settings pode adicionar extras, mas os testados ficam primeiro.
            extra = [m for m in (settings.ai_groq_models_list or []) if m not in _GROQ_TOOL_MODELS]
            all_models = list(_GROQ_TOOL_MODELS) + extra
            
            oai_tools = _tools_to_openai(tools)
            oai_msgs = [{"role": "system", "content": system}] + _messages_to_openai(messages)
            headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}

            # Nomes de provider ("groq", "gemini", "claude") não são modelos —
            # quando preferred é um nome de provider, usa todos os modelos desse provider.
            _provider_names = set(router._providers.keys())  # groq, gemini, claude, sambanova, deepseek, cerebras
            preferred_is_provider_name = preferred in _provider_names

            estimated_tokens = _count_tokens(oai_msgs, oai_tools)

            # Seleção de modelos inteligente com ordenação adaptativa de tamanho
            from core.llm.router import get_model_size, get_model_context_limit
            
            valid_models = []
            for m in all_models:
                ctx_limit = get_model_context_limit(m)
                if estimated_tokens > ctx_limit:
                    log.warning("agent.groq.context_limit_skipped", model=m, estimated=estimated_tokens, limit=ctx_limit)
                    continue
                valid_models.append(m)
                
            if not valid_models:
                valid_models = all_models

            def _groq_size_sort_key(m: str) -> int:
                sz = get_model_size(m)
                # Tool calling complexo: preferir modelos médios/grandes mesmo para contextos pequenos.
                # O 8b (sz=1) é reservado como último recurso — muito fraco para seguir instruções multi-etapa.
                if estimated_tokens < 15_000:
                    if sz == 2: return 0   # Scout/Qwen 32B — melhor custo/benefício
                    if sz == 3: return 1   # 70B — qualidade máxima
                    return 2               # 8b — último recurso
                elif estimated_tokens < 100_000:
                    if sz == 2: return 0
                    if sz == 3: return 1
                    return 2
                else:
                    return -sz  # contexto grande: prefere modelos maiores

            if preferred and preferred in valid_models:
                other_models = [m for m in valid_models if m != preferred]
                other_models.sort(key=_groq_size_sort_key)
                all_models = [preferred] + other_models
            else:
                valid_models.sort(key=_groq_size_sort_key)
                all_models = valid_models

            for idx, model in enumerate(all_models):
                # Em strict_mode com modelo ESPECÍFICO, pula os outros modelos.
                if strict_mode and preferred and not preferred_is_provider_name and model != preferred:
                    continue

                # Verifica se o modelo suporta o tamanho do contexto
                ctx_limit = _MODEL_CONTEXT_LIMITS.get(model)
                if ctx_limit and estimated_tokens > ctx_limit:
                    log.warning("agent.llm.context_overflow",
                                model=model, estimated=estimated_tokens, limit=ctx_limit)
                    last_err = f"{model} contexto muito grande ({estimated_tokens} > {ctx_limit} tokens)"
                    if pending_events is not None:
                        pending_events.append({
                            "type": "context_overflow",
                            "provider": "groq",
                            "model": model,
                            "estimated_tokens": estimated_tokens,
                            "limit": ctx_limit,
                        })
                    continue

                _rl_key = f"groq:{model}"
                can_go, wait = _pre_call_check(model, estimated_tokens, pending_events, _rl_key, provider="groq")
                if not can_go:
                    last_err = f"rate_limit {model} (RPD esgotado)"
                    continue
                if wait > 0:
                    import asyncio
                    await asyncio.sleep(wait)

                is_last_model = (idx == len(all_models) - 1)
                max_retries = 3 if strict_mode else 1
                current_msgs = oai_msgs  # pode ser truncado em 413
                for attempt in range(1, max_retries + 1):
                    try:
                        resp = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            json={"model": model, "max_tokens": 4096, "temperature": 0.1,
                                  "messages": current_msgs, "tools": oai_tools, "tool_choice": "auto"},
                            headers=headers, timeout=120.0 if strict_mode else 20.0,
                        )
                    except Exception as e:
                        last_err = str(e)
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(5)
                            continue
                        break

                    if resp.status_code == 200:
                        _agent_rate_limited_until.pop(_rl_key, None)
                        data = resp.json()
                        real_tokens = (data.get("usage") or {}).get("total_tokens", 0)
                        _post_call_record(model, real_tokens)
                        if pending_events is not None:
                            pending_events.append({"type": "model_active", "provider": "groq", "model": model})
                        res = _response_from_openai(data)
                        res["_successful_provider"] = "groq"
                        res["_successful_model"] = model
                        return res

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("retry-after", 0) or 0)
                        _on_429(model, _rl_key, retry_after)
                        last_err = f"rate_limit {model}"
                        log.warning("agent.llm.rate_limit_rotate", model=model,
                                    retry_after_sec=retry_after, action="next_model")
                        if pending_events is not None:
                            pending_events.append({"type": "rate_wait", "provider": "groq", "model": model,
                                                   "wait_sec": 0, "reason": "RPM→próximo modelo"})
                        # Rotaciona para o próximo modelo imediatamente — não desperdica tempo re-tentando o mesmo
                        break

                    if resp.status_code == 413:
                        # Contexto muito grande — trunca e retenta uma vez
                        if len(current_msgs) > 4:
                            current_msgs = [current_msgs[0]] + current_msgs[-3:]
                            continue
                        last_err = f"groq 413: contexto muito grande para {model}"
                        break

                    if resp.status_code == 400:
                        body_lower = resp.text.lower()
                        if "decommissioned" in body_lower or "deprecated" in body_lower or "not found" in body_lower:
                            last_err = f"groq model decommissioned: {model}"
                            break
                    if resp.status_code in (500, 502, 503, 504):
                        last_err = f"groq HTTP {resp.status_code} (transitório)"
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(3 * attempt)
                            continue
                        break
                    last_err = f"groq HTTP {resp.status_code}: {resp.text[:100]}"
                    break

            # Se todos os modelos falharam para Groq, coloca o provedor em cooldown
            from core.llm.router import _provider_rate_limited_until
            _provider_rate_limited_until["groq"] = time.monotonic() + 300.0  # 5 min cooldown
            log.warning("agent.llm.provider.cooldown_triggered", provider="groq", reason=f"all_models_failed (last: {last_err})")

        # ── Gemini ────────────────────────────────────────────────────────
        elif provider.name == "gemini":
            key = settings.GEMINI_API_KEY
            if not key:
                continue
            
            _DEPRECATED_GEMINI = {"gemini-flash-latest", "gemini-1.5-flash", "gemini-2.0-flash-exp", "gemini-2.0-pro-exp"}
            _DEFAULT_GEMINI = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
            all_models = [m for m in (settings.ai_gemini_models_list or []) if m not in _DEPRECATED_GEMINI] or _DEFAULT_GEMINI
            gemini_tools = _tools_to_gemini(tools)
            gemini_msgs = _messages_to_gemini(messages)
            
            _gemini_msgs_for_count = [{"role": "system", "content": system}] + \
                                      [{"role": "user", "content": str(m.get("parts", [{}])[0].get("text", "")
                                                                       if isinstance(m, dict) else "")}
                                       for m in gemini_msgs]
            estimated_tokens_gemini = _count_tokens(_gemini_msgs_for_count)

            # Seleção de modelos inteligente com ordenação adaptativa de tamanho
            from core.llm.router import get_model_size, get_model_context_limit
            
            valid_models = []
            for m in all_models:
                ctx_limit = get_model_context_limit(m)
                if estimated_tokens_gemini > ctx_limit:
                    log.warning("agent.gemini.context_limit_skipped", model=m, estimated=estimated_tokens_gemini, limit=ctx_limit)
                    continue
                valid_models.append(m)
                
            if not valid_models:
                valid_models = all_models

            def _gemini_size_sort_key(m: str) -> int:
                sz = get_model_size(m)
                if estimated_tokens_gemini < 15_000:
                    return sz
                elif estimated_tokens_gemini < 100_000:
                    if sz == 2: return 0
                    if sz == 1: return 1
                    return 2
                else:
                    return -sz

            if preferred and preferred in valid_models:
                other_models = [m for m in valid_models if m != preferred]
                other_models.sort(key=_gemini_size_sort_key)
                models = [preferred] + other_models
            else:
                valid_models.sort(key=_gemini_size_sort_key)
                models = valid_models

            gemini_allowed_names = None
            if force_tool_call and allowed_tool_names:
                _avail = {t["name"] for t in tools}
                gemini_allowed_names = [n for n in allowed_tool_names if n in _avail]
                if not gemini_allowed_names:
                    gemini_allowed_names = None

            payload = {
                "contents": gemini_msgs,
                "systemInstruction": {"parts": [{"text": system}]},
                "tools": gemini_tools,
                "toolConfig": {
                    "functionCallingConfig": {
                        # ANY = obriga chamada de ferramenta; AUTO = modelo decide
                        "mode": "ANY" if force_tool_call else "AUTO",
                        # Restringe às ferramentas de investigação enquanto contexto incompleto
                        # Modelo escolhe qual usar livremente — só não pode chamar ações prematuras
                        **({"allowedFunctionNames": gemini_allowed_names}
                           if gemini_allowed_names else {}),
                    },
                },
                "generationConfig": {
                    "temperature": 0.1,
                },
            }

            for model in models:
                _rl_key = f"gemini:{model}"

                can_go, wait = _pre_call_check(model, estimated_tokens_gemini, pending_events, _rl_key, provider="gemini")
                if not can_go:
                    last_err = f"rate_limit {model} (RPD esgotado)"
                    continue
                if wait > 0:
                    import asyncio
                    await asyncio.sleep(wait)

                max_retries = 3 if strict_mode else 1
                for attempt in range(1, max_retries + 1):
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                    try:
                        resp = await client.post(url, json=payload, timeout=120.0 if strict_mode else 20.0)
                    except Exception as e:
                        last_err = str(e)
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(2 * attempt)
                            continue
                        break

                    if resp.status_code == 200:
                        _agent_rate_limited_until.pop(_rl_key, None)
                        data = resp.json()
                        usage = data.get("usageMetadata") or {}
                        real_tokens = usage.get("totalTokenCount", 0)
                        _post_call_record(model, real_tokens)
                        if pending_events is not None:
                            pending_events.append({"type": "model_active", "provider": "gemini", "model": model})
                        res = _response_from_gemini(data)
                        res["_successful_provider"] = "gemini"
                        res["_successful_model"] = model
                        return res

                    if resp.status_code == 429:
                        last_err = f"rate_limit {model}"
                        body_text = resp.text[:500].lower() if hasattr(resp, "text") else ""
                        is_daily_quota = "daily" in body_text or "daily limit" in body_text
                        if is_daily_quota:
                            log.warning("agent.llm.quota_exhausted", provider="gemini", model=model)
                            _agent_rate_limited_until[_rl_key] = _time.monotonic() + 3600
                            # Marca RPD como esgotado
                            rpd_limit = _get_rpd(model) or 1500
                            global _rpd_date, _rpd_tracker
                            _rpd_tracker[model] = rpd_limit
                            _save_rate_state()
                            break
                        retry_after = int(resp.headers.get("retry-after", 0) or 0)
                        _on_429(model, _rl_key, retry_after)
                        if attempt < max_retries:
                            import asyncio
                            _wait = min(retry_after or 10, 15)
                            log.warning("agent.llm.retry_wait", provider="gemini", model=model,
                                        wait_sec=_wait, attempt=attempt)
                            if pending_events is not None:
                                pending_events.append({"type": "rate_wait", "provider": "gemini", "model": model, "wait_sec": _wait, "reason": "RPM"})
                            await asyncio.sleep(_wait)
                            continue
                        break

                    if resp.status_code in (500, 502, 503, 504):
                        last_err = f"gemini HTTP {resp.status_code} (transitório)"
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(2 * attempt)
                            continue
                        break
                    last_err = f"gemini HTTP {resp.status_code}: {resp.text[:100]}"
                    break

                if strict_mode and "rate_limit" in last_err:
                    break

            # Se todos os modelos falharam para Gemini, coloca o provedor em cooldown
            from core.llm.router import _provider_rate_limited_until
            _provider_rate_limited_until["gemini"] = time.monotonic() + 300.0  # 5 min cooldown
            log.warning("agent.llm.provider.cooldown_triggered", provider="gemini", reason=f"all_models_failed (last: {last_err})")

        # ── Providers OpenAI-compat extras (SambaNova, DeepSeek, Cerebras) ──────
        elif provider.name in ("sambanova", "deepseek", "cerebras", "ollama"):
            _prov_cfg = {
                "sambanova": {
                    "key_fn": lambda: settings.SAMBANOVA_API_KEY,
                    "url": "https://api.sambanova.ai/v1/chat/completions",
                    "models_fn": lambda: settings.ai_sambanova_models_list,
                },
                "deepseek": {
                    "key_fn": lambda: settings.DEEPSEEK_API_KEY,
                    "url": "https://api.deepseek.com/v1/chat/completions",
                    "models_fn": lambda: settings.ai_deepseek_models_list,
                },
                "cerebras": {
                    "key_fn": lambda: settings.CEREBRAS_API_KEY,
                    "url": "https://api.cerebras.ai/v1/chat/completions",
                    "models_fn": lambda: settings.ai_cerebras_models_list,
                },
                "ollama": {
                    "key_fn": lambda: "ollama",
                    "url": "http://localhost:11434/api/chat",
                    "models_fn": lambda: settings.ai_ollama_models_list,
                    "timeout": 300.0,
                    "native": True,  # usa API nativa Ollama (não OpenAI-compat)
                },
            }[provider.name]

            prov_key = _prov_cfg["key_fn"]()
            if not prov_key:
                continue

            prov_headers = {"Authorization": f"Bearer {prov_key}", "content-type": "application/json"}
            prov_msgs = [{"role": "system", "content": system}] + _messages_to_openai(messages)
            oai_tools_prov = _tools_to_openai(tools)
            estimated_tokens_prov = _count_tokens(prov_msgs, oai_tools_prov)

            prov_models = _prov_cfg["models_fn"]() or []
            
            # Seleção de modelos inteligente com ordenação adaptativa de tamanho
            from core.llm.router import get_model_size, get_model_context_limit
            
            valid_models = []
            for m in prov_models:
                ctx_limit = get_model_context_limit(m)
                if estimated_tokens_prov > ctx_limit:
                    log.warning(f"agent.{provider.name}.context_limit_skipped", model=m, estimated=estimated_tokens_prov, limit=ctx_limit)
                    continue
                valid_models.append(m)
                
            if not valid_models:
                valid_models = prov_models

            def _prov_size_sort_key(m: str) -> int:
                sz = get_model_size(m)
                if estimated_tokens_prov < 15_000:
                    return sz
                elif estimated_tokens_prov < 100_000:
                    if sz == 2: return 0
                    if sz == 1: return 1
                    return 2
                else:
                    return -sz

            if preferred and preferred in valid_models:
                other_models = [m for m in valid_models if m != preferred]
                other_models.sort(key=_prov_size_sort_key)
                prov_models = [preferred] + other_models
            else:
                valid_models.sort(key=_prov_size_sort_key)
                prov_models = valid_models

            for idx_p, model in enumerate(prov_models):
                _rl_key_p = f"{provider.name}:{model}"

                # Pula modelos que estão atualmente em cooldown de rate-limit (429) para evitar retentativas inúteis, exceto no strict_mode
                if not strict_mode and time.monotonic() < _agent_rate_limited_until.get(_rl_key_p, 0.0):
                    log.info("agent.llm.model_cooldown_skipped", provider=provider.name, model=model)
                    continue

                ctx_limit = _MODEL_CONTEXT_LIMITS.get(model)
                if ctx_limit and estimated_tokens_prov > ctx_limit:
                    last_err = f"{model} contexto muito grande ({estimated_tokens_prov} > {ctx_limit})"
                    if pending_events is not None:
                        pending_events.append({"type": "context_overflow", "provider": provider.name, "model": model,
                                               "estimated_tokens": estimated_tokens_prov, "limit": ctx_limit})
                    continue

                can_go, wait = _pre_call_check(model, estimated_tokens_prov, pending_events, _rl_key_p, provider=provider.name)
                if not can_go:
                    last_err = f"rate_limit {model} (RPD esgotado)"
                    continue
                if wait > 0:
                    import asyncio
                    await asyncio.sleep(wait)

                is_last = (idx_p == len(prov_models) - 1)
                cur_msgs = prov_msgs
                max_retries = 3 if strict_mode else 1
                is_ollama_native = _prov_cfg.get("native", False)
                ollama_msgs = _messages_to_ollama_native(system, messages) if is_ollama_native else None
                for attempt in range(1, max_retries + 1):
                    try:
                        if is_ollama_native:
                            # Ollama native API — usa /api/chat com options.num_gpu=0 (forçar CPU)
                            ollama_tools = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("input_schema", {})}} for t in tools]
                            req_payload: dict = {"model": model, "messages": ollama_msgs, "stream": False,
                                                 "options": {"num_gpu": 0, "temperature": 0.1}}
                            if ollama_tools:
                                req_payload["tools"] = ollama_tools
                            resp = await client.post(
                                _prov_cfg["url"],
                                json=req_payload,
                                timeout=120.0 if strict_mode else (60.0 if provider.name == "ollama" else 20.0),
                            )
                        else:
                            req_payload = {
                                "model": model,
                                "max_tokens": 4096,
                                "temperature": 0.1,
                                "messages": cur_msgs,
                                "tools": oai_tools_prov,
                                "tool_choice": "auto"
                            }
                            req_headers = dict(prov_headers)
                            if provider.name == "cerebras":
                                if "max_completion_tokens" not in req_payload and "max_tokens" not in req_payload:
                                    req_payload["max_completion_tokens"] = 4096
                                if "gpt-oss-120b" in model:
                                    req_payload["reasoning_effort"] = "high" if strict_mode else "medium"
                                elif "zai-glm-4.7" in model:
                                    req_payload["clear_thinking"] = True
                                if "service_tier" not in req_payload:
                                    req_payload["service_tier"] = "auto"
                                req_headers["queue_threshold"] = "15000"
                                req_headers["Cerebras-Queue-Threshold"] = "15000"

                            resp = await client.post(
                                _prov_cfg["url"],
                                json=req_payload,
                                headers=req_headers,
                                timeout=120.0 if strict_mode else 20.0,
                            )
                    except Exception as e:
                        last_err = str(e)
                        if attempt < max_retries:
                            import asyncio
                            await asyncio.sleep(2 * attempt)
                            continue
                        break

                    if resp.status_code == 200:
                        _agent_rate_limited_until.pop(_rl_key_p, None)
                        data = resp.json()
                        if pending_events is not None:
                            pending_events.append({"type": "model_active", "provider": provider.name, "model": model})
                        if is_ollama_native:
                            # Converte resposta nativa Ollama para formato interno
                            msg = data.get("message", {})
                            tcs = msg.get("tool_calls") or []
                            oai_tcs = []
                            for tc in tcs:
                                fn = tc.get("function", {})
                                args = fn.get("arguments", {})
                                oai_tcs.append({"id": f"call_{uuid.uuid4().hex[:8]}", "type": "function",
                                                "function": {"name": fn.get("name", ""),
                                                             "arguments": json.dumps(args) if isinstance(args, dict) else args}})
                            openai_fmt = {"choices": [{"message": {"content": msg.get("content"), "tool_calls": oai_tcs},
                                                       "finish_reason": "tool_calls" if oai_tcs else "stop"}]}
                            real_tokens = data.get("eval_count", 0) + data.get("prompt_eval_count", 0)
                            _post_call_record(model, real_tokens)
                            res = _response_from_openai(openai_fmt)
                            res["_successful_provider"] = provider.name
                            res["_successful_model"] = model
                            return res
                        real_tokens = (data.get("usage") or {}).get("total_tokens", 0)
                        _post_call_record(model, real_tokens)
                        res = _response_from_openai(data)
                        res["_successful_provider"] = provider.name
                        res["_successful_model"] = model
                        return res

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("retry-after", 0) or 0)
                        _on_429(model, _rl_key_p, retry_after)
                        last_err = f"rate_limit {model}"
                        log.warning("agent.llm.429_rotate", provider=provider.name, model=model)
                        break  # Rotaciona imediatamente para próximo modelo

                    if resp.status_code in (401, 402, 403):
                        last_err = f"{provider.name} sem crédito/chave (HTTP {resp.status_code})"
                        break

                    if resp.status_code == 413:
                        if len(cur_msgs) > 4:
                            cur_msgs = [cur_msgs[0]] + cur_msgs[-3:]
                            continue
                        last_err = f"{provider.name} 413: contexto muito grande para {model}"
                        break

                    if resp.status_code in (500, 502, 503, 504):
                        last_err = f"{provider.name} HTTP {resp.status_code} (transitório)"
                        if attempt < max_retries - 1:
                            import asyncio
                            await asyncio.sleep(3)
                            continue
                        break

                    last_err = f"{provider.name} HTTP {resp.status_code}: {resp.text[:100]}"
                    break

            # Se todos os modelos falharam para este provedor extra, coloca-o em cooldown
            from core.llm.router import _provider_rate_limited_until
            _provider_rate_limited_until[provider.name] = time.monotonic() + 300.0  # 5 min cooldown
            log.warning("agent.llm.provider.cooldown_triggered", provider=provider.name, reason="all_models_failed")

    raise RuntimeError(f"Todos os providers falharam: {last_err}")


# ── Thinking pós-decisão — gerado DEPOIS de saber qual ferramenta será chamada ─

_TOOL_THINKING_SYSTEM = """Você é o Agente de Investigação Comercial LinkB2B narrando sua investigação em voz alta.

Você receberá:
- OBJETIVO: o que o usuário perguntou
- ENCONTRADO ATÉ AGORA: resumo do que cada ferramenta já retornou (esta é a única fonte de dados reais!)
- PRÓXIMA AÇÃO: qual ferramenta vai ser usada agora

Escreva 2-4 frases que demonstrem RACIOCÍNIO INVESTIGATIVO real:

1. Referencie o objetivo do usuário com a empresa específica.
2. Conecte o que foi encontrado: compare dados de fontes diferentes, note inconsistências, destaque o que é relevante para o objetivo.
3. Se cabível, questione discrepâncias entre o Pipedrive e as mensagens.
4. Explique por que a próxima ferramenta é a escolha certa AGORA — baseado nos dados reais, não em ordem genérica.

EXEMPLOS DE RACIOCÍNIO ESPERADO (USE APENAS COMO REFERÊNCIA DE ESTILO, NUNCA COPIE OS NOMES OU DADOS DOS EXEMPLOS):
- "legal, o Pipedrive tem 2 atividades pendentes — uma delas menciona que o cliente enviou proposta em fevereiro. Isso é interessante porque ainda não confirmei se houve resposta, então vou verificar o e-mail do contato principal para cruzar com a tarefa."
- "curioso: o deal está aberto mas sem valor e sem funil definido. Ainda não temos contatos cadastrados no CRM, então vou buscar as mensagens do WhatsApp da empresa para entender se o negócio avançou além do Pipedrive."
- "encontrei 6 e-mails sobre homologação de embalagens com o contato, mas nenhuma mensagem no WhatsApp. Isso confirma que a comunicação foi por e-mail. Vou agora verificar se há outras pessoas envolvidas no histórico."

REGRAS ABSOLUTAS:
- NUNCA use nomes, datas ou dados dos exemplos (como "Wesley Pinheiro", "Pedro", "Bottcher", "15 de março") se eles não estiverem explicitamente listados nos dados REAIS da seção "ENCONTRADO ATÉ AGORA" do caso atual.
- Se não houver contatos ou nomes de pessoas nos dados reais (ENCONTRADO ATÉ AGORA), NUNCA invente nomes de pessoas ou contatos. Refira-se apenas à empresa ou diga que não há contatos cadastrados.
- A instrução de "citar nomes reais" aplica-se APENAS se os nomes reais estiverem presentes nos dados fornecidos na seção "ENCONTRADO ATÉ AGORA". Caso contrário, não use nenhum nome próprio de contato.
- Termine com ponto final.
- Não sugira ações comerciais."""

