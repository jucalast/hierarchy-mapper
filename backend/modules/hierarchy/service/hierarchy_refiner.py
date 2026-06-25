"""
Refinamento de hierarquia via IA (Groq) com persistência no banco.
"""
from __future__ import annotations

from typing import List

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Employee
from core.external.groq_service import refine_hierarchy_ai
from core.infra.redis_config import redis_client
from core.observability.logging_config import get_logger
from .filters import get_seniority_level, is_same_person

log = get_logger(__name__)


async def refine_and_persist(employees: List[dict], db: AsyncSession) -> dict:
    """Usa Groq AI para reavaliar cargos/hierarquia e persiste no banco."""
    raw_nodes = [e for e in employees if e.get("id") not in ["root_company", "aviso"]]
    if not raw_nodes:
        return {"nodes": employees}

    refined_map = await refine_hierarchy_ai(raw_nodes)
    if not refined_map:
        return {"nodes": employees}

    ref_dict = {r["id"]: r for r in refined_map}

    # 1. Identificar org_id de forma robusta
    org_id = None
    
    # Tenta achar org_id por algum nó que já tenha correspondência direta no banco
    for node in employees:
        if node.get("id") in ["root_company", "aviso"]:
            continue
        stmt = select(Employee)
        if node.get("linkedin"):
            stmt = stmt.where(Employee.linkedin_url == node.get("linkedin"))
        else:
            stmt = stmt.where(Employee.name == node.get("name"), Employee.role == node.get("role"))
        res = await db.execute(stmt)
        emp_db = res.scalars().first()
        if emp_db:
            org_id = emp_db.company_id
            break

    # Se não achou, tenta pelo nome/domínio da root_company
    if not org_id:
        root_node = next((n for n in employees if n.get("id") == "root_company"), None)
        if root_node:
            brand_name = root_node.get("name") or root_node.get("company")
            if brand_name:
                from sqlalchemy import func
                from models import Organization
                stmt_org = select(Organization).where(
                    (func.lower(Organization.name) == brand_name.lower()) |
                    (Organization.domain == root_node.get("domain"))
                )
                res_org = await db.execute(stmt_org)
                org = res_org.scalars().first()
                if org:
                    org_id = org.id

    # 🔒 Lock distribuído: evita que dois refinamentos concorrentes na mesma org
    # (ex: discovery e scan terminando quase ao mesmo tempo) façam o DELETE total
    # um por cima do outro. Se não conseguir o lock, segue sem tocar o banco —
    # apenas retorna a sugestão da IA para exibição (mesmo fallback de org_id=None).
    lock_key = f"hierarchy_refine_lock_{org_id}" if org_id else None
    lock_acquired = True
    if lock_key and redis_client:
        try:
            lock_acquired = bool(await asyncio.to_thread(redis_client.set, lock_key, "1", nx=True, ex=120))
        except Exception as e:
            log.warning("hierarchy.refine.lock_check_failed", error=str(e))
            lock_acquired = True
        if not lock_acquired:
            log.info("hierarchy.refine.skipped_concurrent", org_id=org_id)
            org_id = None

    # 2. Carrega todos os funcionários existentes da organização para correspondência fuzzy na memória
    if org_id:
        from sqlalchemy import delete, and_, not_, or_
        # 🔥 LIMPEZA TOTAL ANTES DE PERSISTIR: Remove tudo da empresa para garantir que o refinamento atual seja a única verdade
        # Preservamos apenas decisões manuais reais.
        await db.execute(
            delete(Employee).where(
                and_(
                    Employee.company_id == org_id,
                    Employee.role.notin_(["Análise Humana", "Não Identificado", "Erro no Processamento", "Professional"])
                )
            )
        )
        await db.commit()
        
        # Agora buscamos o que sobrou (provavelmente nada se for um novo scan limpo)
        res_all = await db.execute(select(Employee).where(Employee.company_id == org_id))
        all_db_emps = res_all.scalars().all()
    else:
        all_db_emps = []

    def is_real_linkedin(url):
        return url and "linkedin.com/in/" in url and "pd_" not in url and "pipedrive_" not in url

    def find_matching_db_emp(node):
        # 1. Match por LinkedIn real
        node_li = node.get("linkedin") or node.get("url")
        if is_real_linkedin(node_li):
            for emp in all_db_emps:
                if emp.linkedin_url == node_li:
                    return emp
        
        # 2. Match por Nome fuzzy
        node_name = node.get("name")
        if node_name:
            for emp in all_db_emps:
                if is_same_person(emp.name, node_name):
                    return emp
                    
        return None

    # Mapeamento de IDs efêmeros → IDs estáveis do banco
    ephemeral_to_db_id: dict = {}
    from .filters import get_department_tag

    # 3. Faz o match dos nós existentes ou insere novos no banco
    for node in employees:
        original_id = node.get("id")
        if original_id in ["root_company", "aviso"]:
            continue

        emp_db = find_matching_db_emp(node)
        if emp_db:
            # Vincula ID estável do banco
            ephemeral_to_db_id[original_id] = f"node_{emp_db.id}"
            
            # Enriquece/conecta com Pipedrive contact
            node_li = node.get("linkedin") or node.get("url")
            if is_real_linkedin(node_li) and (not emp_db.linkedin_url or "pipedrive_" in emp_db.linkedin_url or "pd_" in emp_db.linkedin_url):
                emp_db.linkedin_url = node_li
            # Atualiza foto se a do banco for nula, vazia ou inválida
            db_pic = emp_db.profile_pic
            new_pic = node.get("avatar") or node.get("profile_pic")
            if new_pic and (not db_pic or db_pic.startswith("data:image") or "ghost-person" in db_pic):
                emp_db.profile_pic = new_pic
            if not emp_db.location and node.get("location"):
                emp_db.location = node.get("location")
            if not emp_db.headline and node.get("headline"):
                emp_db.headline = node.get("headline")
            if emp_db.role in ["Contato no Pipedrive", None, ""] and node.get("role"):
                emp_db.role = node.get("role")
                emp_db.department = await get_department_tag(node.get("role"))
                
            # Enriquece novos metadados extraídos
            if not emp_db.description and (node.get("observations") or node.get("description")):
                emp_db.description = node.get("observations") or node.get("description")
            if not emp_db.evidence and node.get("evidence"):
                emp_db.evidence = node.get("evidence")
            if not emp_db.education and node.get("education"):
                emp_db.education = node.get("education")
            if not emp_db.matching_score and node.get("matching_score"):
                emp_db.matching_score = node.get("matching_score")
        else:
            # Novo funcionário do LinkedIn Scan. Persiste no banco de dados.
            if org_id:
                node_li = node.get("linkedin") or node.get("url")
                final_li = node_li if is_real_linkedin(node_li) else f"scan_{org_id}_{original_id}"
                
                new_emp = Employee(
                    name=node.get("name"),
                    role=node.get("role", "Professional"),
                    department=await get_department_tag(node.get("role", "")),
                    seniority=node.get("level", 2),
                    linkedin_url=final_li,
                    profile_pic=node.get("avatar"),
                    location=node.get("location"),
                    company_id=org_id,
                    source="discovery",
                    is_discovery=1,
                    description=node.get("observations") or node.get("description"),
                    evidence=node.get("evidence"),
                    education=node.get("education"),
                    matching_score=node.get("matching_score"),
                    headline=node.get("headline")
                )
                db.add(new_emp)
                await db.flush() # Gera o id para mapear o nó efêmero
                
                ephemeral_to_db_id[original_id] = f"node_{new_emp.id}"
                all_db_emps.append(new_emp)

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

            # 4. Atualiza hierarquia e seniority de cada registro no banco
            node_stable_id = ephemeral_to_db_id.get(original_id)
            db_emp = None
            if node_stable_id and node_stable_id.startswith("node_"):
                db_emp_id = int(node_stable_id.split("_")[1])
                db_emp = next((e for e in all_db_emps if e.id == db_emp_id), None)

            if not db_emp:
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

        # Garante que os dados de enriquecimento salvos no banco retornem ao frontend
        node_stable_id = ephemeral_to_db_id.get(original_id)
        db_emp_to_read = None
        if node_stable_id and node_stable_id.startswith("node_"):
            db_emp_id = int(node_stable_id.split("_")[1])
            db_emp_to_read = next((e for e in all_db_emps if e.id == db_emp_id), None)
            
        if db_emp_to_read:
            best_pic = db_emp_to_read.profile_pic
            if not best_pic or best_pic.startswith("data:image") or "ghost-person" in best_pic:
                best_pic = node.get("avatar") or node.get("profile_pic")
            node["profile_pic"] = best_pic
            node["avatar"] = best_pic
            node["location"] = db_emp_to_read.location or node.get("location")
            node["observations"] = db_emp_to_read.description or node.get("observations")
            node["evidence"] = db_emp_to_read.evidence or node.get("evidence")
            node["education"] = db_emp_to_read.education or node.get("education")

        updated_nodes.append(node)

    if org_id:
        await db.commit()

    if lock_key and redis_client and lock_acquired:
        try:
            await asyncio.to_thread(redis_client.delete, lock_key)
        except Exception:
            pass

    return {"nodes": updated_nodes}

