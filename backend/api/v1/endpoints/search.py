from fastapi import APIRouter, Query, Depends
import httpx
import asyncio
import re
from typing import List, Dict, Any, Optional
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from models import Organization

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

    # Busca WhatsApp
    if do_wa:
        async def fetch_wa():
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"http://localhost:8001/api/whatsapp/contacts/search?name={q}")
                    if resp.status_code == 200:
                        data = resp.json()
                        wa_res = data.get("contacts", []) or data.get("results", [])
                        return [{"id": c.get("id"), "name": c.get("name"), "type": "whatsapp", "number": c.get("number")} for c in wa_res[:10 if final_type else 5]]
            except: return []
            return []
        tasks.append(fetch_wa())

    # Busca Email
    if do_email:
        async def fetch_mail():
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    params = {"q": q, "limit": 10 if final_type else 5}
                    resp = await client.get("http://localhost:8002/api/email/search", params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        return [{"id": c.get("email"), "name": c.get("name"), "type": "email", "email": c.get("email")} for c in data.get("results", [])]
            except: return []
            return []
        tasks.append(fetch_mail())

    # Agrega tudo
    all_results = await asyncio.gather(*tasks)
    for res_list in all_results:
        results.extend(res_list)

    return {"results": results, "total": len(results)}
