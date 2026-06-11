"""
core.rate_limiter
=================
Rate limiter global baseado em IP (slowapi).

Uso nos endpoints:
    from core.rate_limiter import limiter
    from fastapi import Request

    @router.get("/endpoint")
    @limiter.limit("30/minute")
    async def meu_endpoint(request: Request):
        ...

Para limitar por tenant/token ao invés de IP, substitua `get_remote_address`
por uma função que leia o header de autenticação da request.
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
