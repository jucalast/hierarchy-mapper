from fastapi import APIRouter
from api.v1.routers import proxy, brand, jobs, ai, organizations, search, conversations, agent, settings, auth
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
