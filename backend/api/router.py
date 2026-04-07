from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import StreamingResponse
import json
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import httpx
import re
import os
from dotenv import load_dotenv

from core.rate_limiter import limiter
from services.b2b_scanner import discover_employees, discover_employees_stream
from services.filters import get_seniority_level, get_department_tag
from services.groq_service import refine_hierarchy_ai
from services.brand_discovery import discover_company_brand
from services.preview_service import get_url_preview
from services.database import get_db, Employee, Organization
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

def clean_cnpj(val: str) -> str:
    """Extrai apenas dígitos do CNPJ para APIs e Banco."""
    if not val: return ""
    import re
    return re.sub(r'\D', '', val)

router = APIRouter()

@router.get("/proxy/preview")
async def fetch_url_preview(
    url: str,
    role_hint: Optional[str] = Query(None),
    company_hint: Optional[str] = Query(None)
):
    """Retorna metadados Open Graph de uma URL para preview com fallbacks inteligentes."""
    return await get_url_preview(url, role_hint, company_hint)

@router.get("/proxy/image")
async def proxy_linkedin_image(url: str):
    """Proxy para carregar imagens do LinkedIn sem bloqueio de CORS."""
    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://www.linkedin.com/",
        "Connection": "keep-alive"
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return StreamingResponse(
                    resp.aiter_bytes(), 
                    media_type=resp.headers.get("content-type", "image/jpeg")
                )
            else:
                return StreamingResponse(iter([]), status_code=resp.status_code)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/hierarchy/refine")
async def refine_hierarchy(
    employees: List[dict],
    request: Request
):
    """
    Usa a Groq AI (Llama-3) para reavaliar os cargos e definir a hierarquia real, 
    ajustando os manager_ids e os níveis de cada nó.
    """
    print(f"[Backend AI] Iniciando refinamento de hierarquia para {len(employees)} nós...")
    
    # 1. Envia apenas funcionários válidos (ignora aviso, root, etc)
    raw_nodes = [e for e in employees if e.get("id") not in ["root_company", "aviso"]]
    
    if not raw_nodes:
        return {"nodes": employees}
        
    refined_map = await refine_hierarchy_ai(raw_nodes)
    
    # Se a IA falhou, retorna o original
    if not refined_map:
        return {"nodes": employees}
        
    # Mapear refinamentos por ID para busca rápida
    ref_dict = {r["id"]: r for r in refined_map}
    
    # 2. Atualizar a lista original com os novos níveis e gerentes
    updated_nodes = []
    for node in employees:
        ref_entry = ref_dict.get(node["id"])
        if ref_entry:
            node["level"] = ref_entry.get("level", node.get("level"))
            node["manager_id"] = ref_entry.get("manager_id", node.get("manager_id"))
        updated_nodes.append(node)
        
    print(f"[Backend AI] Refinamento concluído com sucesso.")
    return {"nodes": updated_nodes}

@router.get("/brand/discover")
async def discover_brand(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    domain: Optional[str] = Query(None, description="Domínio da empresa"),
    raw_name: Optional[str] = Query(None, description="Nome base da empresa")
):
    """
    Busca sugestões de nomes de marca (LinkedIn-ready) antes de iniciar o scan.
    """
    try:
        return await discover_company_brand(cnpj, domain, raw_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class EmployeeNode(BaseModel):
    id: str
    name: str
    role: str
    department: str
    company: Optional[str] = None
    manager_id: Optional[str] = None
    level: int = 5
    email: Optional[str] = None
    linkedin: Optional[str] = None
    url: Optional[str] = None
    education: Optional[str] = None
    location: Optional[str] = None
    connections: Optional[str] = None
    highlights: Optional[str] = None
    observations: Optional[str] = None

class HierarchyResponse(BaseModel):
    company_name: str
    identifier: str
    employees: List[EmployeeNode]

def clean_cnpj(cnpj: str) -> str:
    return re.sub(r"[^0-9]", "", cnpj)


@router.get("/hierarchy", response_model=HierarchyResponse)
@limiter.limit("10/minute") 
async def get_company_hierarchy(
    request: Request,
    cnpj: str = Query(..., description="O CNPJ da empresa (ex: 07.526.557/0001-00)"),
    domain: Optional[str] = Query(None, description="Opcional. O domínio da empresa (ex: empresa.com.br)")
):
    """
    Busca os dados reais da empresa e seus sócios/diretores na BrasilAPI.
    """
    print(f"[Backend] Recebida chamada para /hierarchy. CNPJ: {cnpj}, Domain: {domain}")
    
    # Força a re-leitura do .env a cada requisição (assim você não precisa reiniciar o Uvicorn)
    load_dotenv(override=True)
    EMAIL_API_KEY = os.getenv("EMAIL_API_KEY")
    
    cnpj_clean = clean_cnpj(cnpj)
    if len(cnpj_clean) != 14:
        raise HTTPException(status_code=400, detail="CNPJ Inválido. Deve conter 14 dígitos.")

    # 🏺 BUSCA EM CASCATA RESILIENTE (Plano A -> B -> C)
    data = None
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Camada 1: BRASILAPI (Padrão)
        try:
            resp = await client.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}")
            if resp.status_code == 200:
                data = resp.json()
        except: pass
        
        # Camada 2: MINHA RECEITA (Open Source - Estável)
        if not data:
            try:
                print(f"[Backend] BrasilAPI Limitada (429) - Tentando Fallback 1: Minha Receita...")
                resp = await client.get(f"https://minhareceita.org/{cnpj_clean}")
                if resp.status_code == 200:
                    data = resp.json()
            except: pass
            
        # Camada 3: RECEITAWS (Último recurso)
        if not data:
            try:
                print(f"[Backend] Minha Receita Limitada - Tentando Fallback 2: ReceitaWS...")
                resp = await client.get(f"https://receitaws.com.br/v1/cnpj/{cnpj_clean}")
                if resp.status_code == 200:
                    raw = resp.json()
                    # Mapeia para o padrão do nosso sistema
                    data = {
                        "razao_social": raw.get("nome"),
                        "nome_fantasia": raw.get("fantasia"),
                        "municipio": raw.get("municipio"),
                        "uf": raw.get("uf"),
                        "qsa": [{"nome_socio": s.get("nome"), "qualificacao_socio": s.get("qual")} for s in raw.get("qsa", [])]
                    }
            except: pass

    if not data:
        raise HTTPException(
            status_code=502, 
            detail="⚠️ Limite de requisições excedido em todas as APIs. Tente novamente em alguns minutos ou use um CNPJ diferente."
        )
            
    razao_social = data.get("razao_social") or data.get("nome_fantasia") or "Empresa Desconhecida"
    qsa = data.get("qsa", [])
    
    nodes: List[EmployeeNode] = []
    
    # Nó Raiz: A própria Empresa (Nível 0 - Entidade Suprema)
    nodes.append(EmployeeNode(
        id="root_company",
        name=razao_social[:30] + "..." if len(razao_social) > 30 else razao_social,
        role="Entidade Principal",
        department="Supply Chain (Matriz)",
        company=razao_social,
        manager_id=None,
        level=0
    ))
    
    # Lista temporária para poder recalcular a hierarquia de quem responde pra quem
    temp_employees = []
    
    # Sócios/Diretores vindos do Governo (Sempre Nível 1 ou nível baseado no cargo)
    for idx, socio in enumerate(qsa):
        cargo_socio = socio.get("qualificacao_socio", "Sócio")
        temp_employees.append(EmployeeNode(
            id=f"socio_{idx}",
            name=socio.get("nome_socio", "Sócio Anônimo"),
            role=cargo_socio,
            department="Quadro de Sócios (QSA)",
            company=razao_social,
            manager_id=None, # Definiremos depois calculando a hierarquia
            level=1 if "sócio" in cargo_socio.lower() or "administrador" in cargo_socio.lower() else get_seniority_level(cargo_socio)
        ))
        
    # -------------------------------------------------------------------------
    # 💡 INTEGRAÇÃO COM API DE EMAIL (OPCIONAL)
    # -------------------------------------------------------------------------
    # Inteligência de Tratamento de Nomes (Remove LTDA, SA, LLC)
    # -------------------------------------------------------------------------
    raw_name = data.get("nome_fantasia") or razao_social
    search_name = re.sub(r'(?i)\b(ltda|s\.a\.|s/a|limitada|s a|sa|s\.a)\b', '', raw_name).replace("-", " ").strip()
    if not search_name:
        search_name = razao_social # fallback
        
    cidade_matriz = data.get("municipio", "")
    
    # Se o front-end mandou um domínio exato, usamos ele (mais preciso para validação)
    # Senão, usamos a dedução básica que pode falhar em empresas complexas
    domain_guess = domain if domain else f"{search_name.lower().replace(' ', '')}.com.br"
    
    # -------------------------------------------------------------------------
    # 💡 MOTOR B2B GENÉRICO (OSINT LinkedIn - NÍVEL BRASIL)
    # -------------------------------------------------------------------------
    # Resolve funcionários de qualquer empresa brasileira. Filtro de filial bloqueia muita gente.
    custom_leads = discover_employees(search_name, domain_guess, email_api_key=EMAIL_API_KEY, max_results=100)
    for lead in custom_leads:
        cargo_custom = lead.get("role", "Especialista")
        temp_employees.append(EmployeeNode(
            id=f"engine_{len(temp_employees)}",
            name=lead.get("name", "Colaborador"),
            role=cargo_custom,
            department=get_department_tag(cargo_custom),
            company=lead.get("company"),
            manager_id=None,
            level=get_seniority_level(cargo_custom),
            email=lead.get("email"),
            linkedin=lead.get("linkedin")
        ))
        
    # Se não tiver QSA, retornamos apenas a empresa para a rede não ficar vazia
    if not qsa:
        temp_employees.append(EmployeeNode(
            id="aviso",
            name="Sem dados expandidos",
            role="Informação Pública Indisponível",
            department="Aviso",
            company=razao_social,
            manager_id="root_company",
            level=1
        ))
        
    # -------------------------------------------------------------------------
    # 🧠 ALGORITMO DE INTELIGÊNCIA DE REPORTING LINES (QUEM RESPONDE PRA QUEM) + CROSS MATCHING
    # -------------------------------------------------------------------------
    
    # 🎯 FILTRO EXCLUSIVO: CADEIA DE SUPRIMENTOS / OPERAÇÕES / COMPRAS
    # Mantemos apenas quem for da área de Suprimentos + as diretorias/sócios (matriz) para encabeçar
    supply_chain_employees = []
    for e in temp_employees:
        dept = get_department_tag(e.role)
        # Passa quem for de Supply/Compras (incluindo novas categorias) + Diretoria e os Sócios
        if any(keyword in dept for keyword in [
            "Compras", "Logística", "Diretoria Executiva", "Corporativo Geral", "QSA"
        ]) or "QSA" in e.department or e.id == "aviso":
            supply_chain_employees.append(e)

    # Substitui a lista de todos pelos filtrados
    temp_employees = supply_chain_employees

    # Agrupa funcionários por nível hierárquico
    levels_map = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
    for e in temp_employees:
        levels_map[e.level].append(e)

    # Conecta as pessoas ao cargo mais alto disponível logo acima, filtrando POR DEPARTAMENTO
    for e in temp_employees:
        assigned_manager = "root_company" # fallback supremo (CNPJ Matriz)
        my_dept = get_department_tag(e.role)
        
        # Procura um chefe compatível de cima (Nível Imediatamente acima) pra baixo (Nível 1)
        for senior_level in range(e.level - 1, 0, -1):
            if not levels_map.get(senior_level):
                continue
            
            candidates = levels_map[senior_level]
            
            # Filtro Semântico Especialista: Tenta validar chefe do MESMO departamento ou chefia Geral (C-Level/QSA)
            matching_bosses = [
                b for b in candidates 
                if get_department_tag(b.role) == my_dept 
                or any(keyword in get_department_tag(b.role) for keyword in [
                    "Diretoria Executiva", "Corporativo Geral", "Compras"
                ])
                or "QSA" in b.department
            ]
            
            if matching_bosses:
                assigned_manager = matching_bosses[0].id
                break
                
        e.manager_id = assigned_manager
        nodes.append(e)
        
    return HierarchyResponse(
        company_name=razao_social,
        identifier=cnpj_clean,
        employees=nodes
    )

@router.get("/hierarchy/stream")
async def stream_company_hierarchy(
    request: Request,
    cnpj: str = Query(..., description="CNPJ da empresa"),
    domain: Optional[str] = Query(None, description="Domínio da empresa"),
    confirmed_brand: Optional[str] = Query(None, description="Marca confirmada"),
    product_focus: Optional[str] = Query(None, description="Foco de categoria/produto (ex: Embalagens)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint SSE que envia dados progressivamente para a interface.
    """
    print(f"[Backend Streaming] Iniciando para CNPJ: {cnpj}, Domain: {domain}, Foco: {product_focus}")
    
    load_dotenv(override=True)
    EMAIL_API_KEY = os.getenv("EMAIL_API_KEY")
    cnpj_clean = clean_cnpj(cnpj)
    if len(cnpj_clean) != 14:
        raise HTTPException(status_code=400, detail="CNPJ Inválido")

    # Usamos generator assíncrono para o StreamingResponse lidar com requests do motor de IA
    async def generator():
        # 🏺 BUSCA EM CASCATA RESILIENTE (Streaming Initial Data)
        data = None
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Tenta BrasilAPI
            try:
                res = await client.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}")
                if res.status_code == 200:
                    data = res.json()
            except: pass
            
            # Tenta Fallback 1: Minha Receita
            if not data:
                try:
                    res = await client.get(f"https://minhareceita.org/{cnpj_clean}")
                    if res.status_code == 200:
                        data = res.json()
                except: pass

            # Tenta Fallback 2: ReceitaWS
            if not data:
                try:
                    res = await client.get(f"https://receitaws.com.br/v1/cnpj/{cnpj_clean}")
                    if res.status_code == 200:
                        raw = res.json()
                        data = {
                            "razao_social": raw.get("nome"),
                            "nome_fantasia": raw.get("fantasia"),
                            "municipio": raw.get("municipio"),
                            "uf": raw.get("uf"),
                            "qsa": [{"nome_socio": s.get("nome"), "qualificacao_socio": s.get("qual")} for s in raw.get("qsa", [])]
                        }
                except: pass

        if not data:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Não foi possível obter dados básicos da empresa em nenhuma API (BrasilAPI/MinhaReceita/ReceitaWS).', 'nodes': [], 'edges': []})}\n\n"
            return
            
        razao_social = data.get("razao_social") or data.get("nome_fantasia") or "Empresa"
        qsa = data.get("qsa", [])
        
        # Inicia a base de funcionários para encontrar os chefes
        hierarchy_pool = []
        
        initial_nodes = []
        
        # Nó Raiz
        root_node = {
            "id": "root_company",
            "name": razao_social[:30] + "..." if len(razao_social) > 30 else razao_social,
            "role": "Entidade Principal",
            "department": "Supply Chain (Matriz)",
            "manager_id": None,
            "level": 0
        }
        initial_nodes.append(root_node)
        hierarchy_pool.append(EmployeeNode(**root_node))
        
        # Sócios QSA (Sempre Nível 6 - Autoridade Máxima)
        for idx, socio in enumerate(qsa):
            cargo_socio = socio.get("qualificacao_socio", "Sócio")
            s_node = {
                "id": f"socio_{idx}",
                "name": socio.get("nome_socio", "Sócio Anônimo"),
                "role": cargo_socio,
                "department": "Quadro de Sócios (QSA)",
                "manager_id": "root_company",
                "level": 6
            }
            initial_nodes.append(s_node)
            hierarchy_pool.append(EmployeeNode(**s_node))
            
        if not qsa:
            initial_nodes.append({
                "id": "aviso",
                "name": "Sem dados QSA",
                "role": "Público Indisponível",
                "department": "Aviso",
                "manager_id": "root_company",
                "level": 6
            })
            
        # Passamos o endereço da matriz para o motor focar na localização correta
        city = data.get("municipio", "")
        state = data.get("uf", "")
        location_focus = f"{city}, {state}" if city else None
        
        raw_name = data.get("nome_fantasia") or razao_social
        search_name = re.sub(r'(?i)\b(ltda|s\.a\.|s/a|limitada|s a|sa|s\.a)\b', '', raw_name).replace("-", " ").strip()
        if not search_name: search_name = razao_social
        domain_guess = domain if domain else f"{search_name.lower().replace(' ', '')}.com.br"
        
        # 2. Streaming de Motor B2B Progressivo
        initial_nodes.sort(key=lambda x: x.get('level', 1), reverse=True) # Ordem decrescente (6 primeiro)
        yield f"data: {json.dumps({'type': 'initial', 'company_name': razao_social, 'nodes': initial_nodes})}\n\n"
        
        async for batch in discover_employees_stream(search_name, domain_guess, confirmed_brand=confirmed_brand, location=location_focus, product_focus=product_focus, email_api_key=EMAIL_API_KEY, max_results=100):
            new_nodes = []
            
            for lead in batch:
                href = lead.get("linkedin", "")
                name_norm = lead.get("name", "").lower().strip()
                
                # ID Persistente vindo do motor (mantém sub-perfis em amálgamas) ou baseado no LinkedIn
                node_id = lead.get("id")
                if not node_id:
                    node_id = f"node_{re.sub(r'[^a-zA-Z0-9]', '_', href.split('/in/')[-1])}" if '/in/' in href else f"node_{hash(href)}"
                
                # Deduplicação proativa: Se já temos esse LinkedIn OU esse nome exatamente igual com o mesmo cargo
                if any(h.id == node_id or (h.name.lower() == name_norm and h.role.lower() == lead.get("role", "").lower()) for h in hierarchy_pool):
                    continue

                cargo = lead.get("role", "Professional")
                dept = lead.get("department", "Operations")
                linkedin_url = lead.get("url") or lead.get("linkedin", "")
                
                emp = EmployeeNode(
                    id=node_id,
                    name=lead.get("name", "Colaborador"),
                    role=cargo,
                    department=dept,
                    company=lead.get("company"),
                    manager_id=None,
                    level=lead.get("level", 1),
                    email=lead.get("email"),
                    linkedin=linkedin_url,
                    url=linkedin_url,
                    education=lead.get("education"),
                    location=lead.get("location"),
                    connections=lead.get("connections"),
                    highlights=lead.get("highlights"),
                    observations=lead.get("observations")
                )
                
                # Encontrar chefe existente no hierarchy_pool
                assigned_manager = "root_company"
                my_dept = emp.department
                
                levels_map = {0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
                for existing in hierarchy_pool:
                    levels_map[existing.level].append(existing)
                    
                # Tentativa de conexão hierárquica por departamento (Olhando para Cima: Nível + 1 até 6)
                for senior_level in range(emp.level + 1, 7):
                    if not levels_map.get(senior_level): continue
                    candidates = levels_map[senior_level]
                    
                    # Prioridade 1: Mesmo Departamento ou Diretoria/Sócios
                    matching_bosses = [
                        b for b in candidates 
                        if b.department == my_dept 
                        or any(k in b.department for k in ["Diretoria Executiva", "Raiz", "Administração", "Quadro de Sócios (QSA)"])
                    ]
                    
                    if matching_bosses:
                        assigned_manager = matching_bosses[0].id
                        break
                    
                    # 💡 NOVO FALLBACK: Se não tem ninguém do dpto ou executivo neste andar, 
                    # mas TEM alguém de outro setor, conecta logo nele (Mais Próximo Disponível)
                    if candidates:
                        assigned_manager = candidates[0].id
                        break
                        
                emp.manager_id = assigned_manager
                
                # 🔄 DINAMISMO HIERÁRQUICO (Efeito Ímã Aprimorado)
                # Se este novo nó for Senior em relação a outros, ele os "puxa" para baixo dele
                reparented_nodes = []
                if emp.level > 1: # Se é pelo menos Especialista/Líder
                    for existing in hierarchy_pool:
                        # Se o existente é de nível inferior (Número menor) e mesmo departamento
                        is_subordinate = (existing.level < emp.level)
                        same_dept = (existing.department == emp.department) or (emp.department == "Quadro de Sócios (QSA)")
                        
                        # NOVA REGRA: Ele puxa se o subordinado estiver na raiz ou num CEO genérico
                        is_orphan = (existing.manager_id == "root_company")
                        is_executive_managed = (existing.manager_id and str(existing.manager_id).startswith("socio_"))
                        
                        if is_subordinate and same_dept and (is_orphan or is_executive_managed):
                            existing.manager_id = emp.id
                            reparented_nodes.append(existing.dict())
                
                hierarchy_pool.append(emp)
                new_nodes.append(emp.dict())
                if reparented_nodes:
                    new_nodes.extend(reparented_nodes)
                
            if new_nodes:
                yield f"data: {json.dumps({'type': 'batch', 'nodes': new_nodes}, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")

@router.get("/hierarchy/{org_id}")
async def get_stored_hierarchy(org_id: int, db: AsyncSession = Depends(get_db)):
    """Busca a hierarquia já salva no banco de dados."""
    stmt = select(Employee).where(Employee.company_id == org_id).order_by(Employee.seniority.asc())
    result = await db.execute(stmt)
    employees = result.scalars().all()
    
    nodes = []
    for emp in employees:
        nodes.append({
            "id": f"emp_{emp.id}",
            "name": emp.name,
            "role": emp.role,
            "level": 6 - emp.seniority if emp.seniority < 6 else 1,
            "seniority": emp.seniority,
            "linkedin": emp.linkedin_url,
            "profile_pic": emp.profile_pic,
            "email": emp.email
        })
    
    return {"nodes": nodes}

# --- PIPEDRIVE SYNC (REFACTORED) ---
@router.post("/pipedrive_sync")
async def pipedrive_sync_endpoint():
    """Endpoint para mover tarefas atrasadas para hoje."""
    try:
        from services.pipedrive_service import pipedrive_service
        return await pipedrive_service.sync_overdue_activities()
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pipedrive_smart_sync")
async def pipedrive_smart_sync_endpoint():
    """Endpoint para remanejar tarefas de forma inteligente (10/dia + prioridade)."""
    try:
        from services.pipedrive_service import pipedrive_service
        return await pipedrive_service.smart_reschedule_activities()
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pipedrive/organizations")
async def get_pipedrive_organizations():
    """Retorna lista de todas as empresas do Pipedrive."""
    try:
        from services.pipedrive_service import pipedrive_service
        return await pipedrive_service.list_organizations()
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/intelligence/enrich")
async def enrich_company_data(
    name: str = Query(..., description="Nome da empresa"),
    address: Optional[str] = Query(None, description="Pista de endereço para filtrar filiais"),
    cnpj: Optional[str] = Query(None, description="CNPJ fornecido manualmente"),
    force: bool = Query(False, description="Forçar nova busca ignorando cache")
):
    """Endpoint para descobrir CNPJ, Domínio e Selecionar Filiais via OSINT + IA."""
    try:
        from services.intelligence_service import intelligence_service
        return await intelligence_service.enrich_company(name, hint_address=address, force_refresh=force, cnpj=cnpj)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

class ConfirmEnrichRequest(BaseModel):
    name: str
    cnpj: Optional[str] = None
    domain: Optional[str] = None
    address: Optional[str] = None
    pipedrive_id: Optional[int] = None

@router.post("/intelligence/confirm")
async def confirm_enrich_data(payload: ConfirmEnrichRequest):
    """Persiste a escolha manual do usuário no banco local (Neon DB)."""
    try:
        from services.database import async_session, Organization
        from sqlalchemy import select
        
        async with async_session() as session:
            # 🏺 UPSERT: Atualiza se já existir pelo nome ou pipedrive_id
            stmt = select(Organization).where((Organization.name == payload.name) | (Organization.pipedrive_id == payload.pipedrive_id))
            res = await session.execute(stmt)
            org = res.scalars().first()
            
            if not org:
                org = Organization(name=payload.name, pipedrive_id=payload.pipedrive_id)
                session.add(org)
            
            org.cnpj = payload.cnpj
            org.domain = payload.domain
            org.address = payload.address
            
            await session.commit()
            return {"status": "success", "message": f"Inteligência de '{payload.name}' gravada com sucesso."}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/pipedrive/organizations/{org_id}")
async def update_pipedrive_org(org_id: int, payload: Dict[str, Any]):
    """Atualiza dados reais no Pipedrive (CNPJ, Domínio, Endereço etc)."""
    try:
        from services.pipedrive_service import pipedrive_service
        success = await pipedrive_service.update_organization(org_id, payload)
        if success:
            return {"status": "success", "message": f"Organização {org_id} atualizada no Pipedrive."}
        else:
            raise Exception("Erro ao atualizar no Pipedrive.")
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))
