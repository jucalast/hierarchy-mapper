from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import StreamingResponse
import json
from pydantic import BaseModel
from typing import List, Optional
from core.rate_limiter import limiter
import httpx
import re
import os
from dotenv import load_dotenv
from api.b2b_engine import discover_employees, discover_employees_stream

# Retiramos os os.getenv globais para ler dinamicamente dentro da rota!

router = APIRouter()

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
    company: Optional[str] = None

class HierarchyResponse(BaseModel):
    company_name: str
    identifier: str
    employees: List[EmployeeNode]

def clean_cnpj(cnpj: str) -> str:
    return re.sub(r"[^0-9]", "", cnpj)

def get_role_level(role: str) -> int:
    """
    Classificação hierárquica especializada para Supply Chain/Procurement.
    Baseada na estrutura corporativa real de compras e suprimentos.
    """
    role = role.lower()
    
    # Nível 1: C-Level Executivo (Diretoria, CPO, C-Suite)
    if any(x in role for x in ['cpo', 'diretor', 'director', 'chief', 'vp', 'vice president', 'presidente', 'executivo']):
        # Evita confundir 'comprador executivo' com 'diretor executivo'
        if 'comprador' in role or 'buyer' in role: return 4
        return 1
    
    # Nível 2: Gestão Gerencial (Gerentes)
    if any(x in role for x in ['gerente', 'manager', 'head']):
        return 2
    
    # Nível 3: Supervisão e Coordenação (Tático)
    if any(x in role for x in ['coordenador', 'coordinator', 'supervisor', 'líder', 'leader', 'lead']):
        return 3
    
    # Nível 4: Analítico Especialista/Sênior (Técnico Sr)
    if any(x in role for x in ['especialista', 'specialist', 'category manager', 'strategic sourcing', 'sênior', 'senior', 'pleno', 'mid']):
        return 4
    
    # Nível 5: Analítico Júnior e Operacional (Suporte/Execução)
    if any(x in role for x in ['júnior', 'jr', 'analista', 'analyst', 'comprador', 'buyer', 'assistente', 'assistant', 'auxiliar', 'operador', 'suporte', 'estagiário', 'intern']):
        return 5
    
    return 5

def get_department_tag(role: str) -> str:
    """
    Classificação departamental especializada para Supply Chain/Procurement.
    Identifica categorias específicas de compras e suprimentos.
    """
    role = role.lower()
    
    # Categorias Estratégicas (Direct Spend)
    if any(x in role for x in [
        'strategic sourcing', 'category manager', 'especialista em embalagem',
        'packaging buyer', 'raw material buyer', 'commodity manager'
    ]):
        return "Compras Estratégicas"
    
    # Compras Indiretas (Indirect Spend)
    if any(x in role for x in [
        'indirect procurement', 'mro buyer', 'facility buyer',
        'compras indiretas', 'comprador mro', 'compras serviços'
    ]):
        return "Compras Indiretas"
    
    # CAPEX (Capital Expenditure)
    if any(x in role for x in [
        'capex buyer', 'investment buyer', 'compras de capital',
        'equipment buyer', 'comprador de bens de capital'
    ]):
        return "Compras CAPEX"
    
    # Marketing e Serviços
    if any(x in role for x in [
        'marketing procurement', 'media buyer', 'agency procurement',
        'compras marketing', 'compras agências'
    ]):
        return "Compras Marketing"
    
    # Logística e Operações
    if any(x in role for x in [
        'logística', 'logistic', 'supply chain', 'operações',
        'warehouse', 'distribuição', 'transporte'
    ]):
        return "Logística & Operações"
    
    # Compras Gerais (fallback)
    if any(x in role for x in [
        'comprador', 'buyer', 'compras', 'procurement',
        'sourcing', 'purchasing', 'suprimentos'
    ]):
        return "Compras Gerais"
    
    # Outros departamentos (mantém lógica original)
    if any(x in role for x in ['marketing', 'mkt', 'growth']): return "Marketing"
    if any(x in role for x in ['venda', 'sales', 'comercial', 'business development', 'bd', 'sdr', 'bdr', 'executivo de', 'account', 'conta']): return "Vendas & Comercial"
    if any(x in role for x in ['ti', 'it', 'tecnologia', 'tech', 'software', 'data', 'dados', 'engenhar', 'engineer', 'developer', 'desenvolvedor', 'sistemas', 'infraestrutura']): return "Tecnologia & T.I."
    if any(x in role for x in ['rh', 'hr', 'human resources', 'recursos humanos', 'talent', 'pessoas', 'people', 'recrutamento', 'recruiter']): return "Recursos Humanos"
    if any(x in role for x in ['finanç', 'finance', 'cfo', 'contábil', 'contabil', 'tesouraria']): return "Financeiro"
    if any(x in role for x in ['jurídic', 'juridic', 'legal', 'advogad', 'compliance']): return "Jurídico"
    if any(x in role for x in ['produto', 'product']): return "Produto"
    if any(x in role for x in ['ceo', 'presidente', 'founder', 'sócio', 'socio', 'dono']): return "Diretoria Executiva"
    return "Corporativo Geral"

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

    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=15.0)
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail="CNPJ não encontrado.")
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Erro ao comunicar com a BrasilAPI: {str(e)}")
            
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
            level=1 if "sócio" in cargo_socio.lower() or "administrador" in cargo_socio.lower() else get_role_level(cargo_socio)
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
            level=get_role_level(cargo_custom),
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
@limiter.limit("10/minute") 
async def stream_company_hierarchy(
    request: Request,
    cnpj: str = Query(..., description="O CNPJ da empresa"),
    domain: Optional[str] = Query(None, description="Opcional. O domínio da empresa")
):
    """
    Endpoint SSE que envia dados progressivamente para a interface.
    """
    print(f"[Backend Streaming] Iniciando para CNPJ: {cnpj}, Domain: {domain}")
    
    load_dotenv(override=True)
    EMAIL_API_KEY = os.getenv("EMAIL_API_KEY")
    cnpj_clean = clean_cnpj(cnpj)
    if len(cnpj_clean) != 14:
        raise HTTPException(status_code=400, detail="CNPJ Inválido")

    # Usamos generator síncrono para o StreamingResponse lidar com requests blocking do DDG
    def generator():
        # 1. Chamada Síncrona para BrasilAPI
        url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}"
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url)
                if res.status_code == 404:
                    return # Fim do stream silencioso
                res.raise_for_status()
                data = res.json()
        except:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Erro BrasilAPI', 'nodes': [], 'edges': []})}\n\n"
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
        
        # Sócios QSA
        for idx, socio in enumerate(qsa):
            cargo_socio = socio.get("qualificacao_socio", "Sócio")
            s_node = {
                "id": f"socio_{idx}",
                "name": socio.get("nome_socio", "Sócio Anônimo"),
                "role": cargo_socio,
                "department": "Quadro de Sócios (QSA)",
                "manager_id": "root_company",
                "level": 1 if "sócio" in cargo_socio.lower() or "administrador" in cargo_socio.lower() else get_role_level(cargo_socio)
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
                "level": 1
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
        yield f"data: {json.dumps({'type': 'initial', 'company_name': razao_social, 'nodes': initial_nodes})}\n\n"
        
        engine_idx = 0
        for batch in discover_employees_stream(search_name, domain_guess, location=location_focus, email_api_key=EMAIL_API_KEY, max_results=100):
            new_nodes = []
            
            # Filtro de departamento
            filtered_batch = []
            for lead in batch:
                cargo = lead.get("role", "Especialista")
                dept = get_department_tag(cargo)
                if any(k in dept for k in ["Compras", "Logística", "Diretoria", "Corporativo"]):
                    filtered_batch.append(lead)
            
            for lead in filtered_batch:
                cargo = lead.get("role", "Especialista")
                emp = EmployeeNode(
                    id=f"engine_{engine_idx}",
                    name=lead.get("name", "Colaborador"),
                    role=cargo,
                    department=get_department_tag(cargo),
                    company=lead.get("company"),
                    manager_id=None,
                    level=get_role_level(cargo),
                    email=lead.get("email"),
                    linkedin=lead.get("linkedin")
                )
                engine_idx += 1
                
                # Encontrar chefe existente no hierarchy_pool
                assigned_manager = "root_company"
                my_dept = emp.department
                
                levels_map = {0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
                for existing in hierarchy_pool:
                    levels_map[existing.level].append(existing)
                    
                for senior_level in range(emp.level - 1, 0, -1):
                    if not levels_map.get(senior_level): continue
                    candidates = levels_map[senior_level]
                    matching_bosses = [
                        b for b in candidates 
                        if b.department == my_dept 
                        or any(k in b.department for k in ["Diretoria Executiva", "Corporativo Geral", "Compras", "QSA"])
                    ]
                    if matching_bosses:
                        assigned_manager = matching_bosses[0].id
                        break
                        
                emp.manager_id = assigned_manager
                hierarchy_pool.append(emp)
                new_nodes.append(emp.dict())
                
            if new_nodes:
                yield f"data: {json.dumps({'type': 'batch', 'nodes': new_nodes})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
    return StreamingResponse(generator(), media_type="text/event-stream")
