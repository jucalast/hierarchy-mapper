from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from services.pipedrive.pipedrive_service import pipedrive_service
from core.database import get_db

router = APIRouter()

@router.post("/pipedrive_sync")
async def pipedrive_sync_endpoint():
    """Endpoint para mover tarefas atrasadas para hoje."""
    try:
        return await pipedrive_service.sync_overdue_activities()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pipedrive_smart_sync")
async def pipedrive_smart_sync_endpoint():
    """Endpoint para remanejar tarefas de forma inteligente (10/dia + prioridade)."""
    try:
        return await pipedrive_service.smart_reschedule_activities()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pipedrive/organizations")
async def get_pipedrive_organizations():
    """Retorna lista de todas as empresas do Pipedrive."""
    try:
        return await pipedrive_service.list_organizations()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/pipedrive/organizations/{org_id}")
async def update_pipedrive_org(org_id: int, payload: Dict[str, Any]):
    """Atualiza dados reais no Pipedrive (CNPJ, Domínio, Endereço etc)."""
    try:
        success = await pipedrive_service.update_organization(org_id, payload)
        if success:
            return {"status": "success", "message": f"Organização {org_id} atualizada no Pipedrive."}
        else:
            raise Exception("Erro ao atualizar no Pipedrive.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
