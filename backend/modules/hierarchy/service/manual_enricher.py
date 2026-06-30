"""
modules.hierarchy.service.manual_enricher
=========================================
Lógica para enriquecimento manual de perfis via copy-paste do LinkedIn.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Employee, Organization
from .role_engine import role_engine
from .filters import get_department_tag, get_seniority_level
from .candidate_service import resolve_employee_by_node_id


from core.observability.logging_config import get_logger

log = get_logger(__name__)

async def enrich_employee_manually(employee_id: str, raw_text: str, db: AsyncSession) -> dict:
    """
    Pega o texto bruto de um perfil, extrai dados via IA e atualiza o funcionário.
    """
    log.info("manual_enricher.start", employee_id=employee_id, text_len=len(raw_text))
    emp = await resolve_employee_by_node_id(employee_id, db)
    if not emp:
        log.warning("manual_enricher.not_found", employee_id=employee_id)
        raise HTTPException(status_code=404, detail="Funcionário não encontrado.")

    # Busca a marca da empresa para dar contexto à IA
    res_org = await db.execute(select(Organization).where(Organization.id == emp.company_id))
    org = res_org.scalars().first()
    target_brand = org.name if org else ""
    log.info("manual_enricher.context_loaded", org=target_brand)

    # Chama o RoleEngine especializado em extração manual
    area_focus = "compras"
    if org and getattr(org, 'category', None):
        area_focus = org.category
    elif org and getattr(org, 'product_focus', None):
        area_focus = org.product_focus

    try:
        log.info("manual_enricher.calling_ai", tier="DEEP")
        ai_data = await role_engine.distill_manual_profile(raw_text, area_focus=area_focus, target_brand=target_brand)
        log.info("manual_enricher.ai_finished", success=bool(ai_data and not ai_data.get("error")))
    except Exception as e:
        log.exception("manual_enricher.ai_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Erro na IA: {str(e)}")
    
    if ai_data.get("error") or not ai_data.get("is_valid", True):
        raise HTTPException(status_code=422, detail=f"A IA não conseguiu processar este texto: {ai_data.get('error', 'Dados insuficientes')}")

    # Atualiza o registro no banco com os novos dados estruturados
    emp.name = ai_data.get("name") or emp.name
    emp.role = ai_data.get("role") or emp.role
    emp.department = ai_data.get("department") or emp.department
    emp.seniority = ai_data.get("seniority") or emp.seniority
    emp.headline = ai_data.get("headline") or emp.headline
    emp.description = ai_data.get("observations") or emp.description
    emp.education = ai_data.get("education") or emp.education
    emp.location = ai_data.get("location") or emp.location
    
    # Se o cargo mudou, recalculamos depto e senioridade se eles vieram vazios da IA
    if not ai_data.get("department"):
        emp.department = await get_department_tag(emp.role)
    if not ai_data.get("seniority"):
        emp.seniority = await get_seniority_level(emp.role)

    await db.commit()
    await db.refresh(emp)

    return {
        "status": "success",
        "message": f"Perfil de {emp.name} atualizado com sucesso.",
        "employee": {
            "id": f"node_{emp.id}",
            "name": emp.name,
            "role": emp.role,
            "department": emp.department,
            "seniority": emp.seniority,
            "headline": emp.headline,
            "observations": emp.description,
            "education": emp.education,
            "location": emp.location,
            "matching_score": 100 # Consideramos 100% pois foi input manual/IA focado
        }
    }


async def update_employee_details(employee_id: str, updates: dict, db: AsyncSession) -> dict:
    """
    Atualiza manualmente os detalhes de um funcionário no banco.
    """
    emp = await resolve_employee_by_node_id(employee_id, db)
    if not emp:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado.")

    # Mapeamento de campos do schema para o model
    field_map = {
        "name": "name",
        "role": "role",
        "department": "department",
        "level": "seniority",
        "email": "email",
        "phone": "phone",
        "linkedin": "linkedin_url",
        "location": "location",
        "observations": "description",
        "education": "education"
    }

    for schema_field, model_field in field_map.items():
        if schema_field in updates and updates[schema_field] is not None:
            setattr(emp, model_field, updates[schema_field])

    # Email descoberto via ferramenta = verificado
    if "email" in updates and updates["email"]:
        emp.email_verified = True

    await db.commit()
    await db.refresh(emp)

    return {"status": "success", "message": f"Dados de {emp.name} salvos com sucesso."}
