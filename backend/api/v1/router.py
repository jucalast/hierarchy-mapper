"""
api.v1.router
=============
Agregador central de todos os routers da API v1.

Cada domínio de negócio expõe um router próprio que é incluído aqui com seu prefixo.
Para adicionar um novo domínio: crie o router no módulo correspondente e inclua abaixo.

Prefixos canônicos:
    /auth           → autenticação JWT
    /settings       → configurações do sistema/Tenant
    /jobs           → background jobs (ARQ / WebSocket)
    /proxy          → proxy de imagens e URL preview
    /ai             → preferência de modelo, quotas, transcrição
    /brand          → descoberta de marca institucional
    /hierarchy      → B2B scanner e grafo de hierarquia
    /organizations  → CRUD de organizações locais
    /intelligence   → sync hub e inteligência de mercado
    /search         → busca global entre entidades
    /conversations  → histórico de chat e atividades
    /triggers       → ações automáticas (respostas email/WhatsApp)
    /agent          → orquestração do agente autônomo
    /prospecting    → prospecção geolocalizada
    /communication  → envio de email e WhatsApp
    (sem prefixo)   → CRM/Pipedrive sync
"""
from fastapi import APIRouter
from api.v1.routers import proxy, brand, jobs, ai, organizations, search, conversations, agent, settings, auth, messages
from modules.prospecting   import router as prospecting_router
from modules.intelligence  import router as intelligence_router
from modules.crm           import router as crm_router
from modules.communication import router as communication_router
from modules.triggers      import router as triggers_router
from modules.hierarchy     import router as hierarchy_router

api_router = APIRouter()

api_router.include_router(auth.router,           prefix="/auth",          tags=["auth"])
api_router.include_router(settings.router,       prefix="/settings",      tags=["settings"])
api_router.include_router(jobs.router,           prefix="/jobs",          tags=["jobs"])
api_router.include_router(proxy.router,          prefix="/proxy",         tags=["proxy"])
api_router.include_router(ai.router,             prefix="/ai",            tags=["ai"])
api_router.include_router(brand.router,          prefix="/brand",         tags=["brand"])
api_router.include_router(hierarchy_router,       prefix="/hierarchy",     tags=["hierarchy"])
api_router.include_router(organizations.router,  prefix="/organizations", tags=["organizations"])
api_router.include_router(crm_router,                                     tags=["crm"])
api_router.include_router(intelligence_router,   prefix="/intelligence",  tags=["intelligence"])
api_router.include_router(search.router,         prefix="/search",        tags=["search"])
api_router.include_router(conversations.router,  prefix="/conversations", tags=["conversations"])
api_router.include_router(triggers_router,       prefix="/triggers",      tags=["triggers"])
api_router.include_router(agent.router,          prefix="/agent",         tags=["agent"])
api_router.include_router(prospecting_router,    prefix="/prospecting",   tags=["prospecting"])
api_router.include_router(communication_router,  prefix="/communication", tags=["communication"])
api_router.include_router(messages.router,       prefix="/messages",      tags=["messages"])
