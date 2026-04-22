"""
core.http_client
================
httpx.AsyncClient singleton compartilhado no app.

Benefícios:
- Connection pooling e keep-alive reais (reaproveita conexões TLS).
- HTTP/2 (multiplexação em uma única conexão TCP quando o servidor suporta).
- Timeouts e limites centralizados em `core.config`.
- Contexts específicos por integração via `get_client(name)` quando precisar
  de timeout/headers customizados (ex: Pipedrive, Gemini).

Uso:
    from core.http_client import get_http_client
    client = get_http_client()
    resp = await client.get(url)

Ciclo de vida:
    await init_http_client()    # chamar no startup
    await close_http_client()   # chamar no shutdown
"""
from __future__ import annotations

import asyncio
from typing import Dict, Optional

import httpx

from core.config import settings
from core.logging_config import get_logger

log = get_logger(__name__)

_lock = asyncio.Lock()
_clients: Dict[str, httpx.AsyncClient] = {}


def _build_client(
    *,
    timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    http2: Optional[bool] = None,
) -> httpx.AsyncClient:
    t = timeout if timeout is not None else settings.http.default_timeout
    limits = httpx.Limits(
        max_connections=settings.http.pool_max_connections,
        max_keepalive_connections=settings.http.pool_max_keepalive_connections,
        keepalive_expiry=settings.http.keepalive_expiry_sec,
    )
    default_headers = {"User-Agent": settings.http.user_agent}
    if headers:
        default_headers.update(headers)
    try:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(
                t,
                connect=settings.http.connect_timeout,
            ),
            limits=limits,
            http2=http2 if http2 is not None else settings.http.http2_enabled,
            headers=default_headers,
            follow_redirects=True,
        )
    except Exception:
        # Se http2 não disponível (falta h2 lib), cai para HTTP/1.1
        return httpx.AsyncClient(
            timeout=httpx.Timeout(t, connect=settings.http.connect_timeout),
            limits=limits,
            http2=False,
            headers=default_headers,
            follow_redirects=True,
        )


async def init_http_client() -> None:
    """Inicializa o client default. Idempotente."""
    async with _lock:
        if "default" not in _clients or _clients["default"].is_closed:
            _clients["default"] = _build_client()
            log.info("http.client.initialized", pool="default")


async def close_http_client() -> None:
    """Fecha todos os clients. Chamar no shutdown do app."""
    async with _lock:
        for name, client in list(_clients.items()):
            try:
                await client.aclose()
            except Exception as e:  # pragma: no cover
                log.warning("http.client.close_failed", name=name, error=str(e))
            _clients.pop(name, None)
        log.info("http.client.closed")


def get_http_client(name: str = "default") -> httpx.AsyncClient:
    """
    Retorna o client compartilhado. Se inexistente, cria sob demanda.

    Prefira chamar `init_http_client()` no startup para garantir a inicialização
    antes de qualquer request.
    """
    client = _clients.get(name)
    if client is None or client.is_closed:
        client = _build_client()
        _clients[name] = client
    return client


async def get_or_create_client(
    name: str,
    *,
    timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None,
    http2: Optional[bool] = None,
) -> httpx.AsyncClient:
    """Obtém/cria client com configuração específica (ex: timeout maior)."""
    async with _lock:
        existing = _clients.get(name)
        if existing and not existing.is_closed:
            return existing
        client = _build_client(timeout=timeout, headers=headers, http2=http2)
        _clients[name] = client
        return client
