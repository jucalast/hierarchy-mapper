"""
core.cache
==========
Cache leve de dois níveis (L1 = memória, L2 = Redis opcional).

Uso típico:
    from core.cache import async_ttl_cache, cache_key_for

    @async_ttl_cache(ttl_sec=600, max_entries=512)
    async def classify_intent(message: str) -> dict:
        ...

Ou manual:
    from core.cache import get_cache
    cache = get_cache("ai.responses")
    value = cache.get(key)
    if value is None:
        value = await compute()
        cache.set(key, value)
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

from core.logging_config import get_logger

log = get_logger(__name__)

T = TypeVar("T")


# =============================================================================
# TTLCache em memória (usa cachetools quando disponível; fallback stdlib)
# =============================================================================

try:
    from cachetools import TTLCache  # type: ignore
    _HAS_CACHETOOLS = True
except ImportError:  # pragma: no cover
    _HAS_CACHETOOLS = False


@dataclass
class _StdlibTTLCache:
    """Fallback mínimo (thread/async-safe) quando cachetools não está disponível."""
    max_entries: int = 1024
    ttl_sec: int = 600
    _store: Dict[str, tuple[float, Any]] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        item = self._store.get(key)
        if item is None:
            return default
        expires_at, value = item
        if time.time() >= expires_at:
            self._store.pop(key, None)
            return default
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self.max_entries:
            # Evict mais velho
            try:
                oldest = min(self._store.items(), key=lambda kv: kv[1][0])
                self._store.pop(oldest[0], None)
            except ValueError:
                pass
        self._store[key] = (time.time() + self.ttl_sec, value)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


class MemoryCache:
    """Wrapper uniforme sobre TTLCache (cachetools) ou fallback."""

    def __init__(self, name: str, ttl_sec: int, max_entries: int):
        self.name = name
        self.ttl_sec = ttl_sec
        self.max_entries = max_entries
        if _HAS_CACHETOOLS:
            self._impl = TTLCache(maxsize=max_entries, ttl=ttl_sec)
        else:
            self._impl = _StdlibTTLCache(max_entries=max_entries, ttl_sec=ttl_sec)
        self.hits = 0
        self.misses = 0

    def get(self, key: str, default: Any = None) -> Any:
        try:
            value = self._impl.get(key, default) if hasattr(self._impl, "get") else self._impl[key]
        except KeyError:
            value = default
        if value is default:
            self.misses += 1
        else:
            self.hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        try:
            self._impl[key] = value
        except TypeError:
            # Fallback sem __setitem__
            self._impl.set(key, value)

    def clear(self) -> None:
        if hasattr(self._impl, "clear"):
            self._impl.clear()

    def stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        return {
            "name": self.name,
            "size": len(self._impl),
            "max_entries": self.max_entries,
            "ttl_sec": self.ttl_sec,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": round(self.hits / total, 3) if total else 0.0,
        }


_caches: Dict[str, MemoryCache] = {}


def get_cache(name: str, *, ttl_sec: int = 600, max_entries: int = 1024) -> MemoryCache:
    c = _caches.get(name)
    if c is None:
        c = MemoryCache(name=name, ttl_sec=ttl_sec, max_entries=max_entries)
        _caches[name] = c
    return c


def all_caches_stats() -> list[Dict[str, Any]]:
    return [c.stats() for c in _caches.values()]


# =============================================================================
# Key hashing helper
# =============================================================================

def cache_key_for(*parts: Any) -> str:
    """Gera chave estável a partir de partes arbitrárias (serializa em JSON)."""
    blob = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# =============================================================================
# Decorator de cache para funções async
# =============================================================================

def async_ttl_cache(
    ttl_sec: int = 600,
    max_entries: int = 512,
    key_builder: Optional[Callable[..., str]] = None,
    cache_name: Optional[str] = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Cache TTL para coroutines. Colapsa chamadas concorrentes para a mesma key."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        name = cache_name or f"{func.__module__}.{func.__qualname__}"
        cache = get_cache(name, ttl_sec=ttl_sec, max_entries=max_entries)
        inflight: Dict[str, asyncio.Future[Any]] = {}

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            if key_builder:
                key = key_builder(*args, **kwargs)
            else:
                key = cache_key_for(args, sorted(kwargs.items()))

            cached = cache.get(key, None)
            if cached is not None:
                return cached  # type: ignore[return-value]

            # Colapsa chamadas concorrentes para a mesma chave
            existing = inflight.get(key)
            if existing is not None:
                return await existing

            loop = asyncio.get_running_loop()
            fut: asyncio.Future[Any] = loop.create_future()
            inflight[key] = fut
            try:
                result = await func(*args, **kwargs)
                cache.set(key, result)
                fut.set_result(result)
                return result
            except Exception as e:
                fut.set_exception(e)
                raise
            finally:
                inflight.pop(key, None)

        return wrapper

    return decorator
