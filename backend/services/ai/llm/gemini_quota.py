"""
Gemini Daily Quota Tracker — controla o uso diário de RPD por modelo.

Limites free tier (abril 2026):
  gemini-2.5-pro       → 100 RPD,  5 RPM
  gemini-2.5-flash     → 250 RPD, 10 RPM
  gemini-2.5-flash-lite → 1000 RPD, 15 RPM

Reset: meia-noite Pacific Time (UTC-7/UTC-8).

Cada chamada bem-sucedida ou com rate-limit 429 é contada.
Persiste em disco para sobreviver a reinicializações.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from core.logging_config import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Limites diários por modelo (free tier)
# ---------------------------------------------------------------------------
DAILY_LIMITS: Dict[str, Dict[str, int]] = {
    "gemini-2.5-pro":        {"rpd": 100,  "rpm": 5},
    "gemini-2.5-flash":      {"rpd": 250,  "rpm": 10},
    "gemini-2.5-flash-lite": {"rpd": 1000, "rpm": 15},
}

# Mapeamento tier → ordem de modelos para tentativa
# O primeiro é o ideal para o tier; os demais são fallbacks dentro do Gemini.
from services.ai.llm.base import LLMTier

TIER_MODEL_PRIORITY: Dict[str, list[str]] = {
    LLMTier.FAST:     ["gemini-2.5-flash-lite", "gemini-2.5-flash"],
    LLMTier.STANDARD: ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"],
    LLMTier.DEEP:     ["gemini-2.5-pro", "gemini-2.5-flash"],
}

_QUOTA_FILE = "gemini_quota_state.json"
_PACIFIC_OFFSET = timedelta(hours=-7)  # PDT (verão); -8 no inverno (não crítico)


def _pacific_day() -> str:
    """Retorna a data atual no fuso Pacific como string 'YYYY-MM-DD'."""
    now_pacific = datetime.now(timezone.utc) + _PACIFIC_OFFSET
    return now_pacific.strftime("%Y-%m-%d")


class GeminiQuotaTracker:
    """
    Rastreia uso diário de RPD por modelo Gemini.
    Thread-safe via asyncio.Lock.
    """
    _instance: Optional["GeminiQuotaTracker"] = None

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # { "YYYY-MM-DD": { model: count } }
        self._state: Dict[str, Dict[str, int]] = {}
        self._load()

    # ------------------------------------------------------------------ I/O
    def _load(self) -> None:
        if os.path.exists(_QUOTA_FILE):
            try:
                with open(_QUOTA_FILE, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except Exception:
                self._state = {}

    def _save(self) -> None:
        try:
            # Mantém apenas os últimos 2 dias para não acumular lixo
            today = _pacific_day()
            yesterday = (datetime.now(timezone.utc) + _PACIFIC_OFFSET - timedelta(days=1)).strftime("%Y-%m-%d")
            self._state = {k: v for k, v in self._state.items() if k in (today, yesterday)}
            with open(_QUOTA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
        except Exception:
            pass

    # ----------------------------------------------------------- Public API
    @classmethod
    def instance(cls) -> "GeminiQuotaTracker":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_usage(self, model: str) -> int:
        """Retorna quantas chamadas já foram feitas hoje para o modelo."""
        today = _pacific_day()
        return self._state.get(today, {}).get(model, 0)

    def get_limit(self, model: str) -> int:
        """Retorna o limite diário do modelo."""
        return DAILY_LIMITS.get(model, {}).get("rpd", 0)

    def get_remaining(self, model: str) -> int:
        """Retorna quantas chamadas ainda estão disponíveis hoje."""
        return max(0, self.get_limit(model) - self.get_usage(model))

    def is_exhausted(self, model: str) -> bool:
        """True se o modelo esgotou a cota diária."""
        limit = self.get_limit(model)
        if limit == 0:
            return False  # modelo desconhecido, sem limite definido
        return self.get_usage(model) >= limit

    def all_exhausted(self) -> bool:
        """True se TODOS os modelos conhecidos esgotaram a cota diária."""
        return all(self.is_exhausted(m) for m in DAILY_LIMITS)

    async def record(self, model: str) -> int:
        """
        Registra uma chamada para o modelo. Retorna o uso total após o registro.
        Salva em disco.
        """
        async with self._lock:
            today = _pacific_day()
            day_data = self._state.setdefault(today, {})
            day_data[model] = day_data.get(model, 0) + 1
            total = day_data[model]
            limit = self.get_limit(model)
            pct = round(total / limit * 100) if limit else 0
            log.info("gemini.quota.used",
                     model=model, used=total, limit=limit, pct=f"{pct}%",
                     remaining=max(0, limit - total))
            self._save()
            return total

    def summary(self) -> Dict[str, Dict]:
        """Retorna resumo de uso/limite/restante para todos os modelos."""
        return {
            model: {
                "used": self.get_usage(model),
                "limit": limits["rpd"],
                "remaining": self.get_remaining(model),
                "exhausted": self.is_exhausted(model),
                "pct": round(self.get_usage(model) / limits["rpd"] * 100, 1) if limits["rpd"] else 0,
            }
            for model, limits in DAILY_LIMITS.items()
        }

    def models_for_tier(self, tier: LLMTier, preferred_model: Optional[str] = None) -> list[str]:
        """
        Retorna a lista de modelos Gemini a tentar para o tier dado,
        filtrando os que já esgotaram a cota diária.
        Se preferred_model for especificado e for um modelo Gemini válido, coloca-o primeiro.
        """
        candidates = list(TIER_MODEL_PRIORITY.get(tier, TIER_MODEL_PRIORITY[LLMTier.STANDARD]))

        # Se pediu um modelo específico, coloca na frente
        if preferred_model and preferred_model in DAILY_LIMITS:
            if preferred_model not in candidates:
                candidates = [preferred_model] + candidates
            else:
                candidates = [preferred_model] + [m for m in candidates if m != preferred_model]

        # Ordena: disponíveis primeiro, esgotados por último (mas ainda incluídos como último recurso)
        available = [m for m in candidates if not self.is_exhausted(m)]
        exhausted = [m for m in candidates if self.is_exhausted(m)]

        if not available:
            log.warning("gemini.quota.all_tier_models_exhausted", tier=tier.value,
                        candidates=candidates)

        return available + exhausted  # tenta disponíveis primeiro, esgotados como fallback emergencial


def get_quota_tracker() -> GeminiQuotaTracker:
    return GeminiQuotaTracker.instance()
