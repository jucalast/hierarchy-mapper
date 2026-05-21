"""
Router de Hierarquia — thin, delega para services.
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.infra.database import get_db
from core.config import settings
from api.v1.schemas import EmployeeNode, HierarchyResponse, CandidateActionRequest, clean_cnpj

from .service.candidate_service import process_candidate_action
from .service.hierarchy_loader import get_stored_hierarchy, get_stored_hierarchy_by_pipedrive
from .service.hierarchy_refiner import refine_and_persist
from .service.b2b_scanner import discover_employees, discover_employees_stream
from .service.filters import get_seniority_level, get_department_tag
from .service.cnpj_resolver import fetch_company_data_by_cnpj, build_full_address
from .service.org_persistence import upsert_organization, persist_socios
from .service.graph_builder import build_root_node, build_socio_nodes, assign_managers, reparent_subordinates

router = APIRouter()


@router.post("/candidate-action")
async def candidate_action(payload: CandidateActionRequest, db: AsyncSession = Depends(get_db)):
    """Aprova ou rejeita um candidato em análise humana."""
    return await process_candidate_action(payload.employee_id, payload.action, db)


@router.post("/refine")
async def refine_hierarchy(employees: List[dict], db: AsyncSession = Depends(get_db)):
    """Usa Groq AI para reavaliar cargos/hierarquia e persiste no banco."""
    return await refine_and_persist(employees, db)


@router.get("", response_model=HierarchyResponse)
async def get_company_hierarchy(
    request: Request,
    cnpj: str = Query(..., description="O CNPJ da empresa"),
    domain: Optional[str] = Query(None),
):
    """Busca dados reais da empresa via CNPJ e retorna hierarquia com sócios."""
    EMAIL_API_KEY = settings.EMAIL_API_KEY
    cnpj_clean = clean_cnpj(cnpj)
    if len(cnpj_clean) != 14:
        raise HTTPException(status_code=400, detail="CNPJ Inválido. Deve conter 14 dígitos.")

    data = await fetch_company_data_by_cnpj(cnpj_clean)
    if not data:
        raise HTTPException(status_code=502, detail="Limite de requisições excedido em todas as APIs.")

    razao_social = data.get("razao_social") or data.get("nome_fantasia") or "Empresa Desconhecida"
    qsa = data.get("qsa", [])

    nodes: List[EmployeeNode] = [EmployeeNode(
        id="root_company",
        name=razao_social[:30] + "..." if len(razao_social) > 30 else razao_social,
        role="Entidade Principal", department="Supply Chain (Matriz)",
        company=razao_social, manager_id=None, level=0,
    )]

    temp_employees = []
    for idx, socio in enumerate(qsa):
        cargo = socio.get("qualificacao_socio", "Sócio")
        temp_employees.append(EmployeeNode(
            id=f"socio_{idx}", name=socio.get("nome_socio", "Sócio Anônimo"), role=cargo,
            department="Quadro de Sócios (QSA)", company=razao_social, manager_id=None,
            level=1 if "sócio" in cargo.lower() or "administrador" in cargo.lower() else await get_seniority_level(cargo),
        ))

    raw_name = data.get("nome_fantasia") or razao_social
    search_name = re.sub(r"(?i)\b(ltda|s\.a\.|s/a|limitada|s a|sa|s\.a)\b", "", raw_name).replace("-", " ").strip() or razao_social
    domain_guess = domain or f"{search_name.lower().replace(' ', '')}.com.br"

    for lead in await discover_employees(search_name, domain_guess, email_api_key=EMAIL_API_KEY, max_results=100):
        cargo = lead.get("role", "Especialista")
        temp_employees.append(EmployeeNode(
            id=f"engine_{len(temp_employees)}", name=lead.get("name", "Colaborador"), role=cargo,
            department=await get_department_tag(cargo), company=lead.get("company"),
            manager_id=None, level=await get_seniority_level(cargo),
            email=lead.get("email"), linkedin=lead.get("linkedin"),
        ))

    if not qsa:
        temp_employees.append(EmployeeNode(
            id="aviso", name="Sem dados expandidos", role="Informação Pública Indisponível",
            department="Aviso", company=razao_social, manager_id="root_company", level=1,
        ))

    supply_chain = [
        e for e in temp_employees
        if any(kw in await get_department_tag(e.role) for kw in ["Compras", "Logística", "Diretoria Executiva", "Corporativo Geral", "QSA"])
        or "QSA" in e.department or e.id == "aviso"
    ]
    levels_map = {i: [] for i in range(1, 7)}
    for e in supply_chain:
        levels_map[e.level].append(e)

    for e in supply_chain:
        my_dept = await get_department_tag(e.role)
        e.manager_id = "root_company"
        for lvl in range(e.level - 1, 0, -1):
            bosses = [
                b for b in levels_map.get(lvl, [])
                if (await get_department_tag(b.role)) == my_dept
                or any(kw in (await get_department_tag(b.role)) for kw in ["Diretoria Executiva", "Corporativo Geral", "Compras"])
                or "QSA" in b.department
            ]
            if bosses:
                e.manager_id = bosses[0].id
                break
        nodes.append(e)

    return HierarchyResponse(company_name=razao_social, identifier=cnpj_clean, employees=nodes)


@router.get("/stream")
async def stream_company_hierarchy(
    request: Request,
    cnpj: str = Query(...),
    domain: Optional[str] = Query(None),
    confirmed_brand: Optional[str] = Query(None),
    confirmed_logo: Optional[str] = Query(None),
    product_focus: Optional[str] = Query(None),
    area_focus: Optional[str] = Query("compras"),
    db: AsyncSession = Depends(get_db),
):
    """SSE — envia dados de hierarquia progressivamente."""
    EMAIL_API_KEY = settings.EMAIL_API_KEY
    cnpj_clean = clean_cnpj(cnpj)

    async def generator():
        data = await fetch_company_data_by_cnpj(cnpj_clean)
        if not data:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Erro nas APIs de CNPJ.'})}\n\n"
            return

        razao_social = data.get("razao_social") or data.get("nome_fantasia") or "Empresa"
        qsa = data.get("qsa", [])
        hierarchy_pool: list = []
        initial_nodes: list = []

        full_address = build_full_address(data)
        org_id = None
        try:
            org_id = await upsert_organization(
                db, razao_social, cnpj_clean, domain, full_address,
                confirmed_brand=confirmed_brand, area_focus=area_focus,
                product_focus=product_focus, confirmed_logo=confirmed_logo,
            )
        except Exception as e:
            print(f"[DB] Erro ao salvar Organizacao: {e}")

        root_node = build_root_node(razao_social, confirmed_brand, confirmed_logo, domain)
        initial_nodes.append(root_node)
        hierarchy_pool.append(EmployeeNode(**root_node))

        for s_node in build_socio_nodes(qsa, razao_social):
            initial_nodes.append(s_node)
            hierarchy_pool.append(EmployeeNode(**s_node))

        if org_id:
            await persist_socios(db, org_id, qsa)
        if not qsa:
            initial_nodes.append({"id": "aviso", "name": "Sem dados QSA", "role": "Publico Indisponivel",
                                   "department": "Aviso", "manager_id": "root_company", "level": 6})

        city, state = data.get("municipio", ""), data.get("uf", "")
        location_focus = f"{city}, {state}" if city else None
        raw_name = data.get("nome_fantasia") or razao_social
        search_name = re.sub(r"(?i)\b(ltda|s\.a\.|s/a|limitada|s a|sa|s\.a)\b", "", raw_name).replace("-", " ").strip()
        domain_guess = domain or f"{search_name.lower().replace(' ', '')}.com.br"

        initial_nodes.sort(key=lambda x: x.get("level", 1), reverse=True)
        yield f"data: {json.dumps({'type': 'initial', 'company_name': razao_social, 'nodes': initial_nodes})}\n\n"

        async for batch in discover_employees_stream(
            search_name, domain_guess, confirmed_brand=confirmed_brand,
            location=location_focus, product_focus=product_focus,
            area_focus=area_focus, email_api_key=EMAIL_API_KEY, max_results=100,
        ):
            new_nodes = []
            for lead in batch:
                href = lead.get("linkedin", "")
                name_norm = lead.get("name", "").lower().strip()
                node_id = lead.get("id") or (
                    f"node_{re.sub(r'[^a-zA-Z0-9]', '_', href.split('/in/')[-1])}" if "/in/" in href
                    else f"node_{hash(href)}"
                )
                if any(h.id == node_id or (h.name.lower() == name_norm and h.role.lower() == lead.get("role", "").lower()) for h in hierarchy_pool):
                    continue

                emp = EmployeeNode(
                    id=node_id, name=lead.get("name", "Colaborador"), role=lead.get("role", "Professional"),
                    department=lead.get("department", "Operations"), company=lead.get("company"),
                    manager_id=None, level=lead.get("level", 2), email=lead.get("email"),
                    linkedin=lead.get("url") or lead.get("linkedin", ""),
                    url=lead.get("url") or lead.get("linkedin", ""),
                    education=lead.get("education"), location=lead.get("location"),
                    connections=lead.get("connections"), highlights=lead.get("highlights"),
                    observations=lead.get("observations"), temperature=lead.get("temperature"),
                )
                emp.manager_id = await assign_managers(emp, hierarchy_pool)
                reparented = reparent_subordinates(emp, hierarchy_pool)
                hierarchy_pool.append(emp)
                new_nodes.append(emp.dict())
                if reparented:
                    new_nodes.extend(reparented)

            if new_nodes:
                yield f"data: {json.dumps({'type': 'batch', 'nodes': new_nodes}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.get("/pipedrive/{pipedrive_id}")
async def get_hierarchy_by_pipedrive(pipedrive_id: int, db: AsyncSession = Depends(get_db)):
    """Busca hierarquia pelo ID do Pipedrive."""
    return await get_stored_hierarchy_by_pipedrive(pipedrive_id, db)


@router.get("/{org_id}")
async def get_hierarchy_by_org(org_id: int, db: AsyncSession = Depends(get_db)):
    """Busca hierarquia salva no banco pelo ID local da organização."""
    result = await get_stored_hierarchy(org_id, db)
    if result is None:
        raise HTTPException(status_code=404, detail="Organização não encontrada no banco local.")
    return result
