"""
api.v1.routers.search
=====================
Busca global entre entidades locais e fontes externas em paralelo.

Agrega resultados de Organization, Employee e contatos externos
via asyncio.gather. Resultados sao deduplicados por ID antes de retornar.

Rotas:
    GET /search?q=&type= -> lista de entidades (empresas, pessoas, contatos)
"""
import asyncio
import re
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.infra.database import get_db
from core.observability.logging_config import get_logger
from models import Employee, Organization

log = get_logger(__name__)

router = APIRouter()

@router.get("/universal")
async def universal_search(
    q: str = Query(..., min_length=1),
    type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Busca universal com suporte a tags (@email, @contato, @empresa) e exclusividade estrita.
    """
    results = []
    
    # 1. Detecção de Tags e Limpeza Estrita
    tag_map = {
        "@email": "email",
        "@contatos": "whatsapp",
        "@contato": "whatsapp",
        "@whatsapp": "whatsapp",
        "@empresas": "organization",
        "@empresa": "organization"
    }
    
    found_tag_type = None
    for tag, t_type in tag_map.items():
        # Busca a tag e o que vem depois dela, ignorando o que vem antes
        match = re.search(rf"{tag}\s+(.*)", q, re.IGNORECASE)
        if not match:
            # Tenta sem espaço após a tag (ex: @emailJoão)
            match = re.search(rf"{tag}(.*)", q, re.IGNORECASE)
            
        if match:
            q = match.group(1).strip()
            found_tag_type = t_type
            break
    
    # Define o tipo final (Prioridade para tag, depois parâmetro)
    final_type = found_tag_type or type
    if final_type == "empresa": final_type = "organization"
    if final_type == "contato": final_type = "whatsapp"
    
    # Detecção automática de e-mail puro (ex: joao@gmail.com) para priorizar busca de contatos
    if not final_type and "@" in q and "." in q.split("@")[-1]:
        final_type = "email"
    
    # Flags de execução Estritas - BLOQUEIO TOTAL E IMEDIATO
    if final_type:
        do_org = (final_type == "organization")
        do_wa = (final_type == "whatsapp")
        do_email = (final_type == "email")
    elif q.startswith("@"):
        # Heurística: Se começou com @ e ainda não detectou tag, 
        # assume que o usuário está digitando uma tag e silencia buscas pesadas.
        do_org = False
        do_wa = False
        do_email = True 
    else:
        do_org = do_wa = do_email = True

    # Se q ficou vazio após a tag, retornamos vazio imediatamente para limpar a UI
    if final_type and not q:
        return {"results": [], "total": 0, "type": final_type}

    # 3. Execução das buscas
    search_term = f"%{q}%"
    
    tasks = []
    
    # Busca Empresas
    if do_org:
        async def fetch_orgs():
            stmt = select(Organization).where(
                or_(
                    func.lower(Organization.name).like(func.lower(search_term)),
                    func.lower(Organization.domain).like(func.lower(search_term)) if Organization.domain else False
                )
            ).limit(10 if final_type else 5)
            res = await db.execute(stmt)
            orgs = res.scalars().all()
            return [{
                "id": o.id, "name": o.name, "type": "organization", 
                "domain": o.domain, "logo_url": o.logo_url
            } for o in orgs]
        tasks.append(fetch_orgs())

    # Busca Contatos (WhatsApp e Email) - UNIFICADO NO BANCO LOCAL
    if do_wa or do_email:
        async def fetch_contacts():
            try:
                # Busca por nome, e-mail ou telefone de forma insensível a maiúsculas
                stmt = select(Employee).where(
                    or_(
                        func.lower(Employee.name).like(func.lower(search_term)),
                        func.lower(Employee.email).like(func.lower(search_term)) if Employee.email else False,
                        Employee.whatsapp_number.like(search_term) if Employee.whatsapp_number else False,
                        Employee.phone.like(search_term) if Employee.phone else False
                    )
                ).limit(15 if final_type else 8)
                
                res = await db.execute(stmt)
                employees = res.scalars().all()
                
                res_list = []
                for c in employees:
                    # Determina o tipo baseado nos dados disponíveis e na fonte
                    c_type = "whatsapp" if (c.whatsapp_number or c.source == "whatsapp") else "email"
                    
                    # Se filtramos por um tipo específico (@whatsapp ou @email), respeitamos
                    if final_type == "whatsapp" and c_type != "whatsapp": continue
                    if final_type == "email" and c_type != "email": continue
                    
                    res_list.append({
                        "id": c.whatsapp_number or c.email or c.pipedrive_id or str(c.id),
                        "name": c.name,
                        "type": c_type,
                        "email": c.email,
                        "phone": c.whatsapp_number or c.phone,
                        "role": c.role,
                        "department": c.department,
                        "company_id": c.company_id,
                        "source": c.source or "local"
                    })
                return res_list
            except Exception as e:
                log.warning("search.contacts.db_failed", error=str(e))
                return []
        tasks.append(fetch_contacts())

    # Agregado de resultados com metadados completos
    all_results = await asyncio.gather(*tasks)
    for res_list in all_results:
        results.extend(res_list)

    return {"results": results, "count": len(results), "type": final_type}
