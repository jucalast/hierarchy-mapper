"""
api.v1.routers.organizations
=============================
Endpoints CRUD para organizações locais (espelho enriquecido do Pipedrive).

GET /organizations/search    → busca por nome ou domínio (autocomplete)
GET /organizations/{org_id}  → detalhes de uma organização
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.infra.database import get_db
from core.observability.logging_config import get_logger
from models import Organization

router = APIRouter()
log = get_logger(__name__)

@router.get("/search")
async def search_organizations(
    q: str = Query(..., min_length=1, description="Termo de busca para nome ou domínio da empresa"),
    db: AsyncSession = Depends(get_db)
):
    """
    Busca organizações no banco de dados por nome ou domínio.
    Retorna uma lista de correspondências ordenadas por relevância.
    """
    try:
        # Prepara o termo para busca (case-insensitive)
        search_term = f"%{q}%"
        
        # Busca por nome ou domínio
        stmt = select(Organization).where(
            or_(
                func.lower(Organization.name).like(func.lower(search_term)),
                func.lower(Organization.domain).like(func.lower(search_term)) if Organization.domain else False
            )
        ).limit(10)
        
        result = await db.execute(stmt)
        organizations = result.scalars().all()
        
        # Formata os resultados
        results = [
            {
                "id": org.id,
                "name": org.name,
                "domain": org.domain or None,
                "logo_url": org.logo_url or None,
                "icp_score": org.icp_score,
                "icp_tier": org.icp_tier
            }
            for org in organizations
        ]
        
        return {"results": results, "total": len(results)}
    
    except Exception as e:
        log.warning("organizations.search.failed", query=q, error=str(e))
        return {"results": [], "total": 0}


@router.get("/{org_id}")
async def get_organization(
    org_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Busca uma organização específica pelo ID.
    """
    try:
        from sqlalchemy import or_
        stmt = select(Organization).where(
            or_(Organization.id == org_id, Organization.pipedrive_id == org_id)
        )
        result = await db.execute(stmt)
        org = result.scalars().first()
        
        if not org:
            return {"error": "Organization not found"}
        
        return {
            "id": org.id,
            "name": org.name,
            "domain": org.domain,
            "cnpj": org.cnpj,
            "logo_url": org.logo_url,
            "linkedin_url": org.linkedin_url,
            "address": org.address,
            "icp_score": org.icp_score,
            "icp_tier": org.icp_tier,
            "prospecting_context": org.prospecting_context
        }
    
    except Exception as e:
        log.warning("organizations.get.failed", org_id=org_id, error=str(e))
        raise HTTPException(status_code=500, detail="Erro ao buscar organização.")

@router.get("/{org_id}/photo")
async def get_organization_photo(
    org_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna a foto da empresa (Google Maps/Places) para usar de background no header
    do Drawer. Busca e persiste no banco (cache permanente) na primeira chamada;
    chamadas seguintes para a mesma empresa retornam o valor já salvo sem nova
    consulta à API.
    """
    from modules.intelligence.service.company_photo_service import fetch_and_cache_company_photo
    try:
        photo_url = await fetch_and_cache_company_photo(org_id, db)
        return {"ok": bool(photo_url), "photo_url": photo_url}
    except Exception as e:
        log.warning("organizations.get_photo.failed", org_id=org_id, error=str(e))
        return {"ok": False, "photo_url": None}


@router.post("/{org_id}/validate-emails")
async def start_batch_email_validation(
    org_id: int,
    background_tasks: BackgroundTasks
):
    """
    Inicia o Superteste (validação em lote) de todos os e-mails da empresa em segundo plano.
    """
    from modules.agent.service.tools.intelligence import batch_discover_and_validate_org_emails
    
    # Executa a função pesada em segundo plano para não dar timeout no frontend
    background_tasks.add_task(batch_discover_and_validate_org_emails, org_id)
        
    return {"ok": True, "message": "Validação em lote iniciada em segundo plano."}


@router.delete("/{org_id}/prospecting-plan")
async def delete_prospecting_plan(
    org_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Apaga o plano de prospecção (prospecting_context) de uma organização.
    """
    try:
        from sqlalchemy import or_
        stmt = select(Organization).where(
            or_(Organization.id == org_id, Organization.pipedrive_id == org_id)
        )
        result = await db.execute(stmt)
        org = result.scalars().first()
        
        if not org:
            raise HTTPException(status_code=404, detail="Organização não encontrada.")
            
        org.prospecting_context = None
        await db.commit()
        return {"ok": True, "message": "Plano de prospecção apagado com sucesso."}
    except Exception as e:
        log.warning("organizations.delete_prospecting_plan.failed", org_id=org_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Erro ao apagar plano: {e}")



