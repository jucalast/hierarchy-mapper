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
    cmd = [python_exe, "-X", "utf8", script_path, company_url, output_filepath]
    
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
        # Spawna o processo capturando stdout e stderr em uma mesma pipe
        # Sem janela cmd popup no Windows (startupinfo opcional) para rodar invisivelmente em background
        startupinfo = None
        if os.name == "nt":
            # Oculta a janela de console do processo secundário quando redirecionamos a pipe
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,  # Habilita stdin para receber comandos de controle remoto
            text=True,
            encoding="utf-8",
            bufsize=1,
            startupinfo=startupinfo
        )
        
        global active_scraper_process
        active_scraper_process = process
        
        loop = asyncio.get_running_loop()
        
        def read_line(proc):
            return proc.stdout.readline()
            
        try:
            yield f"data: {json.dumps({'type': 'log', 'message': '[Agent] Inicializando motor de automação Playwright...'}, ensure_ascii=False)}\n\n"
            
            while True:
                # Lê a saída da pipe de forma não-bloqueante no executor
                line = await loop.run_in_executor(None, read_line, process)
                if not line and process.poll() is not None:
                     break
                     
                clean_line = line.strip()
                if not clean_line:
                    continue
                
                # Intercepta notificações de novos screenshots e cookies capturados
                if "[SCREENSHOT_UPDATED]" in clean_line:
                    yield f"data: {json.dumps({'type': 'screenshot'})}\n\n"
                elif clean_line.startswith("[COOKIE_CAPTURED] "):
                    cookie_val = clean_line.split("[COOKIE_CAPTURED] ")[1].strip()
                    yield f"data: {json.dumps({'type': 'cookie', 'cookie': cookie_val})}\n\n"
                else:
                    # Envia a linha de log do terminal original para o frontend
                    yield f"data: {json.dumps({'type': 'log', 'message': clean_line}, ensure_ascii=False)}\n\n"
            
            # Aguarda a finalização definitiva
            returncode = process.wait()
            if returncode != 0:
                yield f"data: {json.dumps({'type': 'error', 'message': f'[Agent Error] O processo secundário encerrou com código de erro {returncode}'}, ensure_ascii=False)}\n\n"
                return
                
            # Lê o JSON de saída final gerado pelo script
            if os.path.exists(output_filepath):
                with open(output_filepath, "r", encoding="utf-8") as f:
                    results_data = json.load(f)
                
                # Se area_focus ou product_focus estiverem definidos, aplica o filtro da IA
                if results_data and (area_focus or product_focus):
                    yield f"data: {json.dumps({'type': 'log', 'message': '[AI Filter] Iniciando filtragem inteligente de perfis...'}, ensure_ascii=False)}\n\n"
                    
                    # 1. Deduplica por linkedin_url para garantir dados não duplicados
                    unique_employees = []
                    seen_urls = set()
                    for emp in results_data:
                        url = emp.get("linkedin_url")
                        if url:
                            if url not in seen_urls:
                                seen_urls.add(url)
                                unique_employees.append(emp)
                        else:
                            unique_employees.append(emp)
                            
                    total_found = len(unique_employees)
                    yield f"data: {json.dumps({'type': 'log', 'message': f'[AI Filter] Total de perfis únicos a avaliar: {total_found}'}, ensure_ascii=False)}\n\n"
                    
                    # 2. Divide em lotes de 15 perfis
                    batch_size = 15
                    filtered_employees = []
                    
                    if model:
                        from core.llm import set_preferred_model
                        set_preferred_model(model, False)
                        
                    for idx_start in range(0, total_found, batch_size):
                        batch = unique_employees[idx_start : idx_start + batch_size]
                        current_batch_num = idx_start // batch_size + 1
                        total_batches = (total_found + batch_size - 1) // batch_size
                        
                        yield f"data: {json.dumps({'type': 'log', 'message': f'[AI Filter] Processando lote {current_batch_num} de {total_batches}...'}, ensure_ascii=False)}\n\n"
                        
                        # Cria lista simplificada para o prompt para economizar tokens
                        batch_to_evaluate = []
                        for emp_idx, emp in enumerate(batch):
                            batch_to_evaluate.append({
                                "index": emp_idx,
                                "name": emp.get("name"),
                                "role": emp.get("role"),
                                "linkedin_url": emp.get("linkedin_url")
                            })
                            
                        prompt = f"""
Você é um especialista em estruturação organizacional B2B e prospecção de vendas.
Sua tarefa é analisar uma lista de perfis do LinkedIn e decidir se cada perfil é RELEVANTE ou não para uma abordagem focada em compras e logística.

Área de Foco principal: {area_focus or "Compras e Logística"}
Produto/Serviço a ser vendido (opcional): {product_focus or "Geral B2B"}

Diretrizes de Classificação:
1. Um perfil é RELEVANTE (relevant = true) se trabalhar com Compras, Procurement, Suprimentos, Logística, Supply Chain, Recebimento, Facilities, Importação/Exportação ou cargos de liderança operacional relacionados à cadeia de suprimentos.
2. Níveis hierárquicos aceitos: de Diretores a Assistentes/Compradores, desde que na área especificada.
3. Se um produto/serviço estiver especificado (ex: "Embalagens"), a relevância aumenta se o comprador for daquela categoria, mas qualquer comprador geral também é aceitável.
4. Pessoas de RH, Marketing, Vendas, TI (exceto se focado em compras de TI), Administrativo puro, Financeiro, Consultores externos que não sejam da empresa, e outros cargos não relacionados a suprimentos devem ser REJEITADOS (relevant = false).

Lista de perfis do lote atual:
{json.dumps(batch_to_evaluate, ensure_ascii=False, indent=2)}

Retorne APENAS um objeto JSON com a chave "decisions" contendo um array de objetos. Cada objeto deve mapear o "linkedin_url" do perfil correspondente, definindo se é "relevant" (boolean) e uma breve "reason" (string em português):
{{
  "decisions": [
    {{
      "linkedin_url": "...",
      "relevant": true,
      "reason": "Comprador de embalagens, diretamente relevante para o produto papelão."
    }}
  ]
}}
"""
                        try:
                            from core.llm import ask_llm, LLMTier
                            ai_res = await ask_llm(
                                prompt=prompt,
                                system="Você é um classificador especializado em leads B2B e organogramas de compras. Responda apenas com JSON estrito.",
                                json_mode=True,
                                tier=LLMTier.FAST,
                                cacheable=True
                            )
                            
                            data = ai_res.json_data or {}
                            decisions = data.get("decisions", [])
                            
                            decisions_map = {}
                            if isinstance(decisions, list):
                                for dec in decisions:
                                    url = dec.get("linkedin_url")
                                    if url:
                                        decisions_map[url] = dec.get("relevant", False)
                                        
                            for emp in batch:
                                url = emp.get("linkedin_url")
                                if url:
                                    is_relevant = decisions_map.get(url, False)
                                    if url not in decisions_map:
                                        # Fallback por palavra-chave se não respondeu
                                        keywords = ["compra", "suprimento", "procurement", "logistica", "logística", "supply", "facilities", "buyer", "sourcing"]
                                        role_lower = emp.get("role", "").lower()
                                        is_relevant = any(k in role_lower for k in keywords)
                                        
                                    emp_name = emp.get("name") or "Profissional"
                                    emp_role = emp.get("role") or ""
                                    if is_relevant:
                                        filtered_employees.append(emp)
                                        yield f"data: {json.dumps({'type': 'log', 'message': f'✅ [AI Aprovou] {emp_name} ({emp_role})'}, ensure_ascii=False)}\n\n"
                                    else:
                                        yield f"data: {json.dumps({'type': 'log', 'message': f'❌ [AI Filtrou] {emp_name} ({emp_role})'}, ensure_ascii=False)}\n\n"
                                else:
                                    filtered_employees.append(emp)
                        except Exception as e:
                            yield f"data: {json.dumps({'type': 'log', 'message': f'⚠️ [AI Warning] Falha na IA no lote: {str(e)}. Executando fallback por palavra-chave...'}, ensure_ascii=False)}\n\n"
                            keywords = ["compra", "suprimento", "procurement", "logistica", "logística", "supply", "facilities", "buyer", "sourcing"]
                            for emp in batch:
                                emp_name = emp.get("name") or "Profissional"
                                emp_role = emp.get("role") or ""
                                role_lower = emp_role.lower()
                                if any(k in role_lower for k in keywords):
                                    filtered_employees.append(emp)
                                    yield f"data: {json.dumps({'type': 'log', 'message': f'✅ [Fallback Aprovou] {emp_name} ({emp_role})'}, ensure_ascii=False)}\n\n"
                                else:
                                    yield f"data: {json.dumps({'type': 'log', 'message': f'❌ [Fallback Filtrou] {emp_name} ({emp_role})'}, ensure_ascii=False)}\n\n"
                                    
                    results_data = filtered_employees
                    yield f"data: {json.dumps({'type': 'log', 'message': f'🎉 [AI Filter] Filtragem concluída! Mantidos {len(results_data)} de {total_found} perfis.'}, ensure_ascii=False)}\n\n"
                
                yield f"data: {json.dumps({'type': 'result', 'data': results_data}, ensure_ascii=False)}\n\n"
                
                # Deleta o arquivo temporário
                try:
                    os.remove(output_filepath)
                except Exception:
                    pass
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': '[Agent Error] O arquivo de resultados não foi gerado pelo Scraper.'}, ensure_ascii=False)}\n\n"
                
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'[Agent Fatal Error] Falha na transmissão: {str(e)}'}, ensure_ascii=False)}\n\n"
            if process.poll() is None:
                process.terminate()
                
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
    
    if not active_scraper_process or active_scraper_process.poll() is not None:
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
            active_scraper_process.stdin.write(command)
            active_scraper_process.stdin.flush()
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
    
    if not active_scraper_process or active_scraper_process.poll() is not None:
        raise HTTPException(status_code=400, detail="Não há nenhum agente de raspagem ativo no momento.")
        
    try:
        active_scraper_process.stdin.write("cmd_stop\n")
        active_scraper_process.stdin.flush()
        return {"status": "success", "message": "Solicitação de parada graciosa enviada ao agente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao parar o agente graciosamente: {str(e)}")
