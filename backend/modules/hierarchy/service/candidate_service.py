"""
Lógica de aprovação/rejeição de candidatos em análise humana.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Employee
from .filters import get_department_tag, get_seniority_level


async def resolve_employee_by_node_id(node_id: str, db: AsyncSession) -> Employee | None:
    """Resolve um node_id efêmero (node_123, node_username, partner_123) para um Employee do banco."""
    id_str = str(node_id)
    if "pd_" in id_str or "pipedrive_" in id_str:
        import re
        m = re.search(r'\d+', id_str)
        if m:
            pd_id = m.group(0)
            res = await db.execute(select(Employee).where(Employee.pipedrive_id == pd_id))
            emp = res.scalars().first()
            if emp:
                return emp
            
            res = await db.execute(select(Employee).where(Employee.linkedin_url.contains(pd_id)))
            emp = res.scalars().first()
            if emp:
                return emp

    if "_" in id_str and (id_str.startswith("node_") or id_str.startswith("partner_")):
        parts = id_str.split("_")
        if parts[1].isdigit():
            res = await db.execute(select(Employee).where(Employee.id == int(parts[1])))
            return res.scalars().first()
        else:
            username = "_".join(parts[1:])
            res = await db.execute(select(Employee).where(Employee.linkedin_url.contains(username)))
            emp = res.scalars().first()
            if emp:
                return emp
            
            if username.startswith("pd_"):
                alt_username = username.replace("pd_", "pipedrive_")
                res = await db.execute(select(Employee).where(Employee.linkedin_url.contains(alt_username)))
                emp = res.scalars().first()
                if emp:
                    return emp

    try:
        res = await db.execute(select(Employee).where(Employee.id == int(node_id)))
        return res.scalars().first()
    except (ValueError, TypeError):
        return None


async def process_candidate_action(employee_id: str, action: str, db: AsyncSession) -> dict:
    """Aprova ou rejeita um candidato em análise humana."""
    emp = await resolve_employee_by_node_id(employee_id, db)
    if not emp:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado.")

    if action == "approve":
        # Se o cargo atual for Análise Humana, tentamos restaurar um cargo real
        if emp.role == "Análise Humana":
            new_role = emp.headline or "Colaborador"
            # Se o headline também for Análise Humana (loop de erro), forçamos Colaborador
            if not new_role or "análise humana" in new_role.lower():
                new_role = "Colaborador"
            
            emp.role = new_role
            emp.department = await get_department_tag(emp.role)
            emp.seniority = await get_seniority_level(emp.role)
            
        await db.commit()
        return {"status": "success", "message": f"Candidato {emp.name} aprovado e movido para {emp.role}."}

    elif action == "reject":
        emp.role = "Reprovado"
        emp.department = "Reprovado"
        emp.seniority = -1
        await db.commit()
        return {"status": "success", "message": f"Candidato {emp.name} marcado como reprovado no banco."}

    raise HTTPException(status_code=400, detail="Ação inválida. Use 'approve' ou 'reject'.")
