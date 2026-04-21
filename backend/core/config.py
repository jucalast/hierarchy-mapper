"""
Configuração centralizada do sistema.
Carrega variáveis de ambiente uma única vez e expõe como objeto global.
"""
import os
from dotenv import load_dotenv

# Carrega .env uma única vez no import deste módulo
load_dotenv()


class Settings:
    """Configurações centralizadas do backend."""

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./intelligence.db")

    # --- Redis ---
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", None)

    # --- AI / LLM ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # --- Pipedrive CRM ---
    PIPEDRIVE_API_TOKEN: str = os.getenv("PIPEDRIVE_API_TOKEN", "")
    PIPEDRIVE_USER_ID: int = 24921888  # ID João Luccas

    # --- LinkedIn Enrichment ---
    PROXYCURL_API_KEY: str = os.getenv("PROXYCURL_API_KEY", "")
    RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")

    # --- Email ---
    EMAIL_API_KEY: str = os.getenv("EMAIL_API_KEY", "")
    EMAIL_USER: str = os.getenv("EMAIL_USER", "joao.moura@jferres.com.br")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
    EMAIL_PORT: int = int(os.getenv("EMAIL_PORT", 8002))
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")

    # --- WhatsApp ---
    WHATSAPP_SERVICE_URL: str = "http://localhost:8001/api/whatsapp"
    WHATSAPP_APP_ID: str = os.getenv("WHATSAPP_APP_ID", "")
    WHATSAPP_APP_SECRET: str = os.getenv("WHATSAPP_APP_SECRET", "")
    WHATSAPP_ACCESS_TOKEN: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")


# Singleton: importar de qualquer lugar como `from core.config import settings`
settings = Settings()
