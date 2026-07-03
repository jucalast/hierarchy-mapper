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

from core.infra.database import get_db, async_session
from core.infra.redis_config import redis_client
from core.config import settings
from core.observability.logging_config import get_logger
from api.v1.schemas import EmployeeNode, HierarchyResponse, CandidateActionRequest, EnrichManualRequest, EmployeeUpdateRequest, clean_cnpj

log = get_logger(__name__)

from .service.candidate_service import process_candidate_action
from .service.manual_enricher import enrich_employee_manually, update_employee_details
from .service.hierarchy_loader import get_stored_hierarchy, get_stored_hierarchy_by_pipedrive
from .service.hierarchy_refiner import refine_and_persist
from .service.b2b_scanner import discover_employees, discover_employees_stream
from .service.filters import get_seniority_level, get_department_tag, is_same_person
from .service.cnpj_resolver import fetch_company_data_by_cnpj, build_full_address
from .service.org_persistence import upsert_organization, persist_socios
from .service.graph_builder import build_root_node, build_socio_nodes, assign_managers, reparent_subordinates

router = APIRouter()


@router.post("/candidate-action")
async def candidate_action(payload: CandidateActionRequest, db: AsyncSession = Depends(get_db)):
    """Aprova ou rejeita um candidato em análise humana."""
    return await process_candidate_action(payload.employee_id, payload.action, db)


@router.post("/enrich-manual")
async def enrich_manual(payload: EnrichManualRequest, db: AsyncSession = Depends(get_db)):
    """Enriquece um funcionário via texto bruto do LinkedIn."""
    return await enrich_employee_manually(payload.employee_id, payload.raw_text, db)


@router.post("/update-employee")
async def update_employee(payload: EmployeeUpdateRequest, employee_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    """Atualiza manualmente os detalhes de um funcionário."""
    return await update_employee_details(employee_id, payload.dict(), db)


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
        cargo = socio.get("qualificacao_socio") or "Sócio"
        cargo_lower = cargo.lower()
        temp_employees.append(EmployeeNode(
            id=f"socio_{idx}", name=socio.get("nome_socio") or "Sócio Anônimo", role=cargo,
            department="Quadro de Sócios (QSA)", company=razao_social, manager_id=None,
            level=1 if "sócio" in cargo_lower or "administrador" in cargo_lower else await get_seniority_level(cargo),
        ))

    raw_name = data.get("nome_fantasia") or razao_social
    search_name = re.sub(r"(?i)\b(ltda|s\.a\.|s/a|limitada|s a|sa|s\.a)\b", "", raw_name).replace("-", " ").strip() or razao_social
    domain_guess = domain or f"{search_name.lower().replace(' ', '')}.com.br"

    for lead in await discover_employees(search_name, domain_guess, email_api_key=EMAIL_API_KEY, max_results=100):
        cargo = lead.get("role") or "Especialista"
        temp_employees.append(EmployeeNode(
            id=f"engine_{len(temp_employees)}", name=lead.get("name") or "Colaborador", role=cargo,
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
    model: Optional[str] = Query(None),
    strict_mode: Optional[bool] = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """SSE — envia dados de hierarquia progressivamente."""
    EMAIL_API_KEY = settings.EMAIL_API_KEY
    cnpj_clean = clean_cnpj(cnpj)

    async def generator():
        if model:
            from core.llm import set_preferred_model
            set_preferred_model(model, strict_mode)

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

        # 🚀 PERSISTÊNCIA IMEDIATA DOS SÓCIOS: Garante que apareçam no banco e no front na hora
        if qsa and org_id:
            await persist_socios(db, org_id, qsa)
            # Recarrega os sócios salvos para garantir IDs consistentes
            from models import Employee
            from sqlalchemy import select
            stmt_p = select(Employee).where(Employee.company_id == org_id, Employee.department == "Quadro de Sócios (QSA)")
            res_p = await db.execute(stmt_p)
            db_partners = res_p.scalars().all()
            
            for p in db_partners:
                s_node = {
                    "id": f"node_{p.id}",
                    "name": p.name,
                    "role": p.role or "Sócio / Administrador",
                    "department": "Quadro de Sócios (QSA)",
                    "level": 6,
                    "seniority": 6,
                    "manager_id": "root_company",
                    "linkedin": p.linkedin_url
                }
                initial_nodes.append(s_node)
                hierarchy_pool.append(EmployeeNode(**s_node))
        
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
                if any(h.id == node_id or is_same_person(h.name, lead.get("name", "")) for h in hierarchy_pool):
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
                    pipedrive_id=lead.get("pipedrive_id"), source=lead.get("source"),
                )
                emp.manager_id = await assign_managers(emp, hierarchy_pool)
                reparented = reparent_subordinates(emp, hierarchy_pool)
                hierarchy_pool.append(emp)
                new_nodes.append(emp.dict())
                if reparented:
                    new_nodes.extend(reparented)

            if new_nodes:
                yield f"data: {json.dumps({'type': 'batch', 'nodes': new_nodes}, ensure_ascii=False)}\n\n"

        if org_id:
            from modules.agent.service.tools.intelligence import batch_discover_and_validate_org_emails
            asyncio.create_task(batch_discover_and_validate_org_emails(org_id))

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


@router.post("/test-linkedin-scrape")
async def test_linkedin_scrape(
    company_url: str = Query(..., description="A URL da empresa no LinkedIn"),
    session_cookie: Optional[str] = Query(None, description="O cookie li_at opcional"),
    headless: bool = Query(True, description="Se deve rodar em segundo plano"),
):
    """
    Roda um scraping de teste do LinkedIn de forma modular e isolada em subprocesso.
    Retorna a lista de pessoas extraídas.
    """
    import subprocess
    import sys
    import os
    import json
    import uuid
    import asyncio
    
    # Define diretórios de arquivos temporários
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tmp_dir = os.path.join(backend_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    
    # Gera um caminho de saída único para esta requisição para evitar colisões concorrentes
    unique_id = str(uuid.uuid4())
    output_filepath = os.path.join(tmp_dir, f"hierarchy_scan_{unique_id}.json")
    
    # Localiza o script de teste CLI e o interpretador python do venv
    python_exe = sys.executable
    script_path = os.path.join(backend_dir, "scripts", "test_hierarchy_scan.py")
    
    cmd = [python_exe, "-X", "utf8", script_path, company_url, output_filepath]
    
    # Propaga as variáveis de ambiente necessárias
    env = os.environ.copy()
    if session_cookie:
        env["LINKEDIN_LI_AT"] = session_cookie
    env["LINKEDIN_HEADLESS"] = "true" if headless else "false"
    
    # Configurações do subprocesso para o run_in_executor
    kwargs = {
        "env": env,
        "encoding": "utf-8",
        "errors": "ignore"
    }
    
    if os.name == "nt":
        # No Windows, usamos o sinalizador CREATE_NEW_CONSOLE para abrir um terminal separado visível para o usuário!
        # Isso permite que ele veja todo o progresso (scrolls, cliques, login manual) em tempo real.
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    else:
        kwargs["capture_output"] = True
        
    # Executa o subprocesso de maneira assíncrona usando o run_in_executor do asyncio.
    # Como subprocess.run é síncrono e roda em uma thread paralela do pool,
    # não é afetado pelo loop do SelectorEventLoop do Uvicorn e executa nativamente!
    loop = asyncio.get_running_loop()
    
    try:
        # Executa o subprocesso bloqueante em uma thread do pool para não travar o FastAPI
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, **kwargs)
        )
        
        # Se falhar no nível do processo
        if result.returncode != 0:
            err_msg = "Falha no processo secundário do scraper."
            if not kwargs.get("creationflags"):
                err_msg = getattr(result, "stderr", "") or getattr(result, "stdout", "") or err_msg
            raise HTTPException(status_code=500, detail=f"Erro de processo do Scraper: {err_msg}")
            
        # Lê os resultados salvos no arquivo único de saída
        if not os.path.exists(output_filepath):
            raise HTTPException(status_code=500, detail="Arquivo de resultados não foi gerado pelo Scraper. Verifique o terminal aberto.")
            
        with open(output_filepath, "r", encoding="utf-8") as f:
            results_data = json.load(f)
            
        # Deleta o arquivo temporário único após ler com sucesso
        try:
            os.remove(output_filepath)
        except Exception:
            pass
            
        return {"status": "success", "total": len(results_data), "data": results_data}
        
    except Exception as e:
        # Garante que removemos o arquivo temporário em caso de erro
        try:
            if os.path.exists(output_filepath):
                os.remove(output_filepath)
        except Exception:
            pass
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Erro na extração isolada: {str(e)}")


@router.get("/linkedin-scrape/preview")
async def get_linkedin_scrape_preview():
    """
    Retorna a captura de tela mais recente do processo de scraping do LinkedIn.
    Usada para exibição em tempo real (live browser preview) no painel web.
    """
    import os
    from fastapi.responses import FileResponse, Response
    
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    preview_path = os.path.join(backend_dir, "tmp", "scraper_preview.jpg")
    
    if not os.path.exists(preview_path):
        return Response(status_code=404, content="Screenshot não disponível ainda.")
        
    return FileResponse(
        preview_path, 
        media_type="image/jpeg", 
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.post("/linkedin-scrape/start")
async def start_linkedin_scrape(
    company_url: str = Query(..., description="A URL da empresa no LinkedIn"),
    session_cookie: Optional[str] = Query(None, description="O cookie li_at opcional"),
    headless: bool = Query(True, description="Se deve rodar em segundo plano"),
    area_focus: Optional[str] = Query(None, description="Foco de departamento/área"),
    product_focus: Optional[str] = Query(None, description="Foco de produto"),
    model: Optional[str] = Query(None, description="Modelo de IA selecionado"),
):
    """
    Enfileira o scraping do LinkedIn como um background job (ARQ), desacoplado
    da conexão HTTP. O progresso é transmitido via WebSocket em /jobs/ws/{job_id}.
    """
    from arq import create_pool
    from core.infra.redis_config import redis_settings

    try:
        redis = await create_pool(redis_settings)
        job = await redis.enqueue_job(
            "run_linkedin_scrape_task",
            company_url=company_url,
            session_cookie=session_cookie,
            headless=headless,
            area_focus=area_focus,
            product_focus=product_focus,
            model=model,
        )
        return {"job_id": job.job_id, "status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enfileirar scraping: {str(e)}")


@router.post("/linkedin-scrape/interact")
async def linkedin_scrape_interact(
    job_id: str = Query(..., description="ID do job de scraping em andamento"),
    action: str = Query(..., description="Ação: click, type, press"),
    x: Optional[float] = Query(None),
    y: Optional[float] = Query(None),
    text: Optional[str] = Query(None),
    key: Optional[str] = Query(None),
):
    """
    Interage com o navegador de raspagem em tempo real (clique, escrita ou teclas).
    Publica o comando no canal Redis do job para o worker repassar ao subprocesso.
    """
    command: dict = {"action": action}
    if action == "click" and x is not None and y is not None:
        command.update({"x": x, "y": y})
    elif action == "type" and text:
        command["text"] = text
    elif action == "press" and key:
        command["key"] = key
    else:
        raise HTTPException(status_code=400, detail="Ação de interação inválida ou parâmetros insuficientes.")

    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis indisponível para enviar comandos ao agente.")

    try:
        import asyncio
        await asyncio.to_thread(redis_client.publish, f"scraper_commands_{job_id}", json.dumps(command, ensure_ascii=False))
        return {"status": "success", "message": f"Comando '{action}' enviado ao agente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao interagir com o agente: {str(e)}")


@router.post("/linkedin-scrape/stop")
async def linkedin_scrape_stop(job_id: str = Query(..., description="ID do job de scraping em andamento")):
    """
    Para o processo de varredura ativo graciosamente, forçando a extração imediata
    de todas as pessoas localizadas até então.
    """
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis indisponível para enviar comandos ao agente.")

    try:
        import asyncio
        # Flag durável (TTL 1h): garante que o stop é respeitado mesmo se o job ainda
        # estiver na fila do ARQ (sem nenhum listener de pub/sub ativo ainda) ou se a
        # mensagem de pub/sub for perdida por qualquer motivo.
        await asyncio.to_thread(redis_client.set, f"scraper_stop_requested_{job_id}", "1", ex=3600)
        await asyncio.to_thread(redis_client.publish, f"scraper_commands_{job_id}", json.dumps({"action": "stop"}, ensure_ascii=False))
        return {"status": "success", "message": "Solicitação de parada graciosa enviada ao agente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao parar o agente graciosamente: {str(e)}")
