"""
modules.crm.router
==================
Endpoints de sincronizacao CRM com Pipedrive.

Inclui protecao contra rate limit (cooldown detectado antes do sync)
e smart reschedule de atividades vencidas por stage queue.

Rotas:
    POST /pipedrive_sync       -> sync completo (orgs + atividades)
    POST /pipedrive_smart_sync -> reagendamento inteligente por etapa
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from core.infra.database import get_db
from .service import pipedrive_service

router = APIRouter()


@router.post("/pipedrive_sync")
async def pipedrive_sync_endpoint():
    """Endpoint para sincronização completa: Organizações e Atividades."""
    cooldown = pipedrive_service.get_retry_after_seconds()
    if cooldown > 0:
        return {"status": "rate_limited", "retry_after_seconds": cooldown}
    try:
        org_sync = await pipedrive_service.sync_all_parallel()
        act_sync = await pipedrive_service.sync_overdue_activities()
        return {"status": "success", "organizations": org_sync, "activities": act_sync}
    except Exception as e:
        err = str(e)
        if "cooldown" in err.lower() or "rate limit" in err.lower():
            return {"status": "rate_limited", "detail": err}
        raise HTTPException(status_code=500, detail=err)


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
    cooldown = pipedrive_service.get_retry_after_seconds()
    if cooldown > 0:
        return []
    try:
        return await pipedrive_service.list_organizations()
    except Exception as e:
        err = str(e)
        if "cooldown" in err.lower() or "rate limit" in err.lower():
            return []
        raise HTTPException(status_code=500, detail=err)


@router.get("/pipedrive/activities/pending-summary")
async def get_pending_activities_summary():
    """Resumo leve de tarefas pendentes por empresa."""
    try:
        sao_paulo_tz = timezone(timedelta(hours=-3))
        today = datetime.now(sao_paulo_tz).date().isoformat()

        r = await pipedrive_service.make_request(
            "GET", f"activities?user_id={pipedrive_service.user_id}&done=0&limit=500"
        )
        if not r or r.status_code != 200:
            return []

        activities = r.json().get("data") or []
        org_map: dict = {}
        for act in activities:
            due = act.get("due_date")
            if not due or not act.get("deal_id"):
                continue
            raw_org = act.get("org_id")
            if isinstance(raw_org, dict):
                org_id = raw_org.get("value")
                org_name = raw_org.get("name", "")
            else:
                org_id = raw_org
                org_name = act.get("org_name", "")
            if not org_id:
                continue
            if org_id not in org_map:
                org_map[org_id] = {"org_id": org_id, "org_name": org_name, "next_due_date": due, "overdue_count": 0, "pending_count": 0}
            entry = org_map[org_id]
            entry["pending_count"] += 1
            if due < today:
                entry["overdue_count"] += 1
            if due < entry["next_due_date"]:
                entry["next_due_date"] = due
        return list(org_map.values())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pipedrive/organizations/{org_id}")
async def update_pipedrive_org(org_id: int, payload: Dict[str, Any]):
    """Atualiza dados reais no Pipedrive."""
    try:
        success = await pipedrive_service.update_organization(org_id, payload)
        if success:
            return {"status": "success", "message": f"Organização {org_id} atualizada no Pipedrive."}
        raise Exception("Erro ao atualizar no Pipedrive.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pipedrive/activities/{activity_id}")
async def update_pipedrive_activity(activity_id: int, payload: Dict[str, Any]):
    """Atualiza dados de uma atividade no Pipedrive (ex: marcar como concluída)."""
    try:
        success = await pipedrive_service.update_activity(activity_id, payload)
        if success:
            return {"status": "success", "message": f"Atividade {activity_id} atualizada no Pipedrive."}
        raise Exception("Erro ao atualizar atividade no Pipedrive.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipedrive/organizations/{org_id}/details")
async def get_org_details(org_id: int):
    """Retorna o 360 da empresa: Tarefas, contatos, negócios e notas."""
    cooldown = pipedrive_service.get_retry_after_seconds()
    if cooldown > 0:
        raise HTTPException(status_code=429, detail=f"Pipedrive em cooldown. Tente em {cooldown}s")
    try:
        return await pipedrive_service.get_organization_details(org_id)
    except Exception as e:
        err = str(e)
        if "cooldown" in err.lower() or "rate limit" in err.lower():
            raise HTTPException(status_code=429, detail=err)
        raise HTTPException(status_code=500, detail=err)


@router.post("/pipedrive/organizations/{org_id}/reset")
async def reset_org_data(org_id: int, db: AsyncSession = Depends(get_db)):
    """Reseta todos os dados salvos de uma empresa e limpa cache."""
    try:
        from models.organization.organization import Organization
        from models.people.employee import Employee
        from core.infra.redis_config import redis_client
        from sqlalchemy import delete as sa_delete

        result = await db.execute(select(Organization).where(Organization.pipedrive_id == org_id))
        org = result.scalar()

        if not org:
            raise HTTPException(status_code=404, detail=f"Organização {org_id} não encontrada.")

        employees_result = await db.execute(sa_delete(Employee).where(Employee.company_id == org.id))
        deleted_employees = employees_result.rowcount or 0

        org.cnpj = None
        org.domain = None
        org.logo_url = None
        org.linkedin_url = None
        org.partners = None
        org.intelligence_data = None
        org.updated_at = datetime.utcnow()
        await db.commit()

        deleted_count = 0
        try:
            if redis_client:
                patterns = [f"org:{org_id}:*", f"hierarchy:{org_id}:*", f"intelligence:{org_id}:*", f"*:{org_id}:*"]
                for pattern in patterns:
                    cursor = 0
                    while True:
                        cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
                        if keys:
                            deleted_count += redis_client.delete(*keys)
                        if cursor == 0:
                            break
        except Exception:
            pass

        return {"status": "success", "message": f"Dados da empresa {org_id} resetados.", "employees_deleted": deleted_employees, "redis_deleted": deleted_count}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/pipedrive/organizations/{org_id}")
async def delete_pipedrive_org(org_id: int):
    """Exclui completamente a organização do Pipedrive e apaga do banco local."""
    try:
        status = await pipedrive_service.delete_organization(org_id)
        if status is True:
            return {"status": "success", "message": "Organização excluída do Pipedrive e do banco local."}
        elif status == "partial_success_permissions":
            return {"status": "partial_success", "message": "Empresa removida do Mapeador, mas você não tem permissão para excluí-la do Pipedrive."}
        return {"status": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
