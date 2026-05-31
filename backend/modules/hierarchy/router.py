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
from api.v1.schemas import EmployeeNode, HierarchyResponse, CandidateActionRequest, clean_cnpj

log = get_logger(__name__)

from .service.candidate_service import process_candidate_action
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

            # 🚀 LIMPEZA: Deleta funcionários antigos (MENOS Sócios/QSA) para iniciar mapeamento limpo
            # Isso atende ao requisito: "nunca apague o card de root e de socios"
            from sqlalchemy import delete, and_, not_, or_
            await session.execute(
                delete(Employee).where(
                    and_(
                        Employee.company_id == db_org.id,
                        not_(
                            or_(
                                Employee.department == "Quadro de Sócios (QSA)",
                                Employee.seniority == 6
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

                                    existing_res = await session.execute(
                                        select(Employee).where(Employee.linkedin_url == emp_url)
                                    )
                                    existing = existing_res.scalars().first()
                                    
                                    if not existing:
                                        new_emp = Employee(
                                            name=emp_name,
                                            role=final_role,
                                            department=dept,
                                            linkedin_url=emp_url,
                                            profile_pic=emp_raw.get("avatar"),
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
                                        employee_id = f"node_{new_emp.id}"
                                    else:
                                        existing.role = final_role
                                        existing.department = dept
                                        existing.matching_score = score
                                        existing.company_id = db_org.id
                                        if not existing.description: existing.description = c['role']
                                        if not existing.profile_pic: existing.profile_pic = emp_raw.get("avatar")
                                        if not existing.location or existing.location == "Localização não identificada":
                                            existing.location = emp_loc
                                        if not existing.evidence: existing.evidence = evidence
                                        if not existing.email: existing.email = emp_email
                                        await session.commit()
                                        employee_id = f"node_{existing.id}"
                                    
                                    node = {
                                        "id": employee_id,
                                        "name": emp_name,
                                        "role": final_role,
                                        "department": dept,
                                        "company": db_org.name,
                                        "linkedin": emp_url,
                                        "avatar": emp_raw.get("avatar"),
                                        "profile_pic": emp_raw.get("avatar"),
                                        "location": emp_loc,
                                        "matching_score": score,
                                        "observations": c['role'],
                                        "evidence": evidence,
                                        "email": emp_email or (existing.email if existing else None),
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
