"""
Refinamento de hierarquia via IA (Groq) com persistência no banco.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Employee
from core.external.groq_service import refine_hierarchy_ai
from .filters import get_seniority_level


async def refine_and_persist(employees: List[dict], db: AsyncSession) -> dict:
    """Usa Groq AI para reavaliar cargos/hierarquia e persiste no banco."""
    raw_nodes = [e for e in employees if e.get("id") not in ["root_company", "aviso"]]
    if not raw_nodes:
        return {"nodes": employees}

    refined_map = await refine_hierarchy_ai(raw_nodes)
    if not refined_map:
        return {"nodes": employees}

    ref_dict = {r["id"]: r for r in refined_map}

    # Mapeamento de IDs efêmeros → IDs estáveis do banco
    ephemeral_to_db_id: dict = {}
    org_id = None
    for node in employees:
        res = await db.execute(
            select(Employee).where(Employee.name == node.get("name"), Employee.role == node.get("role"))
        )
        emp_db = res.scalars().first()
        if emp_db:
            ephemeral_to_db_id[node["id"]] = f"node_{emp_db.id}"
            if not org_id:
                org_id = emp_db.company_id

    updated_nodes = []
    for node in employees:
        original_id = node.get("id")

        if original_id in ephemeral_to_db_id:
            node["id"] = ephemeral_to_db_id[original_id]

        ref_entry = ref_dict.get(original_id)
        if ref_entry:
            new_level = ref_entry.get("level", node.get("level"))
            new_manager_id = ref_entry.get("manager_id", node.get("manager_id"))

            if original_id != "root_company" and new_level == 0:
                new_level = await get_seniority_level(node.get("role", ""))

            final_manager_id = new_manager_id
            if new_manager_id in ephemeral_to_db_id:
                final_manager_id = ephemeral_to_db_id[new_manager_id]
            elif new_manager_id == "root_company":
                final_manager_id = "root_company"

            # Sócios e Root são imutáveis
            if node.get("level") == 6 or node.get("department") == "Quadro de Sócios (QSA)" or original_id == "root_company":
                new_level = node.get("level", 6)
                final_manager_id = "root_company" if original_id != "root_company" else None

            node["level"] = new_level
            node["manager_id"] = final_manager_id

            if node.get("linkedin") or node.get("name"):
                stmt = select(Employee)
                if node.get("linkedin"):
                    stmt = stmt.where(Employee.linkedin_url == node.get("linkedin"))
                else:
                    stmt = stmt.where(Employee.name == node.get("name"), Employee.role == node.get("role"))
                res = await db.execute(stmt)
                db_emp = res.scalars().first()
                if db_emp:
                    db_emp.seniority = new_level
                    db_emp.manager_id = str(final_manager_id)

        updated_nodes.append(node)

    if org_id:
        await db.commit()

    return {"nodes": updated_nodes}
