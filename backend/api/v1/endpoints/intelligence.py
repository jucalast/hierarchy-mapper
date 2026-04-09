from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from sqlalchemy import select, delete
from services.intelligence.intelligence_service import intelligence_service
from core.database import async_session
from models import Organization, Employee
from api.v1.schemas import ConfirmEnrichRequest

router = APIRouter()

@router.get("/enrich")
async def enrich_company_data(
    name: str = Query(..., description="Nome da empresa"),
    address: Optional[str] = Query(None, description="Pista de endereço para filtrar filiais"),
    cnpj: Optional[str] = Query(None, description="CNPJ fornecido manualmente"),
    force: bool = Query(False, description="Forçar nova busca ignorando cache")
):
    """Endpoint para descobrir CNPJ, Domínio e Selecionar Filiais via OSINT + IA."""
    try:
        return await intelligence_service.enrich_company(name, hint_address=address, force_refresh=force, cnpj=cnpj)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/confirm")
async def confirm_enrich_data(payload: ConfirmEnrichRequest):
    """Persiste a escolha manual do usuário vinculando o Perfil do LinkedIn à Organização."""
    try:
        async with async_session() as session:
            # 🕵️ Busca pela Empresa Única (Prioriza Pipedrive ID ou CNPJ)
            stmt = select(Organization).where(Organization.pipedrive_id == payload.pipedrive_id)
            if payload.cnpj:
                clean_cnpj = payload.cnpj.replace(".", "").replace("/", "").replace("-", "")
                stmt = select(Organization).where((Organization.pipedrive_id == payload.pipedrive_id) | (Organization.cnpj == clean_cnpj))
                
            res = await session.execute(stmt)
            org = res.scalars().first()
            
            if not org:
                # Cria se não existir nada vinculado a esse Pipedrive ID ou CNPJ
                org = Organization(pipedrive_id=payload.pipedrive_id)
                session.add(org)
            
            # ✍️ ATRIBUIÇÃO: Vincula os dados escolhidos ao registro central
            org.name = payload.name
            org.cnpj = payload.cnpj.replace(".", "").replace("/", "").replace("-", "") if payload.cnpj else org.cnpj
            org.domain = payload.domain
            org.address = payload.address
            # Se vierem dados de LinkedIn do carrossel no payload
            if hasattr(payload, 'linkedin_url'): org.linkedin_url = payload.linkedin_url
            if hasattr(payload, 'logo_url'): org.logo_url = payload.logo_url
            
            await session.commit()
            await session.refresh(org)

            # 👥 SALVAMENTO DE SÓCIOS (QSA)
            if payload.partners:
                # Limpa p/ evitar duplicados
                await session.execute(delete(Employee).where(Employee.company_id == org.id, Employee.department == "Quadro de Sócios (QSA)"))
                
                for p in payload.partners:
                    new_p = Employee(
                        name=p.get("name"),
                        role=p.get("role", "Sócio"),
                        department="Quadro de Sócios (QSA)",
                        seniority=0,
                        company_id=org.id
                    )
                    session.add(new_p)
                await session.commit()
            
            return {
                "status": "success", 
                "message": f"Associação LinkedIn + {len(payload.partners) if payload.partners else 0} Sócios concluída."
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
