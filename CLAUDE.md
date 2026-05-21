# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Comandos de Desenvolvimento

### Iniciar ambiente completo (recomendado)
```powershell
# Na raiz do projeto — inicia Redis + Backend (hot-reload) + Frontend + WhatsApp service
.\rodar_dev.ps1

# Versão estável (sem hot-reload)
.\rodar_dev_stable.ps1
```

### Iniciar apenas o backend (manual)
```powershell
cd backend
# Ativar venv primeiro
..\venv\Scripts\Activate.ps1

# Servidor com hot-reload
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Worker ARQ (jobs pesados em background)
python -m arq services.worker.WorkerSettings
```

### Iniciar apenas o frontend
```powershell
cd frontend
npm run dev      # porta 3000
npm run build
npm run lint
```

### Verificar sintaxe Python
```powershell
cd backend
python -m py_compile <arquivo.py>
# Ou todos de uma vez:
Get-ChildItem -Recurse -Filter "*.py" | ForEach-Object { python -m py_compile $_.FullName }
```

### Banco de dados
```powershell
cd backend
# Migrações (Alembic)
alembic upgrade head
alembic revision --autogenerate -m "descrição"

# O banco SQLite (intelligence.db) é criado automaticamente no startup
# O seed de dados padrão roda em init_db() → seed_system_settings() + seed_tenant_data()
```

---

## Arquitetura do Backend

### Stack principal
| Camada | Tecnologia |
|--------|-----------|
| Web framework | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 async (aiosqlite) |
| LLM Gateway | Gemini / Claude / Groq / Cerebras / SambaNova / DeepSeek / Ollama |
| Background jobs | arq (Redis queue) |
| Cache | Redis (opcional) + MemoryCache TTL (fallback) |
| HTTP client | httpx.AsyncClient singleton com pooling |
| Observabilidade | structlog + Prometheus metrics |
| Rate limiting | slowapi (por IP) |

### Estrutura de diretórios

```
backend/
├── main.py                    # Entrypoint FastAPI: lifespan, middleware, exception handlers
├── api/
│   └── v1/
│       ├── router.py          # Agrega todos os routers em api_router
│       └── routers/           # Endpoints: auth, ai, conversations, jobs, organizations,
│                              #   proxy, search, settings, brand, agent
├── core/                      # Infraestrutura transversal (sem lógica de negócio)
│   ├── config.py              # Settings único (pydantic-settings) — single source of truth
│   ├── exceptions.py          # Exceções de negócio padronizadas
│   ├── rate_limiter.py        # slowapi limiter por IP
│   ├── infra/
│   │   ├── database.py        # Engine SQLAlchemy, get_db(), init_db(), seeds
│   │   ├── cache.py           # MemoryCache TTL + async_ttl_cache decorator
│   │   ├── http_client.py     # httpx.AsyncClient singleton
│   │   └── redis_config.py    # redis.Redis síncrono para cache de imagens
│   ├── llm/
│   │   ├── base.py            # Interfaces: LLMProvider, LLMResult, LLMTier, LLMMessage
│   │   ├── router.py          # ask_llm(), fallback chain, throttle, cache de respostas
│   │   ├── gemini_quota.py    # Rastreamento de quota diária Gemini
│   │   ├── quota_manager.py   # Circuit breaker por provider
│   │   └── providers/         # claude.py, gemini.py, groq.py, ollama.py, openai_compat.py
│   └── observability/
│       ├── logging_config.py  # structlog, RequestIDMiddleware, get_logger()
│       └── metrics.py         # Métricas Prometheus: http, llm, cache, circuit breaker
├── models/                    # SQLAlchemy ORM (declarative)
│   ├── __init__.py            # Re-exporta tudo
│   ├── conversation/          # ConversationThread, ConversationMessage, ActivityLog
│   ├── crm/                   # Integration (Pipedrive, WhatsApp, Outlook)
│   ├── hierarchy/             # HierarchyConfig
│   ├── organization/          # Organization, Tenant
│   ├── people/                # Employee, ProspectLead
│   └── system/                # SystemSetting, User, BusinessProfile, ICPConfig
├── modules/                   # Lógica de negócio organizada por domínio
│   ├── agent/                 # Orquestração de agente autônomo (loop, tools, prompts)
│   ├── ai/                    # Intent classification, business context, data pipeline
│   ├── communication/         # Email (IMAP) + WhatsApp (API externa)
│   ├── context/               # Montagem de contexto compartilhado para IA
│   ├── crm/                   # Integração Pipedrive (sync, deals, contacts)
│   ├── hierarchy/             # B2B discovery (scanner, role engine, graph builder)
│   ├── intelligence/          # Brand discovery, sync hub, URL preview
│   ├── prospecting/           # Prospecção geolocalizada com mapa Leaflet
│   ├── sales/                 # Estratégia de vendas (sugestão de próximas ações)
│   └── triggers/              # Polling de respostas (email/WhatsApp), ações automáticas
└── services/
    └── worker.py              # ARQ worker — run_b2b_discovery_task()
```

---

## Padrões Arquiteturais Críticos

### 1. LLM Gateway — `ask_llm()`
**Nunca chame providers LLM diretamente.** Use sempre:
```python
from core.llm.router import ask_llm, LLMTier

result = await ask_llm(
    prompt="...",
    system="Você é um assistente B2B.",
    history=[{"role": "user", "content": "..."}],
    json_mode=True,
    tier=LLMTier.STANDARD,          # FAST=15s | STANDARD=45s | DEEP=90s
    preferred_model="gemini-2.5-flash",  # Opcional
    cache_prefix=str(org_id),        # Isola cache por organização
)
print(result.text, result.provider, result.model)
```

A fallback chain é definida em `settings.ai.fallback_chain` e executada automaticamente. `strict_model=True` desativa fallback.

### 2. Dependency Injection de banco
```python
from core.infra.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

@router.get("/example")
async def my_endpoint(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Organization).where(...))
    return result.scalars().all()
```

Nunca instancie `AsyncSession` diretamente. O rollback automático é feito pelo context manager de `async_session()`.

### 3. Logging estruturado — obrigatório em todos os módulos
```python
from core.observability.logging_config import get_logger

log = get_logger(__name__)  # No topo do arquivo, fora de funções

log.info("module.action", key=value, org_id=org_id)
log.warning("module.action.degraded", reason=str(e))
log.exception("module.action.failed", error=str(e))  # Inclui stack trace
```

**Nunca use `print()`.** Use log estruturado.

### 4. Cache de respostas LLM
O `ask_llm()` aplica cache automático quando `temperature <= 0.21` e `cacheable=True`. Para operações que não devem ser cacheadas (ex: streaming, geração criativa), use `cacheable=False`.

Para cachear outras funções:
```python
from core.infra.cache import async_ttl_cache

@async_ttl_cache(ttl_sec=600, max_entries=256, cache_name="meu_cache")
async def buscar_dados(org_id: int) -> dict:
    ...
```

### 5. HTTP client compartilhado
```python
from core.infra.http_client import get_http_client

client = get_http_client()  # Reutiliza pool de conexões
resp = await client.get("https://api.exemplo.com/dados")
```

Nunca crie `httpx.AsyncClient()` avulso dentro de requests — esgota file descriptors.

### 6. Módulos seguem o padrão: `router.py` + `service/`
Cada módulo em `modules/` expõe um `router.py` com os endpoints FastAPI e delega lógica para `service/`. Nunca coloque regras de negócio em `router.py`.

### 7. Tratamento de erros nos routers
```python
try:
    # operação de banco
    await session.commit()
except Exception as e:
    await session.rollback()
    log.exception("module.action.failed", error=str(e))
    raise HTTPException(status_code=500, detail="Mensagem amigável.")
```

---

## Configuração e Variáveis de Ambiente

O arquivo `.env` na raiz de `backend/` alimenta o `Settings` em `core/config.py`. Variáveis críticas:

```dotenv
# Banco
DATABASE_URL=sqlite+aiosqlite:///./intelligence.db

# LLM (ao menos um obrigatório)
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...
GROQ_API_KEY=...

# CRM
PIPEDRIVE_API_TOKEN=...

# Email
EMAIL_USER=joao@empresa.com.br
EMAIL_PASSWORD=...

# Segurança
JWT_SECRET=<valor-aleatório-longo>  # Obrigatório em produção
ENVIRONMENT=development              # ou production
```

Acesse sempre via `from core.config import settings` — nunca leia `os.getenv()` diretamente nos módulos de negócio.

---

## Modelos e Banco de Dados

### Criando um novo model
1. Crie em `models/<domínio>/<arquivo>.py` herdando de `Base` (`core.infra.database`)
2. Adicione índices compostos em `__table_args__` para queries frequentes
3. Importe no `models/__init__.py`
4. Importe no `init_db()` em `core/infra/database.py` (para `create_all`)
5. Adicione migração manual resiliente em `init_db()` se adicionar coluna a tabela existente

### Cascade delete
Use `cascade="all, delete-orphan"` e `ondelete="CASCADE"` no FK para garantir limpeza.

---

## Fluxo de uma requisição de chat (domínio principal)

```
Frontend POST /api/v1/agent/chat
    → agent.router
    → modules/agent/service/core/loop.py (AgentLoop)
    → modules/ai/service/pipeline/data_fetcher.py (monta contexto org)
    → core/llm/router.py → ask_llm() (fallback chain LLM)
    → modules/agent/service/tools/registry.py (executa tool calls)
    → api/v1/routers/conversations.py (salva mensagens)
    → SSE stream → Frontend
```

---

## Background Tasks (Startup)

Iniciadas no `lifespan` de `main.py`. Falhas são logadas como warning (não param o servidor):

| Task | Módulo | Propósito |
|------|--------|-----------|
| `SyncIntelligenceHub` | `modules/intelligence/service/sync_hub.py` | Sincroniza dados do CRM |
| `TriggerService` | `modules/triggers/service/trigger_service.py` | Polling de respostas email/WhatsApp |
| `start_email_scheduler` | `modules/communication/service/email/scheduler.py` | Scan IMAP periódico |
| `run_llm_preemptive_healthcheck` | `core/llm/router.py` | Healthcheck dos LLM providers |

---

## Regras ao Modificar Este Repositório

1. **Ao adicionar uma função pública**, adicione docstring com propósito e parâmetros não óbvios.
2. **Ao modificar uma função documentada**, atualize a docstring correspondente.
3. **Ao adicionar integração externa**, registre a variável de env no `core/config.py` (não no módulo).
4. **Ao alterar o schema do banco**, adicione migração resiliente em `init_db()` com `try/except: pass`.
5. **Ao alterar endpoints**, atualize o `__doc__` da função (FastAPI usa isso no Swagger).
6. **Nunca** importe `settings` de um lugar que não seja `core.config`.
7. **Nunca** coloque lógica de negócio em `router.py` — mova para `service/`.
8. **Ao remover código**, verifique se há referência no `models/__init__.py` e nos seeds.
