from fastapi import APIRouter, Depends, Query, Request, HTTPException
from fastapi.responses import StreamingResponse
import json
import re
import os
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from models import Employee, Organization
from services.hierarchy.b2b_scanner import discover_employees, discover_employees_stream
from services.hierarchy.filters import get_seniority_level, get_department_tag
from services.external.groq_service import refine_hierarchy_ai
from api.v1.schemas import EmployeeNode, HierarchyResponse, clean_cnpj

router = APIRouter()

@router.post("/refine")
async def refine_hierarchy(
    employees: List[dict],
    db: AsyncSession = Depends(get_db)
):
    """
    Usa a Groq AI (Llama-3) para reavaliar os cargos e definir a hierarquia real, 
    ajustando os manager_ids e os níveis de cada nó, e SALVA no banco local.
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
    
    # 2. Atualizar a lista original e PERSISTIR no banco
    updated_nodes = []
    
    # 🕵️ Mapeamento de IDs Efêmeros para IDs de Banco Reais para esta leva
    # Isso é CRUCIAL para que o manager_id salvo no banco seja estável e referenciável
    ephemeral_to_db_id = {}
    org_id = None
    
    # Primeiro, buscamos todos os funcionários desta leva no banco para ter os IDs reais
    for node in employees:
        stmt = select(Employee).where(Employee.name == node.get("name"), Employee.role == node.get("role"))
        res = await db.execute(stmt)
        emp_db = res.scalars().first()
        if emp_db:
            ephemeral_to_db_id[node["id"]] = f"node_{emp_db.id}"
            if not org_id: org_id = emp_db.company_id

    for node in employees:
        original_id = node.get("id")
        
        # Sincroniza o ID do próprio nó com o banco de dados se houver mapeamento
        if original_id in ephemeral_to_db_id:
            node["id"] = ephemeral_to_db_id[original_id]
            
        ref_entry = ref_dict.get(original_id)
        if ref_entry:
            new_level = ref_entry.get("level", node.get("level"))
            new_manager_id = ref_entry.get("manager_id", node.get("manager_id"))
            
            # Garantir que funcionário não seja Nível 0 (reservado para a empresa)
            if original_id != "root_company" and new_level == 0:
                new_level = get_seniority_level(node.get("role", ""))

            # 🛠️ RESOLUÇÃO DE MANAGER ID PARA PERSISTÊNCIA ESTÁVEL
            # Se a IA sugeriu um ID efêmero (ex: node_fulano), tentamos converter para o ID Real (node_45)
            # Isso faz com que ao "puxar" do banco, o relacionamento já venha resolvido e correto.
            final_manager_id = new_manager_id
            if new_manager_id in ephemeral_to_db_id:
                final_manager_id = ephemeral_to_db_id[new_manager_id]
            elif new_manager_id == "root_company":
                final_manager_id = "root_company"

            # 🛡️ TRAVA DE SEGURANÇA MÁXIMA: Sócios e Root são imutáveis no refinamento
            if node.get("level") == 6 or node.get("department") == "Quadro de Sócios (QSA)" or original_id == "root_company":
                print(f"      [Backend AI] 🛡️ Protegendo integridade do Sócio/Root: {node.get('name')}")
                new_level = node.get("level", 6)
                final_manager_id = "root_company" if original_id != "root_company" else None
            
            node["level"] = new_level
            node["manager_id"] = final_manager_id
            
            # Persistência no Banco de Dados
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
        print(f"[Backend AI] Persistência concluída para Org ID {org_id}.")
        
    print(f"[Backend AI] Refinamento concluído com sucesso.")
    return {"nodes": updated_nodes}

@router.get("", response_model=HierarchyResponse)
async def get_company_hierarchy(
    request: Request,
    cnpj: str = Query(..., description="O CNPJ da empresa (ex: 07.526.557/0001-00)"),
    domain: Optional[str] = Query(None, description="Opcional. O domínio da empresa (ex: empresa.com.br)")
):
    """
    Busca os dados reais da empresa e seus sócios/diretores na BrasilAPI.
    """
    print(f"[Backend] Recebida chamada para /hierarchy. CNPJ: {cnpj}, Domain: {domain}")
    
    load_dotenv(override=True)
    EMAIL_API_KEY = os.getenv("EMAIL_API_KEY")
    
    cnpj_clean = clean_cnpj(cnpj)
    if len(cnpj_clean) != 14:
        raise HTTPException(status_code=400, detail="CNPJ Inválido. Deve conter 14 dígitos.")

    # 🏺 BUSCA EM CASCATA RESILIENTE (Plano A -> B -> C)
    data = None
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Camada 1: BRASILAPI
        try:
            resp = await client.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}")
            if resp.status_code == 200:
                data = resp.json()
        except: pass
        
        # Camada 2: MINHA RECEITA
        if not data:
            try:
                print(f"[Backend] BrasilAPI Limitada (429) - Tentando Fallback 1: Minha Receita...")
                resp = await client.get(f"https://minhareceita.org/{cnpj_clean}")
                if resp.status_code == 200:
                    data = resp.json()
            except: pass
            
        # Camada 3: RECEITAWS
        if not data:
            try:
                print(f"[Backend] Minha Receita Limitada - Tentando Fallback 2: ReceitaWS...")
                resp = await client.get(f"https://receitaws.com.br/v1/cnpj/{cnpj_clean}")
                if resp.status_code == 200:
                    raw = resp.json()
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
    
    # Nó Raiz
    nodes.append(EmployeeNode(
        id="root_company",
        name=razao_social[:30] + "..." if len(razao_social) > 30 else razao_social,
        role="Entidade Principal",
        department="Supply Chain (Matriz)",
        company=razao_social,
        manager_id=None,
        level=0
    ))
    
    temp_employees = []
    for idx, socio in enumerate(qsa):
        cargo_socio = socio.get("qualificacao_socio", "Sócio")
        temp_employees.append(EmployeeNode(
            id=f"socio_{idx}",
            name=socio.get("nome_socio", "Sócio Anônimo"),
            role=cargo_socio,
            department="Quadro de Sócios (QSA)",
            company=razao_social,
            manager_id=None,
            level=1 if "sócio" in cargo_socio.lower() or "administrador" in cargo_socio.lower() else get_seniority_level(cargo_socio)
        ))
        
    raw_name = data.get("nome_fantasia") or razao_social
    search_name = re.sub(r'(?i)\b(ltda|s\.a\.|s/a|limitada|s a|sa|s\.a)\b', '', raw_name).replace("-", " ").strip()
    if not search_name: search_name = razao_social
    domain_guess = domain if domain else f"{search_name.lower().replace(' ', '')}.com.br"
    
    custom_leads = await discover_employees(search_name, domain_guess, email_api_key=EMAIL_API_KEY, max_results=100)
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
        
    supply_chain_employees = []
    for e in temp_employees:
        dept = get_department_tag(e.role)
        if any(keyword in dept for keyword in [
            "Compras", "Logística", "Diretoria Executiva", "Corporativo Geral", "QSA"
        ]) or "QSA" in e.department or e.id == "aviso":
            supply_chain_employees.append(e)

    temp_employees = supply_chain_employees
    levels_map = {1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
    for e in temp_employees:
        levels_map[e.level].append(e)

    for e in temp_employees:
        assigned_manager = "root_company"
        my_dept = get_department_tag(e.role)
        for senior_level in range(e.level - 1, 0, -1):
            if not levels_map.get(senior_level): continue
            candidates = levels_map[senior_level]
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

@router.get("/stream")
async def stream_company_hierarchy(
    request: Request,
    cnpj: str = Query(..., description="CNPJ da empresa"),
    domain: Optional[str] = Query(None, description="Domínio da empresa"),
    confirmed_brand: Optional[str] = Query(None, description="Marca confirmada"),
    confirmed_logo: Optional[str] = Query(None, description="Logo confirmado do LinkedIn"),
    product_focus: Optional[str] = Query(None, description="Foco de categoria/produto (ex: Embalagens)"),
    area_focus: Optional[str] = Query("compras", description="Área de foco (compras ou logistica)"),
    db: AsyncSession = Depends(get_db)
):
    """Endpoint SSE que envia dados progressivamente para a interface."""
    print(f"[Backend Streaming] Iniciando para CNPJ: {cnpj}, Domain: {domain}, Foco: {product_focus}, Área: {area_focus}")
    
    load_dotenv(override=True)
    EMAIL_API_KEY = os.getenv("EMAIL_API_KEY")
    cnpj_clean = clean_cnpj(cnpj)
    
    async def generator():
        data = None
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}")
                if res.status_code == 200: data = res.json()
            except: pass
            if not data:
                try:
                    res = await client.get(f"https://minhareceita.org/{cnpj_clean}")
                    if res.status_code == 200: data = res.json()
                except: pass
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
            yield f"data: {json.dumps({'type': 'error', 'message': 'Houve um erro geral nas APIs.'})}\n\n"
            return
            
        razao_social = data.get("razao_social") or data.get("nome_fantasia") or "Empresa"
        qsa = data.get("qsa", [])
        
        hierarchy_pool = []
        initial_nodes = []
        
        # 💾 PERSISTÊNCIA INCREMENTAL DA EMPRESA
        org_id = None
        cnpj_clean = clean_cnpj(cnpj)
        
        # Composição do endereço completo
        full_address = ""
        if data:
            addr_parts = []
            if data.get("logradouro"): addr_parts.append(f"{data.get('logradouro')}, {data.get('numero') or 'S/N'}")
            if data.get("complemento"): addr_parts.append(str(data.get("complemento")))
            if data.get("bairro"): addr_parts.append(str(data.get("bairro")))
            if data.get("municipio"): addr_parts.append(f"{data.get('municipio')}-{data.get('uf')}")
            if data.get("cep"): addr_parts.append(f"CEP: {data.get('cep')}")
            full_address = " | ".join(addr_parts)

        try:
            # 🏺 BUSCA RESILIENTE (Cascata: CNPJ -> Domínio -> Nome)
            org = None
            # 1. Tenta por CNPJ
            stmt_cnpj = select(Organization).where(Organization.cnpj == cnpj_clean)
            res_cnpj = await db.execute(stmt_cnpj)
            org = res_cnpj.scalars().first()
            
            # 2. Se não achou, tenta por Domínio (se disponível)
            if not org and domain:
                stmt_dom = select(Organization).where(Organization.domain == domain)
                res_dom = await db.execute(stmt_dom)
                org = res_dom.scalars().first()
            
            # 3. Se ainda não achou, tenta por Nome (Case Insensitive)
            if not org:
                # Remove variações comuns para melhorar o match
                clean_name = confirmed_brand or razao_social
                stmt_name = select(Organization).where(func.lower(Organization.name) == clean_name.lower())
                res_name = await db.execute(stmt_name)
                org = res_name.scalars().first()

            if not org:
                # 🚀 CRIAR NO PIPEDRIVE SE FOR NOVA
                from services.pipedrive.pipedrive_service import pipedrive_service
                
                new_name = confirmed_brand or (razao_social[:30] + "..." if len(razao_social) > 30 else razao_social)
                p_id = await pipedrive_service.create_organization({
                    "name": new_name,
                    "address": full_address,
                    "domain": domain
                })
                
                org = Organization(
                    name=new_name,
                    cnpj=cnpj_clean,
                    domain=domain,
                    address=full_address,
                    category=area_focus,
                    product_focus=product_focus,
                    pipedrive_id=p_id # Salva o ID retornado (ou None se falhou)
                )
                db.add(org)
                await db.flush()
                print(f"[Stream] Nova empresa criada. Local ID: {org.id}, Pipedrive ID: {p_id}")
            else:
                # 🔄 ATUALIZAÇÃO SÍNCRONA: Une o CNPJ aos dados que já existiam
                if not org.cnpj: org.cnpj = cnpj_clean
                if not org.address or len(org.address) < 5: org.address = full_address
                if confirmed_brand: org.name = confirmed_brand
                if domain and not org.domain: org.domain = domain
                if area_focus: org.category = area_focus
                if product_focus: org.product_focus = product_focus
                
                # Se ela existia no banco local mas não tinha Pipedrive ID (caso raro), tenta criar agora
                if not org.pipedrive_id:
                    from services.pipedrive.pipedrive_service import pipedrive_service
                    p_id = await pipedrive_service.create_organization({
                        "name": org.name,
                        "address": org.address,
                        "domain": org.domain
                    })
                    if p_id:
                        org.pipedrive_id = p_id
                        print(f"[Stream] Empresa existente vinculada ao Pipedrive. ID: {p_id}")
            
            org_id = org.id
            await db.commit()
        except Exception as e:
            print(f"[DB] Erro ao salvar Organização: {e}")

        root_node = {
            "id": "root_company",
            "name": confirmed_brand or (razao_social[:30] + "..." if len(razao_social) > 30 else razao_social),
            "role": "Entidade Principal",
            "department": "Supply Chain (Matriz)",
            "manager_id": None,
            "level": 0,
            "company_logo": confirmed_logo,
            "domain": domain
        }
        initial_nodes.append(root_node)
        hierarchy_pool.append(EmployeeNode(**root_node))
        
        # 💾 PERSISTÊNCIA DOS SÓCIOS (QSA)
        for idx, socio in enumerate(qsa):
            name_socio = socio.get("nome_socio", "Sócio Anônimo")
            role_socio = socio.get("qualificacao_socio", "Sócio")
            clean_socio_id = f"socio_{re.sub(r'[^a-zA-Z0-9]', '_', name_socio.lower())}"
            s_node = {"id": clean_socio_id, "name": name_socio, "role": role_socio, "department": "Quadro de Sócios (QSA)", "manager_id": "root_company", "level": 6}
            initial_nodes.append(s_node)
            hierarchy_pool.append(EmployeeNode(**s_node))
            
            # Salva o sócio no banco se ainda não existir
            if org_id:
                try:
                    stmt_s = select(Employee).where(Employee.name == name_socio, Employee.company_id == org_id)
                    res_s = await db.execute(stmt_s)
                    if not res_s.scalars().first():
                        db.add(Employee(
                            name=name_socio,
                            role=role_socio,
                            seniority=6,
                            company_id=org_id,
                            manager_id="root_company",
                            description="Sócio (QSA)"
                        ))
                except: pass
        
        if org_id: await db.commit()

        if not qsa:
            initial_nodes.append({"id": "aviso", "name": "Sem dados QSA", "role": "Público Indisponível", "department": "Aviso", "manager_id": "root_company", "level": 6})
            
        city = data.get("municipio", "")
        state = data.get("uf", "")
        location_focus = f"{city}, {state}" if city else None
        raw_name = data.get("nome_fantasia") or razao_social
        search_name = re.sub(r'(?i)\b(ltda|s\.a\.|s/a|limitada|s a|sa|s\.a)\b', '', raw_name).replace("-", " ").strip()
        domain_guess = domain if domain else f"{search_name.lower().replace(' ', '')}.com.br"
        
        initial_nodes.sort(key=lambda x: x.get('level', 1), reverse=True)
        yield f"data: {json.dumps({'type': 'initial', 'company_name': razao_social, 'nodes': initial_nodes})}\n\n"
        
        async for batch in discover_employees_stream(search_name, domain_guess, confirmed_brand=confirmed_brand, location=location_focus, product_focus=product_focus, area_focus=area_focus, email_api_key=EMAIL_API_KEY, max_results=100):
            new_nodes = []
            for lead in batch:
                href = lead.get("linkedin", "")
                name_norm = lead.get("name", "").lower().strip()
                node_id = lead.get("id")
                if not node_id:
                    node_id = f"node_{re.sub(r'[^a-zA-Z0-9]', '_', href.split('/in/')[-1])}" if '/in/' in href else f"node_{hash(href)}"
                
                if any(h.id == node_id or (h.name.lower() == name_norm and h.role.lower() == lead.get("role", "").lower()) for h in hierarchy_pool):
                    continue

                emp = EmployeeNode(
                    id=node_id, name=lead.get("name", "Colaborador"), role=lead.get("role", "Professional"), 
                    department=lead.get("department", "Operations"), company=lead.get("company"), 
                    manager_id=None, level=lead.get("level", 2), email=lead.get("email"), 
                    linkedin=lead.get("url") or lead.get("linkedin", ""), url=lead.get("url") or lead.get("linkedin", ""),
                    education=lead.get("education"), location=lead.get("location"), connections=lead.get("connections"),
                    highlights=lead.get("highlights"), observations=lead.get("observations"),
                    temperature=lead.get("temperature")
                )
                
                # 🛠️ GESTÃO DE CONEXÕES AO VIVO (AGRESSIVA)
                assigned_manager = "root_company"
                
                if emp.level <= 0:
                    emp.level = get_seniority_level(emp.role)
                    if emp.level <= 0: emp.level = 1

                levels_map = {0: [], 1: [], 2: [], 3: [], 4: [], 5: [], 6: []}
                highest_senior_id = "root_company"
                max_level_found = -1

                for existing in hierarchy_pool: 
                    if existing.id == emp.id: continue
                    levels_map[existing.level].append(existing)
                
                # Passo A: Tenta achar um chefe (Nível IMEDIATAMENTE ACIMA do emp)
                found_boss = False
                # Começa do nível vizinho (emp.level + 1) e vai subindo até o topo (6)
                for senior_level in range(emp.level + 1, 7):
                    if found_boss: break
                    if not levels_map.get(senior_level): continue
                    
                    matching_bosses = [b for b in levels_map[senior_level] if b.department == emp.department or any(k in b.department for k in ["Diretoria Executiva", "Raiz", "Administração", "Quadro de Sócios (QSA)"])]
                    if matching_bosses:
                        assigned_manager = matching_bosses[0].id
                        found_boss = True
                        found_boss = True
                
                emp.manager_id = assigned_manager
                
                # Passo C: RE-LIGAMENTO DINÂMICO (Quem já está lá pode ganhar um novo chefe melhor)
                reparented_nodes = []
                if emp.level > 1:
                    for existing in hierarchy_pool:
                        if existing.id == emp.id: continue
                        
                        # Se o novo cara (emp) é do mesmo setor e é mais sênior que o subordinado (existing)
                        # E o subordinado atualmente está na raiz ou em um fallback genérico
                        is_same_dept = (existing.department == emp.department)
                        is_emp_superior = (emp.level > existing.level)
                        is_currently_orphan = (existing.manager_id == "root_company" or existing.manager_id == highest_senior_id)
                        
                        if is_same_dept and is_emp_superior and is_currently_orphan:
                            existing.manager_id = emp.id
                            reparented_nodes.append(existing.dict())
                
                hierarchy_pool.append(emp)
                new_nodes.append(emp.dict())
                if reparented_nodes: new_nodes.extend(reparented_nodes)
                
            if new_nodes:
                yield f"data: {json.dumps({'type': 'batch', 'nodes': new_nodes}, ensure_ascii=False)}\n\n"
        
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")

@router.get("/pipedrive/{pipedrive_id}")
async def get_stored_hierarchy_by_pipedrive(pipedrive_id: int, db: AsyncSession = Depends(get_db)):
    """Busca a hierarquia salva usando o ID do Pipedrive."""
    stmt = select(Organization).where(Organization.pipedrive_id == pipedrive_id)
    res = await db.execute(stmt)
    org = res.scalars().first()
    
    # 🔄 FALLBACK: Se não encontrou por Pipedrive ID, tenta pelo ID local
    if not org:
        stmt_local = select(Organization).where(Organization.id == pipedrive_id)
        res_local = await db.execute(stmt_local)
        org = res_local.scalars().first()
        
    if not org:
        return {"nodes": [], "company_name": "Não encontrada", "status": "new"}
    return await get_stored_hierarchy(org.id, db)

@router.get("/{org_id}")
async def get_stored_hierarchy(org_id: int, db: AsyncSession = Depends(get_db)):
    """Busca a hierarquia completa já salva no banco de dados com resolução de IDs."""
    stmt_org = select(Organization).where(Organization.id == org_id)
    res_org = await db.execute(stmt_org)
    org = res_org.scalars().first()
    if not org:
        raise HTTPException(status_code=404, detail="Organização não encontrada no banco local.")

    stmt_emp = select(Employee).where(Employee.company_id == org_id).order_by(Employee.seniority.desc())
    result_emp = await db.execute(stmt_emp)
    employees = result_emp.scalars().all()

    if not employees:
        return {"company_name": org.name, "nodes": [], "status": "empty"}
        
    nodes = []
    # 1. Nó Raiz
    nodes.append({
        "id": "root_company", "name": org.name, "role": "Entidade Principal", "department": "Supply Chain (Matriz)", 
        "manager_id": None, "level": 0, "company_logo": org.logo_url, "logo": org.logo_url, "domain": org.domain, "cnpj": org.cnpj,
        "linkedin": org.linkedin_url
    })

    # 2. Build mapping of ephemeral IDs/Keys to the new stable DB-based node IDs
    # Ephemeral IDs used during scan: node_{linkedin_user} or socio_{idx}
    id_mapping = {}
    for emp in employees:
        new_id = f"node_{emp.id}"
        
        # Mapping by LinkedIn URL (Stable username)
        if emp.linkedin_url and '/in/' in emp.linkedin_url:
            username = re.sub(r'[^a-zA-Z0-9]', '_', emp.linkedin_url.split('/in/')[-1].split('?')[0].rstrip('/'))
            id_mapping[f"node_{username}"] = new_id
            
        # Mapping by Name (as fallback for partners/socios)
        clean_name = re.sub(r'[^a-zA-Z0-9]', '_', emp.name.lower())
        id_mapping[f"socio_{clean_name}"] = new_id

    # 3. Create JSON nodes with corrected manager_ids and levels
    for emp in employees:
        new_id = f"node_{emp.id}"
        level = emp.seniority
        
        # Proteção: Funcionário não pode ser Nível 0 (senão vira root entity no UI)
        if level <= 0:
            level = get_seniority_level(emp.role)
            
        manager_id = emp.manager_id
        if not manager_id or manager_id == "None":
            manager_id = "root_company"
        elif manager_id in id_mapping:
            # Resolve ephemeral ID to stable DB ID
            manager_id = id_mapping[manager_id]
        elif "/" in str(manager_id) or "?" in str(manager_id):
            # Se for um link direto ou ID sujo, tenta limpar para casar com mapping
            clean_m_id = f"node_{re.sub(r'[^a-zA-Z0-9]', '_', str(manager_id).split('/in/')[-1].split('?')[0].rstrip('/'))}"
            manager_id = id_mapping.get(clean_m_id, "root_company")
        
        # Limpeza de e-mail (Bypass logic style)
        clean_email = emp.email
        if clean_email and clean_email.endswith("@") and org.domain:
            clean_email = f"{clean_email}{org.domain}"

        nodes.append({
            "id": new_id, 
            "name": emp.name, 
            "role": emp.role, 
            "level": level,
            "seniority": level, # Garante que o PersonaCard pegue o nível correto
            "department": get_department_tag(emp.role), 
            "manager_id": manager_id, 
            "linkedin": emp.linkedin_url, 
            "url": emp.linkedin_url, 
            "profile_pic": emp.profile_pic, 
            "email": clean_email, 
            "education": emp.description, 
            "observations": emp.description, # Duplica para compatibilidade
            "location": emp.location,
            "phone": emp.phone,
            "whatsapp_number": emp.whatsapp_number,
            "temperature": emp.temperature
        })
    
    return {"company_name": org.name, "nodes": nodes, "status": "cached"}
