from fastapi import APIRouter
from api.v1.endpoints import proxy, hierarchy, brand, pipedrive, intelligence, jobs, ai, organizations, search

api_router = APIRouter()

# Jobs & Background Tasks: /api/v1/jobs/*
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])

# Proxy endpoints: /api/v1/proxy/*
api_router.include_router(proxy.router, prefix="/proxy", tags=["proxy"])

# AI endpoints: /api/v1/ai/*
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])

# Brand endpoints: /api/v1/brand/*
api_router.include_router(brand.router, prefix="/brand", tags=["brand"])

# Hierarchy endpoints: /api/v1/hierarchy/*
api_router.include_router(hierarchy.router, prefix="/hierarchy", tags=["hierarchy"])

# Organizations endpoints: /api/v1/organizations/*
api_router.include_router(organizations.router, prefix="/organizations", tags=["organizations"])

# Pipedrive endpoints
# Note: pipedrive_sync and pipedrive_smart_sync were at root of /api/v1/ in old version
# but we can also group them or keep them root by setting prefix to "" if needed.
# To avoid breaking frontend, we must match:
# /api/v1/pipedrive_sync
# /api/v1/pipedrive_smart_sync
# /api/v1/pipedrive/organizations
api_router.include_router(pipedrive.router, tags=["pipedrive"])

# Intelligence endpoints: /api/v1/intelligence/*
api_router.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"])

# Search endpoints: /api/v1/search/*
api_router.include_router(search.router, prefix="/search", tags=["search"])
