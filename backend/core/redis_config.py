import os
import redis
from arq.connections import RedisSettings
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

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
