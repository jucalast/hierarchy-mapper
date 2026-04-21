"""
Persistência de organizações e funcionários no banco local + Pipedrive.
Lida com upsert de empresas e sócios (QSA).
"""
import re
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import Organization, Employee


async def upsert_organization(
    db: AsyncSession,
    razao_social: str,
    cnpj_clean: str,
    domain: Optional[str],
    full_address: str,
    confirmed_brand: Optional[str] = None,
    area_focus: Optional[str] = None,
    product_focus: Optional[str] = None,
    confirmed_logo: Optional[str] = None
) -> Optional[int]:
    """
    Busca a organização no banco (cascata: CNPJ → Domain → Nome).
    Se não existir, cria nova + cria no Pipedrive.
    Retorna o org_id.
    """
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
        clean_name = confirmed_brand or razao_social
        stmt_name = select(Organization).where(func.lower(Organization.name) == clean_name.lower())
        res_name = await db.execute(stmt_name)
        org = res_name.scalars().first()

    if not org:
        # Criar no Pipedrive SE for nova
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
            pipedrive_id=p_id
        )
        db.add(org)
        await db.flush()
        print(f"[Stream] Nova empresa criada. Local ID: {org.id}, Pipedrive ID: {p_id}")
    else:
        # Atualização síncrona: une dados que já existiam
        if not org.cnpj:
            org.cnpj = cnpj_clean
        if not org.address or len(org.address) < 5:
            org.address = full_address
        if confirmed_brand:
            org.name = confirmed_brand
        if domain and not org.domain:
            org.domain = domain
        if area_focus:
            org.category = area_focus
        if product_focus:
            org.product_focus = product_focus
        
        # Se não tinha Pipedrive ID, tenta criar agora
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
    return org_id


async def persist_socios(
    db: AsyncSession,
    org_id: int,
    qsa: list
):
    """Persiste os sócios (QSA) no banco se ainda não existirem."""
    if not org_id or not qsa:
        return
    
    for idx, socio in enumerate(qsa):
        name_socio = socio.get("nome_socio", "Sócio Anônimo")
        role_socio = socio.get("qualificacao_socio", "Sócio")
        
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
        except:
            pass
    
    await db.commit()
