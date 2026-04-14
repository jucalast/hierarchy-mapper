from fastapi import APIRouter, Query, Depends
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models import Organization
from typing import List, Optional

router = APIRouter()

class OrgSearchResult:
    def __init__(self, id: int, name: str, domain: Optional[str] = None):
        self.id = id
        self.name = name
        self.domain = domain

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
                "logo_url": org.logo_url or None
            }
            for org in organizations
        ]
        
        return {"results": results, "total": len(results)}
    
    except Exception as e:
        print(f"[Organizations Search] Erro: {str(e)}")
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
        stmt = select(Organization).where(Organization.id == org_id)
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
            "address": org.address
        }
    
    except Exception as e:
        print(f"[Organization Get] Erro: {str(e)}")
        return {"error": str(e)}
