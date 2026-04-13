from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from sqlalchemy import select, delete, or_
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
    """Persiste a escolha manual do usuário vinculando o Perfil do LinkedIn à Organização e sincroniza com Pipedrive."""
    try:
        from services.pipedrive.pipedrive_service import pipedrive_service
        
        async with async_session() as session:
            # 🕵️ BUSCA AGRESSIVA DE DEDUPLICAÇÃO (Prioriza Pipedrive ID > CNPJ > Nome)
            from sqlalchemy import func
            
            # Filtro 1: Pipedrive ID
            filters = [Organization.pipedrive_id == payload.pipedrive_id]
            
            # Filtro 2: CNPJ (se fornecido)
            if payload.cnpj:
                clean_cnpj = payload.cnpj.replace(".", "").replace("/", "").replace("-", "")
                filters.append(Organization.cnpj == clean_cnpj)
            
            # Filtro 3: Nome (Case Insensitive)
            if payload.name:
                filters.append(func.lower(Organization.name) == payload.name.lower())
                
            stmt = select(Organization).where(or_(*filters))
            res = await session.execute(stmt)
            org = res.scalars().first()
            
            if not org:
                print(f"[Intelligence] 🆕 Criando novo registro para: {payload.name}")
                org = Organization(pipedrive_id=payload.pipedrive_id)
                session.add(org)
            else:
                print(f"[Intelligence] 🤝 Fundindo dados no registro existente ID {org.id}: {org.name}")
                # Se o registro existente não tinha Pipedrive ID e agora temos, vincula.
                if not org.pipedrive_id and payload.pipedrive_id:
                    org.pipedrive_id = payload.pipedrive_id
            
            # ✍️ ATRIBUIÇÃO LOCAL: Vincula os dados escolhidos ao registro central
            if payload.name: org.name = payload.name
            if payload.cnpj: org.cnpj = payload.cnpj.replace(".", "").replace("/", "").replace("-", "")
            if payload.domain: org.domain = payload.domain
            if payload.address and len(payload.address) > 3: 
                org.address = payload.address
            
            # Persiste dados do LinkedIn
            if payload.linkedin_url: org.linkedin_url = payload.linkedin_url
            if payload.logo_url: org.logo_url = payload.logo_url
            
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
                        seniority=6, # Nível de Sócio é 6 (Admin/Owner)
                        company_id=org.id
                    )
                    session.add(new_p)
                await session.commit()
            
            # 🚀 SINCRONIZAÇÃO PIPEDRIVE (Só agora que foi confirmado!)
            if payload.pipedrive_id:
                pipedrive_data = {
                    "address": payload.address,
                    "domain": payload.domain,
                    "cnpj": payload.cnpj,
                    "linkedin_url": payload.linkedin_url,
                    "logo_url": payload.logo_url,
                    "name": payload.name
                }
                await pipedrive_service.update_organization(payload.pipedrive_id, pipedrive_data)

            return {
                "status": "success", 
                "message": f"Organização '{payload.name}' mapeada e sincronizada com sucesso.",
                "local_id": org.id
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
