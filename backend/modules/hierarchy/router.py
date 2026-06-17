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
from .service.filters import get_seniority_level, get_department_tag
from .service.cnpj_resolver import fetch_company_data_by_cnpj, build_full_address
from .service.org_persistence import upsert_organization, persist_socios
from .service.graph_builder import build_root_node, build_socio_nodes, assign_managers, reparent_subordinates

router = APIRouter()

# Armazena o subprocesso ativo de raspagem do LinkedIn para permitir controle interativo por stdin
active_scraper_process = None


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


@router.get("/linkedin-scrape/stream")
async def stream_linkedin_scrape(
    company_url: str = Query(..., description="A URL da empresa no LinkedIn"),
    session_cookie: Optional[str] = Query(None, description="O cookie li_at opcional"),
    headless: bool = Query(True, description="Se deve rodar em segundo plano"),
    area_focus: Optional[str] = Query(None, description="Foco de departamento/área"),
    product_focus: Optional[str] = Query(None, description="Foco de produto"),
    model: Optional[str] = Query(None, description="Modelo de IA selecionado"),
):
    """
    Executa o scraping do LinkedIn em segundo plano e transmite os logs do terminal,
    as notificações de novos prints (screenshots) e os resultados finais via Server-Sent Events (SSE).
    """
    import subprocess
    import sys
    import os
    import json
    import uuid
    import asyncio
    from fastapi.responses import StreamingResponse
    
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tmp_dir = os.path.join(backend_dir, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    
    unique_id = str(uuid.uuid4())
    output_filepath = os.path.join(tmp_dir, f"hierarchy_scan_{unique_id}.json")
    
    python_exe = sys.executable
    script_path = os.path.join(backend_dir, "scripts", "test_hierarchy_scan.py")
    
    # Prepara o comando
    cmd = [python_exe, "-X", "utf8", script_path, company_url, output_filepath, "--no-delay"]
    
    env = os.environ.copy()
    if session_cookie:
        env["LINKEDIN_LI_AT"] = session_cookie
    env["LINKEDIN_HEADLESS"] = "true" if headless else "false"
    
    # Remove qualquer screenshot antigo para iniciar do zero
    preview_path = os.path.join(tmp_dir, "scraper_preview.jpg")
    if os.path.exists(preview_path):
        try:
            os.remove(preview_path)
        except Exception:
            pass

    async def sse_generator():
        # Helper para enviar log para o SSE e para o Terminal via Redis
        async def send_log(message: str, msg_type: str = "log"):
            yield_data = f"data: {json.dumps({'type': msg_type, 'message': message}, ensure_ascii=False)}\n\n"
            if redis_client:
                try:
                    loop.run_in_executor(
                        None, 
                        lambda: redis_client.publish(
                            "linkedin_scan_logs", 
                            json.dumps({"message": message}, ensure_ascii=False)
                        )
                    )
                except Exception:
                    pass
            return yield_data

        # 🏢 IDENTIFICAÇÃO DA ORGANIZAÇÃO (CONTEXTO)
        from sqlalchemy import select, func
        from models.organization.organization import Organization
        from models.people.employee import Employee
        from .service.candidate_processor import CandidateProcessor
        
        db_org = None
        async with async_session() as session:
            clean_url = company_url.split("/people/")[0].split("?")[0].rstrip("/")
            res = await session.execute(
                select(Organization).where(
                    (Organization.linkedin_url.contains(clean_url)) | 
                    (func.lower(Organization.name).contains(clean_url.split("/")[-1].replace("-", " ")))
                )
            )
            db_org = res.scalars().first()
            
            if db_org:
                yield await send_log(f"[Agent] Empresa identificada: {db_org.name} (ID: {db_org.id})")
            else:
                yield await send_log(f"[Agent] Empresa não encontrada no banco. Criando registro temporário para {clean_url.split('/')[-1]}...")
                db_org = Organization(
                    name=clean_url.split("/")[-1].replace("-", " ").title(),
                    linkedin_url=company_url,
                    source="discovery_scan"
                )
                session.add(db_org)
                await session.commit()
                await session.refresh(db_org)

            # 🚀 LIMPEZA: Deleta funcionários antigos (MENOS Sócios/QSA e decisões manuais)
            # Preservamos contatos que já possuem cargo definido (aprovados) ou foram reprovados
            from sqlalchemy import delete, and_, not_, or_
            await session.execute(
                delete(Employee).where(
                    and_(
                        Employee.company_id == db_org.id,
                        not_(
                            or_(
                                Employee.department == "Quadro de Sócios (QSA)",
                                Employee.seniority == 6,
                                # 🛡️ Preservar decisões: Qualquer coisa que não seja 'Análise Humana' ou genérico
                                and_(
                                    Employee.role != "Análise Humana",
                                    Employee.role != "Não Identificado",
                                    Employee.role != "Erro no Processamento",
                                    Employee.role != "Professional"
                                )
                            )
                        )
                    )
                )
            )
            await session.commit()
            yield f"data: {json.dumps({'type': 'clear_nodes'}, ensure_ascii=False)}\n\n"

        # ─── Compatibilidade Windows: subprocess via thread + asyncio.Queue ───
        # asyncio.create_subprocess_exec NÃO funciona no WindowsSelectorEventLoop.
        import subprocess
        import threading
        import queue as thread_queue

        loop = asyncio.get_running_loop()
        log.info("hierarchy.scrape.loop_check", loop_type=str(type(loop)))

        line_queue: thread_queue.Queue = thread_queue.Queue()
        process_ref: dict = {}

        def run_scraper():
            """Roda o subprocesso em thread bloqueante e enfileira linhas."""
            try:
                proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    encoding="utf-8",
                    errors="replace",
                )
                process_ref["proc"] = proc
                global active_scraper_process
                active_scraper_process = proc  # type: ignore[assignment]
                for line in proc.stdout:  # type: ignore[union-attr]
                    line_queue.put(("line", line.rstrip()))
                # Stdout fechou — enfileira "done" ANTES de proc.wait()
                # O proc.wait() pode demorar (cleanup do Playwright/Chromium),
                # mas o frontend já pode começar a processar os resultados.
                rc = proc.poll()  # Tenta pegar o returncode imediatamente
                line_queue.put(("done", rc if rc is not None else 0))
                proc.wait()  # Aguarda em background (sem bloquear a fila)
            except Exception as exc:
                line_queue.put(("error", str(exc)))

        scraper_thread = threading.Thread(target=run_scraper, daemon=True)
        scraper_thread.start()
        
        try:
            yield await send_log("[Agent] Inicializando motor de automação Playwright...")
            
            returncode = 0
            while True:
                # Polling não-bloqueante da fila em asyncio
                try:
                    kind, payload = await loop.run_in_executor(
                        None,
                        lambda: line_queue.get(timeout=10)  # 10s entre mensagens é suficiente
                    )
                except Exception:
                    # Timeout de 10s sem mensagem — verifica se o processo já terminou
                    proc = process_ref.get("proc")
                    if proc and proc.poll() is not None:
                        # Processo já terminou — prossegue sem aguardar mais
                        returncode = proc.returncode or 0
                        yield await send_log("[Agent] Processo finalizado. Iniciando processamento...")
                        break
                    yield await send_log("[Agent] Aguardando resposta do scraper...")
                    continue

                if kind == "done":
                    returncode = payload
                    break
                elif kind == "error":
                    yield await send_log(f"[Agent Fatal] Erro ao iniciar scraper: {payload}", "error")
                    return
                else:
                    line: str = payload
                    if not line:
                        continue
                    # Intercepta notificações de novos screenshots e cookies capturados
                    if "[SCREENSHOT_UPDATED]" in line:
                        yield f"data: {json.dumps({'type': 'screenshot'})}\n\n"
                    elif line.startswith("[COOKIE_CAPTURED] "):
                        cookie_val = line.split("[COOKIE_CAPTURED] ")[1].strip()
                        yield f"data: {json.dumps({'type': 'cookie', 'cookie': cookie_val})}\n\n"
                    else:
                        yield await send_log(line)
            
            # Aguarda a finalização definitiva
            if returncode != 0:
                yield await send_log(f"[Agent Error] O processo secundário encerrou com código de erro {returncode}", "error")
                return
                
            # Lê o JSON de saída final gerado pelo script
            if os.path.exists(output_filepath):
                with open(output_filepath, "r", encoding="utf-8") as f:
                    results_data = json.load(f)
                
                if results_data:
                    yield await send_log(f"[AI Filter] Iniciando processamento inteligente de {len(results_data)} perfis...")
                    
                    # Deduplica por linkedin_url
                    unique_employees = []
                    seen_urls = set()
                    for emp in results_data:
                        url = emp.get("linkedin_url")
                        if url:
                            clean_url_emp = url.split("?")[0].rstrip("/")
                            if clean_url_emp not in seen_urls:
                                seen_urls.add(clean_url_emp)
                                unique_employees.append(emp)
                        else:
                            unique_employees.append(emp)
                    
                    # 🚀 PROCESSAMENTO COM CANDIDATE_PROCESSOR (Em Lotes de 10 para Performance)
                    nodes_to_yield = []
                    async with async_session() as session:
                        stmt_rej = select(Employee).where(
                            Employee.company_id == db_org.id,
                            (Employee.role == "Reprovado") | (Employee.department == "Reprovado")
                        )
                        res_rej = await session.execute(stmt_rej)
                        rejected_urls = {emp.linkedin_url.split("?")[0].rstrip("/") for emp in res_rej.scalars().all() if emp.linkedin_url}

                        # Prepara candidatos válidos
                        valid_candidates = []
                        for idx, emp in enumerate(unique_employees):
                            emp_url = emp.get("linkedin_url", "").split("?")[0].rstrip("/")
                            if emp_url in rejected_urls:
                                yield await send_log(f"⏩ [Ignorado] {emp.get('name')} já foi reprovado anteriormente.")
                                continue
                            
                            valid_candidates.append({
                                "idx": idx,
                                "name": emp.get("name"),
                                "role": emp.get("role"),
                                "linkedin_url": emp_url,
                                "context": [
                                    f"--- DADOS RASPADO DO LINKEDIN ---",
                                    f"NOME: {emp.get('name')}",
                                    f"CARGO EXIBIDO: {emp.get('role')}",
                                    f"LOCALIZAÇÃO: {emp.get('location', 'Brasil')}",
                                    f"PERFIL: {emp_url}"
                                ],
                                "emp_raw": emp
                            })

                        # Processa em lotes de 10
                        from .service.role_engine import role_engine
                        batch_size = 10
                        for i in range(0, len(valid_candidates), batch_size):
                            batch = valid_candidates[i:i + batch_size]
                            yield await send_log(f"🧠 [AI Batch] Processando lote {i//batch_size + 1} ({len(batch)} perfis)...")
                            
                            try:
                                def normalize_linkedin(url: str) -> str:
                                    if not url: return ''
                                    url = url.split('?')[0].rstrip('/')
                                    url = url.replace('http://', 'https://')
                                    if 'linkedin.com' in url:
                                        parts = url.split('linkedin.com')
                                        return 'linkedin.com' + parts[1]
                                    return url
                                    
                                import unicodedata
                                def clean_name(s: str) -> str:
                                    if not s: return ""
                                    return "".join(
                                        c for c in unicodedata.normalize('NFD', s.lower())
                                        if unicodedata.category(c) != 'Mn'
                                    ).strip()

                                def names_match(n1: str, n2: str) -> bool:
                                    n1_clean, n2_clean = clean_name(n1), clean_name(n2)
                                    if n1_clean == n2_clean: return True
                                    parts1, parts2 = n1_clean.split(), n2_clean.split()
                                    if not parts1 or not parts2: return False
                                    if len(parts1) == 1 and parts1[0] == parts2[0]: return True
                                    if len(parts2) == 1 and parts2[0] == parts1[0]: return True
                                    if parts1[0] == parts2[0] and parts1[-1] == parts2[-1]: return True
                                    return False

                                batch_results = await role_engine.distill_roles_batch_v2(
                                    batch,
                                    db_org.name,
                                    area_focus=area_focus or "compras",
                                    product_focus=product_focus or "Geral B2B"
                                )
                                
                                # 🚀 PROCESSAMENTO PARALELO DE E-MAILS PARA O LOTE
                                approved_tasks = []
                                approved_candidates_data = []

                                for c in batch:
                                    res = batch_results.get(c['idx'])
                                    if not res or not res.get("is_valid"):
                                        yield await send_log(f"❌ [Filtrado] {c['name']} ({c['role']})")
                                        # Marca como Reprovado no banco se existir para ocultar da UI
                                        norm_url = normalize_linkedin(c.get('linkedin_url'))
                                        all_emps_res = await session.execute(
                                            select(Employee).where(Employee.company_id == db_org.id)
                                        )
                                        all_emps = all_emps_res.scalars().all()
                                        existing_rej = next((e for e in all_emps if (norm_url and normalize_linkedin(e.linkedin_url) == norm_url) or names_match(e.name, c['name'])), None)
                                        if existing_rej:
                                            existing_rej.role = "Reprovado"
                                            existing_rej.department = "Reprovado"
                                            await session.commit()
                                        continue

                                    # Prepara dados para processamento
                                    emp_name = res.get("proper_name", c['name'])
                                    approved_candidates_data.append({
                                        "res": res,
                                        "candidate": c,
                                        "emp_name": emp_name
                                    })

                                    # Cria tarefa de descoberta de e-mail se houver domínio
                                    if db_org and db_org.domain:
                                        try:
                                            name_parts = emp_name.split()
                                            first_name = name_parts[0] if name_parts else ""
                                            last_name = name_parts[-1] if len(name_parts) > 1 else ""
                                            if first_name and last_name:
                                                from core.external.email_service import discover_and_validate_email
                                                approved_tasks.append(discover_and_validate_email(
                                                    first=first_name,
                                                    last=last_name,
                                                    domain=db_org.domain,
                                                    do_smtp=True
                                                ))
                                            else:
                                                approved_tasks.append(asyncio.sleep(0, result=None))
                                        except Exception:
                                            approved_tasks.append(asyncio.sleep(0, result=None))
                                    else:
                                        approved_tasks.append(asyncio.sleep(0, result=None))

                                # Executa todas as descobertas de e-mail em paralelo
                                email_results = await asyncio.gather(*approved_tasks)

                                # Processa cada aprovado com seu respectivo e-mail
                                for idx, data in enumerate(approved_candidates_data):
                                    res = data['res']
                                    c = data['candidate']
                                    emp_name = data['emp_name']
                                    emp_email_data = email_results[idx]
                                    emp_email = emp_email_data.get("email") if emp_email_data else None

                                    final_role = res.get("role", c['role'])
                                    dept = res.get("department", "A validar")
                                    score = res.get("matching_score", 50)
                                    evidence = res.get("evidence")
                                    emp_url = c['linkedin_url']
                                    emp_raw = c['emp_raw']

                                    # Resolução resiliente da localização
                                    fallback_loc = "Brasil"
                                    if db_org and db_org.address:
                                        normalized = db_org.address.replace(",", " - ")
                                        addr_parts = [p.strip() for p in normalized.split(" - ") if p.strip()]
                                        if len(addr_parts) >= 2:
                                            city = addr_parts[-2].title()
                                            state = addr_parts[-1].upper()
                                            fallback_loc = f"{city}, {state}, Brasil" if len(state) == 2 else f"{city}, {state}"
                                        else:
                                            fallback_loc = db_org.address

                                    emp_loc = emp_raw.get("location")
                                    if not emp_loc or emp_loc == "Localização não identificada":
                                        emp_loc = fallback_loc

                                    import unicodedata
                                    def clean_name(s: str) -> str:
                                        if not s: return ""
                                        return "".join(
                                            c for c in unicodedata.normalize('NFD', s.lower())
                                            if unicodedata.category(c) != 'Mn'
                                        ).strip()

                                    def names_match(n1: str, n2: str) -> bool:
                                        n1_clean, n2_clean = clean_name(n1), clean_name(n2)
                                        if n1_clean == n2_clean: return True
                                        parts1, parts2 = n1_clean.split(), n2_clean.split()
                                        if not parts1 or not parts2: return False
                                        # Match se for só o primeiro nome
                                        if len(parts1) == 1 and parts1[0] == parts2[0]: return True
                                        if len(parts2) == 1 and parts2[0] == parts1[0]: return True
                                        # Match primeiro e último nome
                                        if parts1[0] == parts2[0] and parts1[-1] == parts2[-1]: return True
                                        return False

                                    norm_emp_url = normalize_linkedin(emp_url)
                                    all_emps_res = await session.execute(
                                        select(Employee).where(Employee.company_id == db_org.id)
                                    )
                                    all_emps = all_emps_res.scalars().all()
                                    
                                    # Busca primeiro por URL do LinkedIn
                                    existing = next((e for e in all_emps if norm_emp_url and normalize_linkedin(e.linkedin_url) == norm_emp_url), None)
                                    
                                    # Se não achou por LinkedIn, tenta achar por match inteligente de nome
                                    if not existing:
                                        matches = [e for e in all_emps if names_match(e.name, emp_name)]
                                        # Só mescla se for inequívoco (exatamente 1 correspondência)
                                        if len(matches) == 1:
                                            existing = matches[0]
                                            yield await send_log(f"🔗 [Vinculado] {emp_name} encontrado no banco (como {existing.name}). Mesclando perfil do LinkedIn...")
                                    
                                        # ----------------------------------------------------
                                        # NOVA LÓGICA: Verifica no Pipedrive se já existe antes de criar local
                                        # ----------------------------------------------------
                                        from modules.crm.service.pipedrive_service import pipedrive_service
                                        if db_org and db_org.pipedrive_id:
                                            try:
                                                pd_search = await pipedrive_service._request(
                                                    "GET", 
                                                    "persons/search", 
                                                    params={"term": emp_name, "exact_match": 0, "limit": 5}
                                                )
                                                if pd_search and pd_search.status_code == 200:
                                                    d = pd_search.json()
                                                    items = d.get("data", {}).get("items") or []
                                                    for i in items:
                                                        p = i.get("item", {})
                                                        org = p.get("organization")
                                                        if org and str(org.get("id")) == str(db_org.pipedrive_id):
                                                            n1, n2 = clean_name(emp_name), clean_name(p.get("name", ""))
                                                            if n1 in n2 or n2 in n1 or names_match(emp_name, p.get("name", "")):
                                                                pd_email = p.get("primary_email")
                                                                if pd_email:
                                                                    emp_email = pd_email
                                                                
                                                                pd_phones = p.get("phones")
                                                                pd_phone = pd_phones[0] if pd_phones and len(pd_phones) > 0 else None
                                                                
                                                                new_emp = Employee(
                                                                    name=emp_name,
                                                                    role=final_role,
                                                                    department=dept,
                                                                    linkedin_url=emp_url,
                                                                    profile_pic=emp_raw.get("avatar"),
                                                                    location=emp_loc,
                                                                    company_id=db_org.id,
                                                                    is_discovery=1,
                                                                    source="pipedrive",
                                                                    matching_score=score,
                                                                    evidence=evidence,
                                                                    description=c['role'],
                                                                    email=emp_email,
                                                                    phone=pd_phone,
                                                                    pipedrive_id=str(p.get("id"))
                                                                )
                                                                session.add(new_emp)
                                                                await session.commit()
                                                                await session.refresh(new_emp)
                                                                existing = new_emp
                                                                yield await send_log(f"🔗 [Pipedrive] {emp_name} encontrado no Pipedrive. Importado e mesclado.")
                                                                break
                                            except Exception:
                                                pass

                                    if not existing:
                                        final_pic = emp_raw.get("avatar")
                                        if not final_pic and emp_url:
                                            from modules.intelligence.service.preview_service import get_url_preview
                                            try:
                                                preview = await get_url_preview(emp_url, fast_mode=True)
                                                if preview and preview.get("image"):
                                                    final_pic = preview.get("image")
                                            except Exception:
                                                pass
                                                
                                        new_emp = Employee(
                                            name=emp_name,
                                            role=final_role,
                                            department=dept,
                                            linkedin_url=emp_url,
                                            profile_pic=final_pic,
                                            location=emp_loc,
                                            company_id=db_org.id,
                                            is_discovery=1,
                                            source="discovery_scan",
                                            matching_score=score,
                                            evidence=evidence,
                                            description=c['role'],
                                            email=emp_email,
                                        )
                                        session.add(new_emp)
                                        await session.commit()
                                        await session.refresh(new_emp)
                                        existing = new_emp
                                        
                                    employee_id = f"node_{existing.id}"
                                    avatar_to_yield = existing.profile_pic
                                    
                                    if existing.id != locals().get('new_emp', Employee()).id:
                                        # 🛡️ PROTEÇÃO: Não sobrescreve se o contato já foi aprovado ou se o novo status é "pior"
                                        current_is_valid = existing.role and "análise humana" not in existing.role.lower() and "reprovado" not in existing.role.lower()
                                        new_is_vague = "análise humana" in final_role.lower()
                                        
                                        if current_is_valid and new_is_vague:
                                            # Mantém o que já estava lá (decisão manual ou automática anterior)
                                            yield await send_log(f"ℹ️ [Preservado] {emp_name} já possui cargo definido.")
                                        else:
                                            # Atualiza o nome se o novo for mais completo
                                            if len(emp_name) > len(existing.name):
                                                existing.name = emp_name
                                                
                                            existing.role = final_role
                                            existing.department = dept
                                            existing.linkedin_url = emp_url
                                            existing.matching_score = score
                                            existing.evidence = evidence
                                            # Dando preferência ao email já existente no sistema/pipedrive
                                            existing.email = existing.email or emp_email
                                            existing.description = c['role']
                                            existing.company_id = db_org.id
                                            
                                            # Trata a foto de perfil com fallback (novo scraper, db existente ou preview)
                                            final_pic = emp_raw.get("avatar") or existing.profile_pic
                                            if not final_pic and emp_url:
                                                from modules.intelligence.service.preview_service import get_url_preview
                                                try:
                                                    preview = await get_url_preview(emp_url, fast_mode=True)
                                                    if preview and preview.get("image"):
                                                        final_pic = preview.get("image")
                                                except Exception:
                                                    pass
                                            
                                            if not existing.profile_pic: existing.profile_pic = final_pic
                                            if not existing.location or existing.location == "Localização não identificada":
                                                existing.location = emp_loc
                                            if not existing.evidence: existing.evidence = evidence
                                            if not existing.email: existing.email = emp_email
                                            
                                            # Se for um merge com pipedrive, adiciona o link do linkedin e muda source
                                            if not existing.linkedin_url:
                                                existing.linkedin_url = emp_url
                                                if existing.source == "pipedrive":
                                                    existing.source = "pipedrive + scan"
                                            
                                            await session.commit()
                                        
                                        employee_id = f"node_{existing.id}"
                                        avatar_to_yield = final_pic
                                    
                                    node = {
                                        "id": employee_id,
                                        "name": emp_name,
                                        "role": final_role,
                                        "department": dept,
                                        "company": db_org.name,
                                        "linkedin": emp_url,
                                        "avatar": avatar_to_yield,
                                        "profile_pic": avatar_to_yield,
                                        "location": emp_loc,
                                        "matching_score": score,
                                        "observations": c['role'],
                                        "evidence": evidence,
                                        "email": (existing.email if existing else None) or emp_email,
                                        "pipedrive_id": int(existing.pipedrive_id) if existing and existing.pipedrive_id and str(existing.pipedrive_id).isdigit() else None,
                                        "source": existing.source if existing else "discovery_scan",
                                    }
                                    nodes_to_yield.append(node)
                                    yield await send_log(f"✅ [Aprovado] {emp_name} -> {final_role} ({dept})")
                                    
                                    if len(nodes_to_yield) >= 3:
                                        yield f"data: {json.dumps({'type': 'batch', 'nodes': nodes_to_yield}, ensure_ascii=False)}\n\n"
                                        nodes_to_yield = []

                                        
                            except Exception as e:
                                yield await send_log(f"⚠️ [Erro no Lote] {str(e)}", "error")

                        if nodes_to_yield:
                            yield f"data: {json.dumps({'type': 'batch', 'nodes': nodes_to_yield}, ensure_ascii=False)}\n\n"


                    yield await send_log(f"🎉 Processamento concluído!")
                
                if db_org:
                    from modules.agent.service.tools.intelligence import batch_discover_and_validate_org_emails
                    asyncio.create_task(batch_discover_and_validate_org_emails(db_org.id))
                
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                
                try:
                    os.remove(output_filepath)
                except Exception:
                    pass
            else:
                yield await send_log("[Agent Error] O arquivo de resultados não foi gerado pelo Scraper.", "error")
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                
        except Exception as e:
            try:
                yield f"data: {json.dumps({'type': 'error', 'message': f'[Agent Fatal Error] Falha na transmissão: {str(e)}'}, ensure_ascii=False)}\n\n"
            except Exception:
                pass
        finally:
            proc = process_ref.get("proc")
            if proc:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
                try:
                    proc.stdout.close()
                except Exception:
                    pass
                try:
                    if proc.poll() is None:
                        proc.terminate()
                except Exception:
                    pass
                
    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@router.post("/linkedin-scrape/interact")
async def linkedin_scrape_interact(
    action: str = Query(..., description="Ação: click, type, press"),
    x: Optional[float] = Query(None),
    y: Optional[float] = Query(None),
    text: Optional[str] = Query(None),
    key: Optional[str] = Query(None),
):
    """
    Interage com o navegador de raspagem em tempo real (clique, escrita ou teclas).
    Permite controle remoto completo diretamente da interface web!
    """
    global active_scraper_process
    
    if not active_scraper_process or active_scraper_process.returncode is not None:
        raise HTTPException(status_code=400, detail="Não há nenhum agente de raspagem ativo no momento.")
        
    try:
        command = ""
        if action == "click" and x is not None and y is not None:
            command = f"cmd_click {x} {y}\n"
        elif action == "type" and text:
            # Substitui quebras de linha para evitar que o comando quebre
            safe_text = text.replace("\n", " ")
            command = f"cmd_type {safe_text}\n"
        elif action == "press" and key:
            command = f"cmd_press {key}\n"
            
        if command:
            active_scraper_process.stdin.write(command.encode('utf-8'))
            await active_scraper_process.stdin.drain()
            return {"status": "success", "message": f"Comando '{action}' enviado ao agente."}
        else:
            raise HTTPException(status_code=400, detail="Ação de interação inválida ou parâmetros insuficientes.")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao interagir com o agente: {str(e)}")


@router.post("/linkedin-scrape/stop")
async def linkedin_scrape_stop():
    """
    Para o processo de varredura ativo graciosamente, forçando a extração imediata
    de todas as pessoas localizadas até então.
    """
    global active_scraper_process
    
    if not active_scraper_process or active_scraper_process.returncode is not None:
        raise HTTPException(status_code=400, detail="Não há nenhum agente de raspagem ativo no momento.")
        
    try:
        active_scraper_process.stdin.write("cmd_stop\n".encode('utf-8'))
        await active_scraper_process.stdin.drain()
        return {"status": "success", "message": "Solicitação de parada graciosa enviada ao agente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao parar o agente graciosamente: {str(e)}")
