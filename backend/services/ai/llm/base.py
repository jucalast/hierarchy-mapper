"""
Interfaces e tipos compartilhados do LLM Gateway.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class LLMTier(str, enum.Enum):
    """Classe de latência/complexidade da chamada."""
    FAST = "fast"          # classificação de intenção, respostas curtas
    STANDARD = "standard"  # resposta final com contexto
    DEEP = "deep"          # agent workflow, análises longas


@dataclass
class LLMMessage:
    """Mensagem neutra (independente do provider)."""
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResult:
    text: str
    json_data: Optional[Any] = None          # populado se json_mode=True
    provider: str = ""
    model: str = ""
    latency_sec: float = 0.0
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    raw: Optional[Dict[str, Any]] = field(default=None, repr=False)

    @property
    def is_json(self) -> bool:
        return self.json_data is not None


class LLMError(RuntimeError):
    """Erro genérico de provider LLM."""


class NoProviderAvailableError(LLMError):
    """Todos os providers falharam ou estão sem chave."""


@runtime_checkable
class LLMProvider(Protocol):
    """Contrato que cada provider deve implementar."""

    name: str

    @property
    def available(self) -> bool:  # pragma: no cover
        """True se o provider tem chave e circuito fechado."""
        ...

    async def complete(
        self,
        messages: List[LLMMessage],
        *,
        json_mode: bool = False,
        temperature: float = 0.1,
        timeout_sec: Optional[float] = None,
        tier: LLMTier = LLMTier.STANDARD,
    ) -> LLMResult:  # pragma: no cover
        """Executa a chamada. Lança LLMError em falhas."""
        ...
