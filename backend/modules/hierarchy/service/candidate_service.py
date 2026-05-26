"""
Lógica de aprovação/rejeição de candidatos em análise humana.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Employee
from .filters import get_department_tag


async def resolve_employee_by_node_id(node_id: str, db: AsyncSession) -> Employee | None:
    """Resolve um node_id efêmero (node_123, node_username, partner_123) para um Employee do banco."""
    if "_" in str(node_id) and (str(node_id).startswith("node_") or str(node_id).startswith("partner_")):
        parts = str(node_id).split("_")
        if parts[1].isdigit():
            res = await db.execute(select(Employee).where(Employee.id == int(parts[1])))
            return res.scalars().first()
        else:
            username = "_".join(parts[1:])
            res = await db.execute(select(Employee).where(Employee.linkedin_url.contains(username)))
            return res.scalars().first()

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
        if emp.role == "Análise Humana":
            emp.role = emp.headline or "Colaborador"
            emp.department = await get_department_tag(emp.role)
        await db.commit()
        return {"status": "success", "message": f"Candidato {emp.name} aprovado."}

    elif action == "reject":
        emp.role = "Reprovado"
        emp.department = "Reprovado"
        emp.seniority = -1
        await db.commit()
        return {"status": "success", "message": f"Candidato {emp.name} marcado como reprovado no banco."}

    raise HTTPException(status_code=400, detail="Ação inválida. Use 'approve' ou 'reject'.")
