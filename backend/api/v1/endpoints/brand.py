from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from services.intelligence.brand_discovery import discover_company_brand

router = APIRouter()

@router.get("/discover")
async def discover_brand(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    domain: Optional[str] = Query(None, description="Domínio da empresa"),
    raw_name: Optional[str] = Query(None, description="Nome base da empresa"),
    force: bool = Query(False, description="Forçar nova busca OSINT")
):
    """
    Busca sugestões de nomes de marca (LinkedIn-ready) antes de iniciar o scan.
    """
    try:
        return await discover_company_brand(cnpj, domain, raw_name, force=force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
