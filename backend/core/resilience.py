"""
core.resilience
===============
Primitivos de resiliência reutilizáveis:

- CircuitBreaker: abre/fecha circuito com cooldown exponencial por provedor.
- async_retry: decorator para retry com backoff exponencial + jitter, sem
  precisar do pacote tenacity (mas também funciona junto, se disponível).
- Bulkhead: semáforo nomeado global para limitar concorrência por integração.

Filosofia:
- Cada integração externa tem SEU OWN circuit breaker (chave por nome).
- Retry retorna controle rápido em erros não-retryáveis (4xx não-429).
- Logs estruturados em todas as transições de estado.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Type, TypeVar

from core.config import settings
from core.logging_config import get_logger

log = get_logger(__name__)

T = TypeVar("T")


# =============================================================================
# Circuit Breaker
# =============================================================================

class CircuitOpenError(RuntimeError):
    """Erro levantado quando um circuito está aberto (curto-circuito)."""
    def __init__(self, name: str, remaining_sec: float):
        super().__init__(f"Circuit '{name}' open for {remaining_sec:.0f}s more.")
        self.name = name
        self.remaining_sec = remaining_sec


@dataclass
class CircuitBreaker:
    """
    Circuit breaker simples com cooldown exponencial.

    Estados:
        closed:     chamadas passam normalmente.
        open:       chamadas são curto-circuitadas até `open_until`.
        half_open:  (implícito quando `time.time() >= open_until`) — próxima
                    chamada testa o serviço; se passar, reseta; se falhar,
                    volta a open com cooldown maior.
    """

    name: str
    cooldown_base_sec: int = 15  # Reduzido de 60 para 15 para recuperação mais rápida
    cooldown_max_sec: int = 120  # Reduzido de 300 para 120
    max_consecutive_failures: int = 8  # Aumentado de 5 para 8 para ser mais tolerante

    consecutive_failures: int = 0
    open_until: float = 0.0

    @property
    def is_open(self) -> bool:
        if self.open_until == 0:
            return False
        if time.time() >= self.open_until:
            # Cooldown expirou — volta a half-open (permite uma tentativa)
            self.open_until = 0.0
            return False
        return True

    def remaining_cooldown(self) -> float:
        return max(0.0, self.open_until - time.time())

    def ensure_available(self) -> None:
        if self.is_open:
            remaining = self.remaining_cooldown()
            log.debug("circuit.open.skip", name=self.name, remaining_sec=int(remaining))
            raise CircuitOpenError(self.name, remaining)

    def record_success(self) -> None:
        if self.consecutive_failures > 0:
            log.info("circuit.recovered", name=self.name,
                     prior_failures=self.consecutive_failures)
        self.consecutive_failures = 0
        self.open_until = 0.0

    def record_failure(self, reason: str = "unknown") -> float:
        self.consecutive_failures += 1
        
        # Só abre o circuito se atingir o limite de falhas consecutivas
        if self.consecutive_failures < self.max_consecutive_failures:
            log.info("circuit.failure_registered", name=self.name, 
                     count=self.consecutive_failures, limit=self.max_consecutive_failures)
            return 0.0

        cooldown = min(
            self.cooldown_base_sec * (self.consecutive_failures - self.max_consecutive_failures + 1),
            self.cooldown_max_sec,
        )
        self.open_until = time.time() + cooldown
        log.warning(
            "circuit.open",
            name=self.name,
            cooldown_sec=cooldown,
            consecutive_failures=self.consecutive_failures,
            reason=reason,
        )
        return cooldown

    def reset(self) -> None:
        self.consecutive_failures = 0
        self.open_until = 0.0


# Registry global de circuit breakers por nome
_breakers: Dict[str, CircuitBreaker] = {}


def get_breaker(
    name: str,
    *,
    cooldown_base_sec: Optional[int] = None,
    cooldown_max_sec: Optional[int] = None,
) -> CircuitBreaker:
    b = _breakers.get(name)
    if b is None:
        b = CircuitBreaker(
            name=name,
            cooldown_base_sec=cooldown_base_sec or settings.ai.cooldown_base_sec,
            cooldown_max_sec=cooldown_max_sec or settings.ai.cooldown_max_sec,
            max_consecutive_failures=settings.ai.max_consecutive_failures_before_reset,
        )
        _breakers[name] = b
    return b


def all_breakers() -> Dict[str, CircuitBreaker]:
    return dict(_breakers)


# =============================================================================
# Retry com backoff exponencial + jitter (stdlib puro)
# =============================================================================

async def async_retry(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    attempts: int = 3,
    base_delay_sec: float = 0.5,
    max_delay_sec: float = 15.0,
    jitter: float = 0.25,
    retry_on: Iterable[Type[BaseException]] = (Exception,),
    give_up_on: Iterable[Type[BaseException]] = (),
    op_name: str = "op",
    **kwargs: Any,
) -> T:
    """
    Executa `func(*args, **kwargs)` com retry exponencial.

    - `retry_on`: exceções que disparam retry (default: todas).
    - `give_up_on`: exceções que fazem desistir imediatamente (tem prioridade).
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            return await func(*args, **kwargs)
        except tuple(give_up_on) as e:  # type: ignore[misc]
            log.debug("retry.give_up", op=op_name, error=type(e).__name__)
            raise
        except tuple(retry_on) as e:  # type: ignore[misc]
            last_exc = e
            if attempt >= attempts:
                break
            delay = min(base_delay_sec * (2 ** (attempt - 1)), max_delay_sec)
            delay += random.uniform(0, jitter * delay)
            log.warning(
                "retry.attempt_failed",
                op=op_name,
                attempt=attempt,
                max_attempts=attempts,
                delay_sec=round(delay, 2),
                error=type(e).__name__,
                message=str(e)[:150],
            )
            await asyncio.sleep(delay)

    assert last_exc is not None
    raise last_exc


# =============================================================================
# Bulkhead — limite de concorrência nomeado
# =============================================================================

_semaphores: Dict[str, asyncio.Semaphore] = {}
_sem_limits: Dict[str, int] = {}
_sem_lock = asyncio.Lock()


async def get_bulkhead(name: str, limit: int) -> asyncio.Semaphore:
    async with _sem_lock:
        existing = _semaphores.get(name)
        if existing is None or _sem_limits.get(name) != limit:
            _semaphores[name] = asyncio.Semaphore(limit)
            _sem_limits[name] = limit
        return _semaphores[name]


class Bulkhead:
    """Context manager conveniente: `async with Bulkhead("pipedrive", 10):`"""

    def __init__(self, name: str, limit: int):
        self.name = name
        self.limit = limit
        self._sem: Optional[asyncio.Semaphore] = None

    async def __aenter__(self) -> "Bulkhead":
        self._sem = await get_bulkhead(self.name, self.limit)
        await self._sem.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._sem is not None:
            self._sem.release()
