"""
LLM Quota & Rate Limit Manager
==============================
Tracks real-time usage and remaining capacities (0 to 100%) for all LLM providers
and models by combining local counts and dynamic HTTP header extraction.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Dict, Any, Optional

from core.observability.logging_config import get_logger
from core.llm.gemini_quota import get_quota_tracker

log = get_logger(__name__)

_QUOTAS_FILE = "all_quotas_state.json"


class LLMQuotaManager:
    _instance: Optional["LLMQuotaManager"] = None

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(_QUOTAS_FILE):
            try:
                with open(_QUOTAS_FILE, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except Exception:
                self._state = {}

    def _save(self) -> None:
        try:
            with open(_QUOTAS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            log.warning(f"Failed to save quotas file: {e}")

    @classmethod
    def instance(cls) -> "LLMQuotaManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def record_billing_error(self, provider: str, model: str) -> None:
        """Mark a provider/model as out of credits (remaining and pct set to 0.0)."""
        async with self._lock:
            prov_data = self._state.setdefault(provider, {})
            model_data = prov_data.setdefault(model, {
                "used": 1000,
                "limit": 1000,
                "remaining": 0,
                "pct": 0.0,
                "updated_at": 0.0
            })
            model_data["remaining"] = 0
            model_data["pct"] = 0.0
            model_data["tokens_remaining"] = 0
            model_data["tokens_pct"] = 0.0
            model_data["status"] = "no_credits"
            model_data["updated_at"] = time.time()
            self._save()

    async def update_quota_from_headers(
        self,
        provider: str,
        model: str,
        headers: dict | Any,
    ) -> None:
        """
        Extracts rate limit headers dynamically and updates the cota state.
        Supports Anthropic, Groq, SambaNova, DeepSeek, Cerebras, etc.
        """
        async with self._lock:
            # Normalize headers keys to lowercase
            headers_dict = {}
            if hasattr(headers, "items"):
                headers_dict = {k.lower(): v for k, v in headers.items()}
            elif isinstance(headers, dict):
                headers_dict = {k.lower(): v for k, v in headers.items()}
            else:
                return

            limit_req = None
            remain_req = None
            limit_tok = None
            remain_tok = None

            # Anthropic (Claude)
            if provider == "claude":
                limit_req = headers_dict.get("anthropic-ratelimit-requests-limit")
                remain_req = headers_dict.get("anthropic-ratelimit-requests-remaining")
                limit_tok = headers_dict.get("anthropic-ratelimit-tokens-limit")
                remain_tok = headers_dict.get("anthropic-ratelimit-tokens-remaining")

            # OpenAI-compatible (Groq, SambaNova, DeepSeek, Cerebras)
            else:
                limit_req = headers_dict.get("x-ratelimit-limit-requests")
                remain_req = headers_dict.get("x-ratelimit-remaining-requests")
                limit_tok = headers_dict.get("x-ratelimit-limit-tokens")
                remain_tok = headers_dict.get("x-ratelimit-remaining-tokens")

            # Fallback check for SambaNova/Cerebras variants if not found above
            if not limit_req:
                limit_req = headers_dict.get("x-ratelimit-requests-limit")
            if not remain_req:
                remain_req = headers_dict.get("x-ratelimit-requests-remaining")

            prov_data = self._state.setdefault(provider, {})
            model_data = prov_data.setdefault(model, {
                "used": 0,
                "limit": 0,
                "remaining": 0,
                "pct": 100.0,
                "tokens_limit": 0,
                "tokens_remaining": 0,
                "tokens_pct": 100.0,
                "updated_at": 0.0
            })

            updated = False
            if limit_req is not None and remain_req is not None:
                try:
                    lim = int(limit_req)
                    rem = int(remain_req)
                    model_data["limit"] = lim
                    model_data["remaining"] = rem
                    model_data["used"] = max(0, lim - rem)
                    model_data["pct"] = round((rem / lim) * 100, 1) if lim else 100.0
                    updated = True
                except (ValueError, TypeError):
                    pass

            if limit_tok is not None and remain_tok is not None:
                try:
                    lim_t = int(limit_tok)
                    rem_t = int(remain_tok)
                    model_data["tokens_limit"] = lim_t
                    model_data["tokens_remaining"] = rem_t
                    model_data["tokens_pct"] = round((rem_t / lim_t) * 100, 1) if lim_t else 100.0
                    updated = True
                except (ValueError, TypeError):
                    pass

            if updated:
                model_data["status"] = "healthy"
                model_data["updated_at"] = time.time()
                self._save()

    async def record_generic_request(self, provider: str, model: str) -> None:
        """Increment count locally for providers that don't return rate limit headers."""
        async with self._lock:
            prov_data = self._state.setdefault(provider, {})
            model_data = prov_data.setdefault(model, {
                "used": 0,
                "limit": 1000,  # Default safety limit if not configured
                "remaining": 1000,
                "pct": 100.0,
                "updated_at": 0.0
            })
            
            # Local simple counting increment
            model_data["used"] = model_data.get("used", 0) + 1
            lim = model_data.get("limit", 1000)
            model_data["remaining"] = max(0, lim - model_data["used"])
            model_data["pct"] = round((model_data["remaining"] / lim) * 100, 1) if lim else 0.0
            model_data["status"] = "healthy"
            model_data["updated_at"] = time.time()
            self._save()

    def get_summary(self) -> Dict[str, Any]:
        """Collects and unifies both local trackers and real-time header data."""
        # 1. Fetch Gemini quota summary
        gemini_tracker = get_quota_tracker()
        gemini_summary = gemini_tracker.summary()

        summary: Dict[str, Dict[str, Any]] = {
            "gemini": {},
            "groq": {},
            "claude": {},
            "sambanova": {},
            "deepseek": {},
            "cerebras": {},
            "ollama": {},
        }

        # Populate Gemini
        for m, d in gemini_summary.items():
            summary["gemini"][m] = {
                "limit": d["limit"],
                "remaining": d["remaining"],
                "used": d["used"],
                "pct": round(100.0 - d["pct"], 1),  # remaining percentage
                "status": "rate_limited" if d["exhausted"] else "healthy",
                "updated_at": time.time()
            }

        # Populate other providers from saved state
        for provider in ["groq", "claude", "sambanova", "deepseek", "cerebras", "ollama"]:
            prov_state = self._state.get(provider, {})
            
            # Map standard models if no api transactions occurred yet
            from core.config import settings
            models_list = []
            if provider == "groq":
                models_list = settings.ai_groq_models_list
            elif provider == "claude":
                models_list = settings.ai_claude_models_list
            elif provider == "sambanova":
                models_list = settings.ai_sambanova_models_list
            elif provider == "deepseek":
                models_list = settings.ai_deepseek_models_list
            elif provider == "cerebras":
                models_list = settings.ai_cerebras_models_list
            elif provider == "ollama":
                models_list = settings.ai_ollama_models_list

            for model in models_list:
                m_state = prov_state.get(model, {})
                
                # Check provider rate limit cooldown state in router
                from core.llm.router import _provider_rate_limited_until
                cooldown_until = _provider_rate_limited_until.get(provider, 0)
                
                status = m_state.get("status", "healthy")
                cooldown_remaining = 0
                if time.monotonic() < cooldown_until:
                    status = "rate_limited"
                    cooldown_remaining = max(0, int(cooldown_until - time.monotonic()))

                # Keep no_credits status if set and not in cooldown
                if m_state.get("status") == "no_credits" and status != "rate_limited":
                    status = "no_credits"

                # Ollama is local, has no limits (always 100% remaining)
                if provider == "ollama":
                    summary[provider][model] = {
                        "limit": 999999,
                        "remaining": 999999,
                        "used": 0,
                        "pct": 100.0,
                        "status": "healthy",
                        "cooldown_remaining": 0,
                        "updated_at": time.time()
                    }
                else:
                    pct = m_state.get("pct", 100.0) if status != "no_credits" else 0.0
                    remaining = m_state.get("remaining", 1000) if status != "no_credits" else 0
                    summary[provider][model] = {
                        "limit": m_state.get("limit", 1000),
                        "remaining": remaining,
                        "used": m_state.get("used", 0) if status != "no_credits" else m_state.get("limit", 1000),
                        "pct": pct, # percent of remaining
                        "tokens_limit": m_state.get("tokens_limit", 0),
                        "tokens_remaining": m_state.get("tokens_remaining", 0) if status != "no_credits" else 0,
                        "tokens_pct": m_state.get("tokens_pct", 100.0) if status != "no_credits" else 0.0,
                        "status": status,
                        "cooldown_remaining": cooldown_remaining,
                        "updated_at": m_state.get("updated_at", time.time())
                    }

        return summary


def get_quota_manager() -> LLMQuotaManager:
    return LLMQuotaManager.instance()
