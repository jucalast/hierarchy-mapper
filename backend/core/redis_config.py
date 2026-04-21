import redis
from arq.connections import RedisSettings

from core.config import settings

REDIS_HOST = settings.REDIS_HOST
REDIS_PORT = settings.REDIS_PORT
REDIS_PASSWORD = settings.REDIS_PASSWORD

redis_settings = RedisSettings(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD
)

# Redis Client simples para caching
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=False,
        socket_connect_timeout=5,
        socket_keepalive=True
    )
    # Testa conexão
    redis_client.ping()
except Exception as e:
    print(f"Redis connection failed: {e}. Cache disabled.")
    redis_client = None
