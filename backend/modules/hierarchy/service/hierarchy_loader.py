"""
Carregamento de hierarquias salvas no banco com resolução de IDs efêmeros.
"""
from __future__ import annotations

import re
from typing import List

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from models import Employee, Organization
from .filters import get_seniority_level, get_department_tag


async def get_stored_hierarchy(org_id: int, db: AsyncSession) -> dict:
    """Carrega hierarquia completa do banco com resolução de IDs e manager_ids."""
    res_org = await db.execute(select(Organization).where(Organization.id == org_id))
    org = res_org.scalars().first()
    if not org:
        return None

    res_emp = await db.execute(
        select(Employee)
        .where(
            Employee.company_id == org_id,
            or_(Employee.role.is_(None), Employee.role != "Reprovado"),
            or_(Employee.department.is_(None), Employee.department != "Reprovado")
        )
        .order_by(Employee.seniority.desc())
    )
    employees = res_emp.scalars().all()

    nodes = [{"id": "root_company", "name": org.name, "role": "Entidade Principal",
              "department": "Supply Chain (Matriz)", "manager_id": None, "level": 0,
              "company_logo": org.logo_url, "logo": org.logo_url, "domain": org.domain,
              "cnpj": org.cnpj, "linkedin": org.linkedin_url}]

    if not employees:
        # Tenta buscar sócios do QSA como fallback mínimo antes de dar empresa como vazia
        res_qsa = await db.execute(
            select(Employee)
            .where(Employee.company_id == org_id, Employee.department == "Quadro de Sócios (QSA)")
        )
        qsa_list = res_qsa.scalars().all()
        for p in qsa_list:
            nodes.append({
                "id": f"node_{p.id}", "name": p.name, "role": p.role or "Sócio / Administrador", 
                "level": 6, "seniority": 6, "department": "Quadro de Sócios (QSA)", 
                "manager_id": "root_company", "linkedin": p.linkedin_url, "url": p.linkedin_url
            })

        return {"company_name": org.name, "nodes": nodes, "status": "cached" if len(nodes) > 1 else "empty"}

    id_mapping: dict = {}

    for emp in employees:
        new_id = f"node_{emp.id}"
        if emp.linkedin_url and "/in/" in emp.linkedin_url:
            username = re.sub(r"[^a-zA-Z0-9]", "_", emp.linkedin_url.split("/in/")[-1].split("?")[0].rstrip("/"))
            id_mapping[f"node_{username}"] = new_id
        clean_name = re.sub(r"[^a-zA-Z0-9]", "_", emp.name.lower())
        id_mapping[f"socio_{clean_name}"] = new_id

    for emp in employees:
        new_id = f"node_{emp.id}"
        level = emp.seniority if emp.seniority > 0 else await get_seniority_level(emp.role)

        manager_id = emp.manager_id
        if not manager_id or manager_id == "None":
            manager_id = "root_company"
        elif manager_id in id_mapping:
            manager_id = id_mapping[manager_id]
        elif "/" in str(manager_id) or "?" in str(manager_id):
            clean_m = f"node_{re.sub(r'[^a-zA-Z0-9]', '_', str(manager_id).split('/in/')[-1].split('?')[0].rstrip('/'))}"
            manager_id = id_mapping.get(clean_m, "root_company")

        clean_email = emp.email
        if clean_email and clean_email.endswith("@") and org.domain:
            clean_email = f"{clean_email}{org.domain}"

        nodes.append({
            "id": new_id, "name": emp.name, "role": emp.role, 
            "level": 6 if emp.department == "Quadro de Sócios (QSA)" else level, 
            "seniority": 6 if emp.department == "Quadro de Sócios (QSA)" else level,
            "department": await get_department_tag(emp.role), "manager_id": manager_id,
            "linkedin": emp.linkedin_url, "url": emp.linkedin_url, "profile_pic": emp.profile_pic,
            "email": clean_email, "education": emp.education, "observations": emp.description,
            "evidence": emp.evidence, "matching_score": emp.matching_score,
            "location": emp.location, "phone": emp.phone, "headline": emp.headline,
            "whatsapp_number": emp.whatsapp_number, "temperature": emp.temperature,
            "pipedrive_id": int(emp.pipedrive_id) if emp.pipedrive_id and emp.pipedrive_id.isdigit() else emp.pipedrive_id, "source": emp.source,
        })

    return {"company_name": org.name, "nodes": nodes, "status": "cached"}


async def get_stored_hierarchy_by_pipedrive(pipedrive_id: int, db: AsyncSession) -> dict:
    """Carrega hierarquia pelo ID do Pipedrive (com fallback para ID local)."""
    res = await db.execute(select(Organization).where(Organization.pipedrive_id == pipedrive_id))
    org = res.scalars().first()

    if not org:
        res_local = await db.execute(select(Organization).where(Organization.id == pipedrive_id))
        org = res_local.scalars().first()

    if not org:
        return {"nodes": [], "company_name": "Nao encontrada", "status": "new"}

    return await get_stored_hierarchy(org.id, db)
