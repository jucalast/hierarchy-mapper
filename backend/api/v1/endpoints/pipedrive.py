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

@router.get("/pipedrive/organizations/{org_id}/details")
async def get_org_details(org_id: int):
    """Retorna o 360 da empresa: Tarefas, contatos, negócios e notas."""
    try:
        return await pipedrive_service.get_organization_details(org_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pipedrive/organizations/{org_id}/reset")
async def reset_org_data(org_id: int, db: AsyncSession = Depends(get_db)):
    """Reseta todos os dados salvos de uma empresa (CNPJ, domínio, logo, LinkedIn, parceiros) e limpa cache."""
    try:
        from models.organization import Organization
        from models.employee import Employee
        from core.redis_config import redis_client
        import json
        
        # Buscar a organização no banco
        result = await db.execute(
            __import__('sqlalchemy').select(Organization).where(Organization.pipedrive_id == org_id)
        )
        org = result.scalar()
        
        if org:
            # 🗑️ DELETAR TODOS OS EMPLOYEES DA ORGANIZAÇÃO (limpar hierarquia completamente)
            employees_result = await db.execute(
                __import__('sqlalchemy').delete(Employee).where(Employee.company_id == org.id)
            )
            deleted_employees = employees_result.rowcount
            print(f"[Reset] Deletados {deleted_employees} employees da organização {org_id}")
            
            # Resetar TODOS os campos da organização no banco
            org.cnpj = None
            org.domain = None
            org.logo_url = None
            org.linkedin_url = None
            org.partners = None
            org.intelligence_data = None
            org.updated_at = __import__('datetime').datetime.utcnow()
            
            await db.commit()
            
            # 🗑️ Limpar cache Redis relacionado à organização
            deleted_count = 0
            try:
                if redis_client:
                    # Padrões de cache que precisam ser limpos
                    patterns = [
                        f"org:{org_id}:*",
                        f"hierarchy:{org_id}:*",
                        f"intelligence:{org_id}:*",
                        f"brand:*:{org_id}:*",
                        f"stored-hierarchy:{org_id}",
                        f"org-{org_id}:*",
                        f"*:{org_id}:*",  # Catch-all pattern
                    ]
                    
                    for pattern in patterns:
                        try:
                            # Usar SCAN para iterar sobre chaves de forma segura
                            cursor = 0
                            while True:
                                cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
                                if keys:
                                    deleted = redis_client.delete(*keys)
                                    deleted_count += deleted
                                    print(f"[Redis] {pattern}: Deletadas {len(keys)} chaves")
                                if cursor == 0:
                                    break
                        except Exception as e:
                            print(f"Aviso ao limpar padrão {pattern}: {e}")
                    
                    # Flush completo das imagens em cache (mais agressivo)
                    try:
                        redis_client.delete(f"image-cache:{org_id}")
                        redis_client.delete(f"logo-cache:{org_id}")
                    except:
                        pass
                        
            except Exception as e:
                print(f"Erro ao limpar cache Redis: {e}")
            
            return {
                "status": "success",
                "message": f"Todos os dados e cache da empresa {org_id} foram resetados.",
                "employees_deleted": deleted_employees,
                "redis_deleted": deleted_count,
                "organization_id": org_id
            }
        else:
            raise HTTPException(status_code=404, detail=f"Organização {org_id} não encontrada.")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pipedrive/organizations/{org_id}/rename")
async def rename_org(org_id: int, payload: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    """Renomeia uma empresa tanto no Pipedrive quanto no banco local."""
    try:
        from models.organization import Organization
        from sqlalchemy import select
        
        new_name = payload.get("name", "").strip()
        
        if not new_name:
            raise HTTPException(status_code=400, detail="Nome não pode estar vazio.")
        
        # Buscar organização no banco
        result = await db.execute(
            select(Organization).where(Organization.pipedrive_id == org_id)
        )
        org = result.scalar()
        
        if not org:
            raise HTTPException(status_code=404, detail=f"Organização {org_id} não encontrada.")
        
        # Atualizar nome no Pipedrive via API
        try:
            await pipedrive_service.update_organization(org_id, {"name": new_name})
            print(f"[Rename] Empresa {org_id} renomeada para '{new_name}' no Pipedrive")
        except Exception as e:
            print(f"[Rename] ⚠️ Aviso ao atualizar Pipedrive: {e}")
        
        # Atualizar nome no banco local
        org.name = new_name
        await db.commit()
        
        return {
            "status": "success",
            "message": f"Empresa renomeada com sucesso para '{new_name}'.",
            "organization_id": org_id,
            "new_name": new_name
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
