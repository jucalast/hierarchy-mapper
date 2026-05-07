"""
core.config
===========
Configuração centralizada do backend.

Single source of truth para TODOS os parâmetros do sistema:
- Segredos (API keys, senhas)
- Endpoints (URLs, portas)
- Limites e timeouts (retry, cooldown, semáforo)
- Feature flags

Uso:
    from core.config import settings
    settings.GEMINI_API_KEY
    settings.http.default_timeout
    settings.ai.gemini_cooldown_base_sec

Retrocompatibilidade:
    Todos os atributos que existiam em versões anteriores (GEMINI_API_KEY,
    PIPEDRIVE_API_TOKEN, etc.) continuam acessíveis em settings.<NOME>.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

try:
    # Pydantic v2 + pydantic-settings (instalar via requirements.txt)
    from pydantic import Field, field_validator
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _PYDANTIC_SETTINGS_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback para ambientes sem pydantic-settings
    _PYDANTIC_SETTINGS_AVAILABLE = False
    from dotenv import load_dotenv
    load_dotenv()


# =============================================================================
# Sub-configurações (agrupamento lógico)
# =============================================================================

if _PYDANTIC_SETTINGS_AVAILABLE:

    class HTTPConfig(BaseSettings):
        """Cliente HTTP único (httpx.AsyncClient) compartilhado no app."""
        model_config = SettingsConfigDict(
            env_prefix="HTTP_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        default_timeout: float = 30.0
        connect_timeout: float = 5.0
        pool_max_connections: int = 200
        pool_max_keepalive_connections: int = 50
        keepalive_expiry_sec: float = 30.0
        http2_enabled: bool = True
        user_agent: str = "HierarchyMapper/2.0 (+FastAPI)"

    class AIConfig(BaseSettings):
        """Configuração da camada de IA (providers, circuit breaker, cache)."""
        model_config = SettingsConfigDict(
            env_prefix="AI_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        # Seleção de providers (ordem de preferência)
        primary_provider: str = "claude"
        fallback_chain: str = "claude,gemini,groq"  # Claude agora é o principal brain

        # Timeouts por tier (sobrescreve default quando LLM é chamado)
        timeout_fast_sec: float = 15.0        # intent classification, tarefas leves
        timeout_standard_sec: float = 45.0    # resposta final
        timeout_deep_sec: float = 90.0        # agent workflow, análises longas

        # Circuit breaker (por provedor)
        cooldown_base_sec: int = 15  # Reduzido de 60 para 15
        cooldown_max_sec: int = 120  # Reduzido de 300 para 120
        max_consecutive_failures_before_reset: int = 8  # Aumentado de 5 para 8

        # Cache de respostas idempotentes
        response_cache_enabled: bool = True
        response_cache_ttl_sec: int = 600
        response_cache_max_entries: int = 1024

        # Limites de contexto
        history_max_messages: int = 6
        history_truncate_chars: int = 1200
        history_data_max_chars: int = 300

        # Modelos (ordem dentro de cada provider)
        # gemini-1.5-pro: 100 RPD | gemini-1.5-flash: 250 RPD | gemini-2.0-flash-exp: 1000 RPD
        gemini_models: str = (
            "gemini-2.0-flash-exp,"
            "gemini-1.5-flash,"
            "gemini-flash-latest"
        )
        groq_models: str = (
            "llama-3.3-70b-versatile,"
            "llama-3.1-8b-instant,"
            "meta-llama/llama-4-scout-17b-16e-instruct,"
            "qwen/qwen3-32b,"
            "llama-3.2-11b-vision-preview,"
            "groq/compound"
        )
        claude_models: str = "claude-3-5-sonnet-latest,claude-3-5-haiku-latest"
        sambanova_models: str = "Meta-Llama-3.3-70B-Instruct,Llama-4-Scout-17B-16E-Instruct"
        deepseek_models: str = "deepseek-chat"
        cerebras_models: str = "gpt-oss-120b,zai-glm-4.7,qwen-3-235b-instruct,llama3.1-8b,llama-3.3-70b"
        ollama_models: str = "qwen2.5:3b"

        # Temperatura default
        temperature_default: float = 0.1

    class DatabaseConfig(BaseSettings):
        model_config = SettingsConfigDict(
            env_prefix="DB_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        echo: bool = False
        pool_size: int = 10
        max_overflow: int = 20
        pool_recycle_sec: int = 1800
        pool_pre_ping: bool = True
        statement_timeout_sec: int = 30

    class PipedriveConfig(BaseSettings):
        model_config = SettingsConfigDict(
            env_prefix="PIPEDRIVE_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        concurrency_limit: int = 10
        request_timeout_sec: float = 30.0
        retry_max_attempts: int = 3
        cache_stages_ttl_sec: int = 3600

    class EmailConfig(BaseSettings):
        model_config = SettingsConfigDict(
            env_prefix="EMAIL_SCAN_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        scan_interval_min: int = 10
        scan_folder: str = "Leads"
        imap_timeout_sec: float = 30.0

    class ObservabilityConfig(BaseSettings):
        model_config = SettingsConfigDict(
            env_prefix="OBS_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        log_level: str = "INFO"
        log_json: bool = False        # True em produção; colorido em dev
        metrics_enabled: bool = True
        request_id_header: str = "X-Request-ID"
        slow_request_threshold_sec: float = 2.0

    class CORSConfig(BaseSettings):
        model_config = SettingsConfigDict(
            env_prefix="CORS_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        # CSV de origens; "*" permite todas (use com cautela em prod)
        allow_origins: str = "*"
        allow_credentials: bool = True

    # =========================================================================
    # Settings raiz — carrega do .env
    # =========================================================================

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )

        # --- Ambiente ---
        environment: str = Field(default="development")
        debug: bool = Field(default=False)

        # --- Database ---
        DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./intelligence.db")

        # --- Redis ---
        REDIS_HOST: str = Field(default="localhost")
        REDIS_PORT: int = Field(default=6379)
        REDIS_PASSWORD: Optional[str] = Field(default=None)
        REDIS_DB: int = Field(default=0)

        # --- AI / LLM ---
        GEMINI_API_KEY: str = Field(default="")
        GROQ_API_KEY: str = Field(default="")
        ANTHROPIC_API_KEY: str = Field(default="")
        SAMBANOVA_API_KEY: str = Field(default="")
        DEEPSEEK_API_KEY: str = Field(default="")
        CEREBRAS_API_KEY: str = Field(default="")

        # --- Pipedrive ---
        PIPEDRIVE_API_TOKEN: str = Field(default="")
        PIPEDRIVE_USER_ID: int = Field(default=24921888)

        # --- LinkedIn Enrichment ---
        PROXYCURL_API_KEY: str = Field(default="")
        RAPIDAPI_KEY: str = Field(default="")

        # --- Email ---
        EMAIL_API_KEY: str = Field(default="")
        EMAIL_USER: str = Field(default="joao.moura@jferres.com.br")
        EMAIL_PASSWORD: str = Field(default="")
        EMAIL_PORT: int = Field(default=8002)
        API_BASE_URL: str = Field(default="http://localhost:8000")
        OLLAMA_API_BASE: str = Field(default="http://localhost:11434/v1/chat/completions")

        # --- WhatsApp ---
        WHATSAPP_SERVICE_URL: str = Field(default="http://localhost:8001/api/whatsapp")
        WHATSAPP_APP_ID: str = Field(default="")
        WHATSAPP_APP_SECRET: str = Field(default="")
        WHATSAPP_ACCESS_TOKEN: str = Field(default="")
        WHATSAPP_PHONE_NUMBER_ID: str = Field(default="")
        WHATSAPP_VERIFY_TOKEN: str = Field(default="")

        # --- Sub-configurações (carregam do mesmo .env com prefixo) ---
        http: HTTPConfig = Field(default_factory=HTTPConfig)
        ai: AIConfig = Field(default_factory=AIConfig)
        db: DatabaseConfig = Field(default_factory=DatabaseConfig)
        pipedrive: PipedriveConfig = Field(default_factory=PipedriveConfig)
        email: EmailConfig = Field(default_factory=EmailConfig)
        observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
        cors: CORSConfig = Field(default_factory=CORSConfig)

        # ---------------------------------------------------------------------
        # Helpers derivados
        # ---------------------------------------------------------------------
        @property
        def is_production(self) -> bool:
            return self.environment.lower() in {"production", "prod"}

        @property
        def is_development(self) -> bool:
            return self.environment.lower() in {"development", "dev", "local"}

        @property
        def cors_origins_list(self) -> list[str]:
            raw = self.cors.allow_origins.strip()
            if raw in ("*", ""):
                return ["*"]
            return [o.strip() for o in raw.split(",") if o.strip()]

        @property
        def ai_fallback_providers(self) -> list[str]:
            return [p.strip().lower() for p in self.ai.fallback_chain.split(",") if p.strip()]

        @property
        def ai_gemini_models_list(self) -> list[str]:
            return [m.strip() for m in self.ai.gemini_models.split(",") if m.strip()]

        @property
        def ai_groq_models_list(self) -> list[str]:
            return [m.strip() for m in self.ai.groq_models.split(",") if m.strip()]

        @property
        def ai_claude_models_list(self) -> list[str]:
            return [m.strip() for m in self.ai.claude_models.split(",") if m.strip()]

        @property
        def ai_sambanova_models_list(self) -> list[str]:
            return [m.strip() for m in self.ai.sambanova_models.split(",") if m.strip()]

        @property
        def ai_deepseek_models_list(self) -> list[str]:
            return [m.strip() for m in self.ai.deepseek_models.split(",") if m.strip()]

        @property
        def ai_cerebras_models_list(self) -> list[str]:
            return [m.strip() for m in self.ai.cerebras_models.split(",") if m.strip()]

        @property
        def ai_ollama_models_list(self) -> list[str]:
            return [m.strip() for m in self.ai.ollama_models.split(",") if m.strip()]

        @property
        def has_gemini(self) -> bool:
            return bool(self.GEMINI_API_KEY)

        @property
        def has_groq(self) -> bool:
            return bool(self.GROQ_API_KEY)

        @property
        def has_claude(self) -> bool:
            return bool(self.ANTHROPIC_API_KEY)

        @property
        def has_sambanova(self) -> bool:
            return bool(self.SAMBANOVA_API_KEY)

        @property
        def has_cerebras(self) -> bool:
            return bool(self.CEREBRAS_API_KEY)

        @property
        def has_deepseek(self) -> bool:
            return bool(self.DEEPSEEK_API_KEY)

        @property
        def has_ollama(self) -> bool:
            return True  # Ollama is local, doesn't need key

        @property
        def any_llm_available(self) -> bool:
            return self.has_gemini or self.has_groq or self.has_claude or self.has_sambanova or self.has_cerebras or self.has_deepseek or self.has_ollama

        @field_validator("environment")
        @classmethod
        def _validate_environment(cls, v: str) -> str:
            v = (v or "development").lower()
            if v not in {"development", "dev", "local", "staging", "production", "prod", "test"}:
                return "development"
            return v

else:
    # -------------------------------------------------------------------------
    # Fallback sem pydantic-settings (ambiente com apenas pydantic+dotenv).
    # Mantém compatibilidade 100% com a versão original.
    # -------------------------------------------------------------------------
    class _FlatSettings:
        DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./intelligence.db")
        REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
        REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
        REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD") or None
        REDIS_DB: int = int(os.getenv("REDIS_DB", 0))

        GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
        ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
        SAMBANOVA_API_KEY: str = os.getenv("SAMBANOVA_API_KEY", "")
        DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
        CEREBRAS_API_KEY: str = os.getenv("CEREBRAS_API_KEY", "")

        PIPEDRIVE_API_TOKEN: str = os.getenv("PIPEDRIVE_API_TOKEN", "")
        PIPEDRIVE_USER_ID: int = int(os.getenv("PIPEDRIVE_USER_ID", 24921888))

        PROXYCURL_API_KEY: str = os.getenv("PROXYCURL_API_KEY", "")
        RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")

        EMAIL_API_KEY: str = os.getenv("EMAIL_API_KEY", "")
        EMAIL_USER: str = os.getenv("EMAIL_USER", "joao.moura@jferres.com.br")
        EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
        EMAIL_PORT: int = int(os.getenv("EMAIL_PORT", 8002))
        API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")

        WHATSAPP_SERVICE_URL: str = os.getenv("WHATSAPP_SERVICE_URL", "http://localhost:8001/api/whatsapp")
        WHATSAPP_APP_ID: str = os.getenv("WHATSAPP_APP_ID", "")
        WHATSAPP_APP_SECRET: str = os.getenv("WHATSAPP_APP_SECRET", "")
        WHATSAPP_ACCESS_TOKEN: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
        WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")

        environment: str = os.getenv("ENVIRONMENT", "development").lower()
        debug: bool = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"}

        # Atributos agrupados (compatibilidade com o caminho feliz)
        class _Namespace:
            def __init__(self, **kw):
                for k, v in kw.items():
                    setattr(self, k, v)

        http = _Namespace(
            default_timeout=30.0, connect_timeout=5.0,
            pool_max_connections=200, pool_max_keepalive_connections=50,
            keepalive_expiry_sec=30.0, http2_enabled=True,
            user_agent="HierarchyMapper/2.0 (+FastAPI)",
        )
        ai = _Namespace(
            primary_provider="gemini",
            fallback_chain="gemini,groq,claude",
            timeout_fast_sec=15.0, timeout_standard_sec=45.0, timeout_deep_sec=90.0,
            cooldown_base_sec=15, cooldown_max_sec=120,
            max_consecutive_failures_before_reset=8,
            response_cache_enabled=True, response_cache_ttl_sec=600,
            response_cache_max_entries=1024,
            history_max_messages=6, history_truncate_chars=1200, history_data_max_chars=300,
            gemini_models="gemini-2.5-pro,gemini-2.5-flash,gemini-2.5-flash-lite",
            groq_models="llama-3.3-70b-versatile,llama-3.1-8b-instant",
            claude_models="claude-sonnet-4-5,claude-3-5-haiku-latest",
            sambanova_models="Meta-Llama-3.3-70B-Instruct,Llama-4-Scout-17B-16E-Instruct",
            deepseek_models="deepseek-chat",
            cerebras_models="gpt-oss-120b,zai-glm-4.7,qwen-3-235b-instruct,llama-3.3-70b,llama3.1-8b",
            temperature_default=0.1,
        )
        db = _Namespace(
            echo=False, pool_size=10, max_overflow=20,
            pool_recycle_sec=1800, pool_pre_ping=True, statement_timeout_sec=30,
        )
        pipedrive = _Namespace(
            concurrency_limit=10, request_timeout_sec=30.0,
            retry_max_attempts=3, cache_stages_ttl_sec=3600,
        )
        email = _Namespace(
            scan_interval_min=10, scan_folder="Leads", imap_timeout_sec=30.0,
        )
        observability = _Namespace(
            log_level="INFO", log_json=False, metrics_enabled=True,
            request_id_header="X-Request-ID", slow_request_threshold_sec=2.0,
        )
        cors = _Namespace(allow_origins="*", allow_credentials=True)

        @property
        def is_production(self) -> bool:
            return self.environment in {"production", "prod"}

        @property
        def is_development(self) -> bool:
            return self.environment in {"development", "dev", "local"}

        @property
        def cors_origins_list(self) -> list:
            raw = self.cors.allow_origins.strip()
            if raw in ("*", ""):
                return ["*"]
            return [o.strip() for o in raw.split(",") if o.strip()]

        @property
        def ai_fallback_providers(self) -> list:
            return [p.strip().lower() for p in self.ai.fallback_chain.split(",") if p.strip()]

        @property
        def ai_gemini_models_list(self) -> list:
            return [m.strip() for m in self.ai.gemini_models.split(",") if m.strip()]

        @property
        def ai_groq_models_list(self) -> list:
            return [m.strip() for m in self.ai.groq_models.split(",") if m.strip()]

        @property
        def ai_claude_models_list(self) -> list:
            return [m.strip() for m in self.ai.claude_models.split(",") if m.strip()]

        @property
        def ai_sambanova_models_list(self) -> list:
            return [m.strip() for m in self.ai.sambanova_models.split(",") if m.strip()]

        @property
        def ai_deepseek_models_list(self) -> list:
            return [m.strip() for m in self.ai.deepseek_models.split(",") if m.strip()]

        @property
        def ai_cerebras_models_list(self) -> list:
            return [m.strip() for m in self.ai.cerebras_models.split(",") if m.strip()]

        @property
        def has_gemini(self) -> bool:
            return bool(self.GEMINI_API_KEY)

        @property
        def has_groq(self) -> bool:
            return bool(self.GROQ_API_KEY)

        @property
        def has_claude(self) -> bool:
            return bool(self.ANTHROPIC_API_KEY)

        @property
        def has_sambanova(self) -> bool:
            return bool(self.SAMBANOVA_API_KEY)

        @property
        def has_cerebras(self) -> bool:
            return bool(self.CEREBRAS_API_KEY)

        @property
        def has_deepseek(self) -> bool:
            return bool(self.DEEPSEEK_API_KEY)

        @property
        def has_ollama(self) -> bool:
            return True

        @property
        def any_llm_available(self) -> bool:
            return (
                self.has_gemini
                or self.has_groq
                or self.has_claude
                or self.has_sambanova
                or self.has_cerebras
                or self.has_deepseek
                or self.has_ollama
            )

    Settings = _FlatSettings  # type: ignore[assignment,misc]


@lru_cache(maxsize=1)
def get_settings() -> "Settings":
    """Acessor cacheado (útil para dependency injection)."""
    return Settings()


# Singleton público — importado como `from core.config import settings`
settings = get_settings()
