"""
core.infra.redis_config
=======================
Cliente Redis sincrono para cache de imagens e settings ARQ para o worker.

O redis_client e sincrono intencionalmente -- chamadas async usam
asyncio.to_thread() nos routers para nao bloquear o event loop.
Se a conexao falhar, redis_client e None e o cache de imagens fica desabilitado.

Exportacoes: redis_client (redis.Redis | None), redis_settings (arq.RedisSettings)
"""
import redis
from arq.connections import RedisSettings

from core.config import settings
from core.observability.logging_config import get_logger

log = get_logger(__name__)

REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT
REDIS_PASSWORD = settings.REDIS_PASSWORD

redis_settings = RedisSettings(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD
)

# Redis Client simples para caching (síncrono — usado via asyncio.to_thread nos routers)
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_keepalive=True
    )
    redis_client.ping()
    log.info("redis.connected", host=REDIS_HOST, port=REDIS_PORT)
except Exception as e:
    log.warning("redis.connection_failed", error=str(e), detail="Cache de imagens desativado")
    redis_client = None
# Force restart for arq worker
