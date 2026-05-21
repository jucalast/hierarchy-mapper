from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from sqlalchemy import select, delete, func
from core.infra.database import async_session
from models import Organization, Employee
from api.v1.schemas import ConfirmEnrichRequest
from .service import intelligence_service

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
        from modules.crm.service.pipedrive_service import pipedrive_service

        async with async_session() as session:
            org = None

            if payload.pipedrive_id:
                stmt = select(Organization).where(Organization.pipedrive_id == payload.pipedrive_id)
                res = await session.execute(stmt)
                org = res.scalars().first()

            if not org and payload.cnpj:
                clean_cnpj = payload.cnpj.replace(".", "").replace("/", "").replace("-", "")
                stmt = select(Organization).where(Organization.cnpj == clean_cnpj)
                res = await session.execute(stmt)
                found_by_cnpj = res.scalars().first()
                if found_by_cnpj:
                    org = found_by_cnpj

            if not org and payload.name:
                stmt = select(Organization).where(func.lower(Organization.name) == payload.name.lower())
                res = await session.execute(stmt)
                found_by_name = res.scalars().first()
                if found_by_name:
                    if not found_by_name.cnpj or (payload.cnpj and found_by_name.cnpj == payload.cnpj.replace(".", "").replace("/", "").replace("-", "")):
                        org = found_by_name

            was_manually_created = False
            target_pid = payload.pipedrive_id

            if not target_pid:
                target_pid = await pipedrive_service.create_organization({
                    "name": payload.name,
                    "address": payload.address,
                    "domain": payload.domain,
                    "cnpj": payload.cnpj
                })
                was_manually_created = True

            if not org:
                org = Organization(pipedrive_id=target_pid)
                session.add(org)
            else:
                if was_manually_created and org.pipedrive_id and org.pipedrive_id != target_pid:
                    org = Organization(pipedrive_id=target_pid)
                    session.add(org)
                else:
                    org.pipedrive_id = target_pid

            if payload.name: org.name = payload.name
            if payload.cnpj: org.cnpj = payload.cnpj.replace(".", "").replace("/", "").replace("-", "")
            if payload.domain: org.domain = payload.domain
            if payload.address: org.address = payload.address
            if payload.linkedin_url: org.linkedin_url = payload.linkedin_url
            if payload.logo_url: org.logo_url = payload.logo_url

            await session.commit()
            await session.refresh(org)

            if payload.partners:
                await session.execute(delete(Employee).where(Employee.company_id == org.id, Employee.department == "Quadro de Sócios (QSA)"))
                for p in payload.partners:
                    new_p = Employee(
                        name=p.get("name"),
                        role=p.get("role", "Sócio"),
                        department="Quadro de Sócios (QSA)",
                        seniority=6,
                        company_id=org.id
                    )
                    session.add(new_p)
                await session.commit()

            if target_pid:
                await pipedrive_service.update_organization(target_pid, {
                    "address": payload.address,
                    "domain": payload.domain,
                    "cnpj": payload.cnpj,
                    "linkedin_url": payload.linkedin_url,
                    "logo_url": payload.logo_url,
                    "name": payload.name
                })

            return {
                "status": "success",
                "message": f"Organização '{payload.name}' mapeada e sincronizada com sucesso.",
                "local_id": org.id,
                "pipedrive_id": target_pid
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
