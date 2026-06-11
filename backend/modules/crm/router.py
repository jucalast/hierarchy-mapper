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
from core.observability.logging_config import get_logger

log = get_logger(__name__)

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
    """Endpoint para remanejar tarefas de forma inteligente (em background)"""
    try:
        from arq import create_pool
        from core.infra.redis_config import redis_settings
        
        redis = await create_pool(redis_settings)
        job = await redis.enqueue_job("run_smart_reschedule_task")
        
        return {
            "status": "queued", 
            "message": "Sincronização inteligente iniciada em background. Você pode fechar ou continuar usando a plataforma.",
            "job_id": job.job_id
        }
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

@router.delete("/pipedrive/activities/{activity_id}")
async def delete_pipedrive_activity(activity_id: int):
    """Deleta uma atividade no Pipedrive."""
    try:
        success = await pipedrive_service.delete_activity(activity_id)
        if success:
            return {"status": "success", "message": f"Atividade {activity_id} deletada do Pipedrive."}
        raise Exception("Erro ao deletar atividade no Pipedrive.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/pipedrive/notes/{note_id}")
async def delete_pipedrive_note(note_id: int):
    """Deleta uma nota no Pipedrive."""
    try:
        success = await pipedrive_service.delete_note(note_id)
        if success:
            return {"status": "success", "message": f"Nota {note_id} deletada do Pipedrive."}
        raise Exception("Erro ao deletar nota no Pipedrive.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipedrive/pipeline/board")
async def get_pipeline_board():
    """Retorna estágios e negócios para o Kanban."""
    try:
        res = await pipedrive_service.get_pipeline_board()
        if res.get("success"):
            return res.get("data")
        raise HTTPException(status_code=500, detail=res.get("error", "Erro ao buscar pipeline board"))
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


@router.post("/pipedrive/persons")
async def create_pipedrive_person(payload: Dict[str, Any]):
    """Cria uma nova pessoa no Pipedrive."""
    try:
        res = await pipedrive_service.create_person(
            name=payload.get("name"),
            email=payload.get("email"),
            phone=payload.get("phone"),
            org_id=payload.get("org_id")
        )
        if res and res.get("success") is not False:
            return {"status": "success", "message": "Pessoa criada no Pipedrive com sucesso.", "data": res.get("data")}
        raise Exception("Erro ao criar pessoa no Pipedrive.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/pipedrive/persons/{person_id}")
async def update_pipedrive_person(person_id: int, payload: Dict[str, Any]):
    """Atualiza uma pessoa no Pipedrive."""
    try:
        success = await pipedrive_service.update_person(person_id, payload)
        if success:
            return {"status": "success", "message": "Pessoa atualizada no Pipedrive com sucesso."}
        raise Exception("Erro ao atualizar pessoa no Pipedrive.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/pipedrive/persons/{person_id}")
async def delete_pipedrive_person(person_id: int):
    """Deleta uma pessoa do Pipedrive."""
    try:
        success = await pipedrive_service.delete_person(person_id)
        if success:
            return {"status": "success", "message": "Pessoa deletada do Pipedrive com sucesso."}
        raise Exception("Erro ao deletar pessoa no Pipedrive.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/pipedrive/current-user")
async def get_current_user():
    """Retorna o nome e avatar do usuário logado do Pipedrive."""
    try:
        users_map = await pipedrive_service.get_users_map()
        users_pics_map = await pipedrive_service.get_users_pics_map()
        user_id = pipedrive_service.user_id # e.g. 24921888
        
        log.info(f"Buscando usuário atual: ID={user_id}. Disponíveis: {list(users_map.keys())}")
        
        name = users_map.get(user_id, "João Luccas")
        avatar = users_pics_map.get(user_id)
        
        # Se por algum motivo o user_id configurado não estiver no cache, pega o primeiro que combine com João ou o primeiro da lista
        if not avatar and users_pics_map:
            log.info("Avatar não encontrado pelo ID, tentando busca por nome 'João'...")
            for uid, pic in users_pics_map.items():
                uname = users_map.get(uid, "")
                if "joao" in uname.lower() or "joão" in uname.lower():
                    name = uname
                    avatar = pic
                    log.info(f"Encontrado fallback por nome: {name}, ID={uid}")
                    break
            else:
                # Fallback para o primeiro com foto
                log.info("Fallback por nome falhou, pegando primeiro usuário com foto disponível.")
                for uid, pic in users_pics_map.items():
                    if pic:
                        name = users_map.get(uid, name)
                        avatar = pic
                        log.info(f"Encontrado fallback genérico: {name}, ID={uid}")
                        break
                        
        log.info(f"Resultado final get_current_user: {name}, avatar={'sim' if avatar else 'não'}")
        
        # Sincroniza com o banco local
        from core.infra.database import async_session
        from models import User, Tenant
        async with async_session() as db_sess:
            # Tenta pegar o tenant_id do primeiro tenant se não soubermos
            tenant_res = await db_sess.execute(select(Tenant).limit(1))
            tenant = tenant_res.scalars().first()
            t_id = tenant.id if tenant else None

            user_stmt = select(User).where(User.name.ilike(f"%{name}%")).limit(1)
            user_res = await db_sess.execute(user_stmt)
            db_user = user_res.scalars().first()
            
            if db_user:
                if avatar and db_user.avatar != avatar:
                    log.info(f"Sincronizando avatar para usuário {db_user.name} no banco local.")
                    db_user.avatar = avatar
                    await db_sess.commit()
            elif t_id:
                # Cria usuário se não existir (raro, mas evita erro)
                new_user = User(
                    tenant_id=t_id,
                    name=name,
                    email=f"{name.lower().replace(' ', '.')}@empresa.com.br",
                    avatar=avatar,
                    user_role="seller"
                )
                db_sess.add(new_user)
                await db_sess.commit()

        return {"id": user_id, "name": name, "avatar": avatar}
    except Exception as e:
        log.error(f"Erro em get_current_user: {e}")
        return {"id": None, "name": "João Luccas", "avatar": None}

