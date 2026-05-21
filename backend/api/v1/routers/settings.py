"""
api.v1.routers.settings
========================
CRUD de configuracoes do Tenant: perfil, produtos, ICP e hierarquia.

Dois grupos de endpoints:
    v1 -- leitura simples de SystemSetting (key->value)
    v2 -- contexto completo + atualizacao granular por entidade

Rotas principais:
    GET  /settings              -> todos os SystemSettings
    GET  /settings/v2/context   -> contexto completo do Tenant
    POST /settings/v2/profile   -> atualiza perfil + vendedor
    POST /settings/v2/products  -> substitui lista de produtos
    POST /settings/v2/icp       -> atualiza ICPConfig e scoring rules
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any

from core.infra.database import get_db
from models.system.system_setting import SystemSetting
from core.observability.logging_config import get_logger

router = APIRouter()
log = get_logger(__name__)

@router.get("")
async def get_all_settings(session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Retorna todas as configurações salvas no banco de dados."""
    try:
        res = await session.execute(select(SystemSetting))
        settings_list = res.scalars().all()
        return {s.key: s.value for s in settings_list}
    except Exception as e:
        log.exception("settings.get_all.failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Erro ao buscar configurações: {e}")

from api.v1.schemas import (
    BusinessProfileSchema, ProductSchema, ReferenceClientSchema, 
    ICPConfigSchema, HierarchyConfigSchema
)
from models import (
    Tenant, User, BusinessProfile, Product, ReferenceClient, 
    ICPConfig, ICPScoreRule, HierarchyConfig, Integration
)
from sqlalchemy.orm import selectinload

@router.get("/v2/context")
async def get_full_context(session: AsyncSession = Depends(get_db)):
    """Retorna o contexto completo do Tenant atual (v2)."""
    from modules.ai.service.context.business_context_service import BusinessContextService
    return await BusinessContextService.get_tenant_context()

@router.post("/v2/profile")
async def update_profile(payload: BusinessProfileSchema, session: AsyncSession = Depends(get_db)):
    res = await session.execute(select(Tenant).limit(1))
    tenant = res.scalars().first()
    
    # Update Profile
    profile_res = await session.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == tenant.id))
    profile = profile_res.scalars().first()
    if not profile:
        profile = BusinessProfile(tenant_id=tenant.id)
        session.add(profile)
    
    profile.segment = payload.segment
    profile.differentials = payload.differentials
    profile.methodology = payload.methodology
    if payload.value_propositions is not None:
        profile.value_propositions = payload.value_propositions
    
    # Update User (Seller)
    user_res = await session.execute(select(User).where(User.tenant_id == tenant.id).limit(1))
    user = user_res.scalars().first()
    if user:
        if payload.seller_name: user.name = payload.seller_name
        if payload.seller_role: user.role = payload.seller_role
        
    await session.commit()
    return {"status": "ok"}

@router.get("/v2/products")
async def get_products(session: AsyncSession = Depends(get_db)):
    res = await session.execute(select(Product))
    return res.scalars().all()

@router.post("/v2/products")
async def add_product(payload: ProductSchema, session: AsyncSession = Depends(get_db)):
    res = await session.execute(select(Tenant).limit(1))
    tenant = res.scalars().first()
    product = Product(
        tenant_id=tenant.id,
        name=payload.name,
        description=payload.description,
        use_cases=payload.use_cases
    )
    session.add(product)
    await session.commit()
    return product

@router.delete("/v2/products/{product_id}")
async def delete_product(product_id: str, session: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete
    await session.execute(delete(Product).where(Product.id == product_id))
    await session.commit()
    return {"status": "ok"}

@router.post("/v2/icp")
async def update_icp(payload: ICPConfigSchema, session: AsyncSession = Depends(get_db)):
    res = await session.execute(select(Tenant).limit(1))
    tenant = res.scalars().first()
    
    icp_res = await session.execute(select(ICPConfig).where(ICPConfig.tenant_id == tenant.id))
    icp = icp_res.scalars().first()
    if not icp:
        icp = ICPConfig(tenant_id=tenant.id)
        session.add(icp)
        await session.flush()
    
    icp.industries_target = payload.industries_target
    icp.company_size_target = payload.company_size_target
    icp.decision_makers = payload.decision_makers
    icp.disqualifiers = payload.disqualifiers
    if payload.pain_points is not None:
        icp.pain_points = payload.pain_points
    
    # Update Rules
    from sqlalchemy import delete
    if payload.score_rules is not None:
        await session.execute(delete(ICPScoreRule).where(ICPScoreRule.icp_config_id == icp.id))
        for r in payload.score_rules:
            rule = ICPScoreRule(
                icp_config_id=icp.id,
                rule_type=r.rule_type,
                value_pattern=r.value_pattern,
                weight_score=r.weight_score,
                reason=r.reason
            )
            session.add(rule)
            
    await session.commit()
    return {"status": "ok"}

@router.post("/v2/hierarchy")
async def update_hierarchy(payload: HierarchyConfigSchema, session: AsyncSession = Depends(get_db)):
    res = await session.execute(select(Tenant).limit(1))
    tenant = res.scalars().first()
    
    hier_res = await session.execute(select(HierarchyConfig).where(HierarchyConfig.tenant_id == tenant.id))
    hier = hier_res.scalars().first()
    if not hier:
        hier = HierarchyConfig(tenant_id=tenant.id)
        session.add(hier)
    
    hier.department_focus = payload.department_focus
    hier.forbidden_keywords = payload.forbidden_keywords
    hier.whitelist_keywords = payload.whitelist_keywords
    hier.seniority_rules = payload.seniority_rules
    hier.department_mapping_rules = payload.department_mapping_rules
    
    await session.commit()
    return {"status": "ok"}

@router.get("/v2/integrations")
async def get_integrations(session: AsyncSession = Depends(get_db)):
    res = await session.execute(select(Tenant).limit(1))
    tenant = res.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant não encontrado.")
        
    int_res = await session.execute(select(Integration).where(Integration.tenant_id == tenant.id))
    integrations = int_res.scalars().all()
    
    result = {}
    for integration in integrations:
        result[integration.type] = {
            "credentials": integration.credentials_encrypted or {},
            "custom_settings": integration.custom_settings or {}
        }
    return result

@router.post("/v2/integrations/{integration_type}")
async def update_integration(
    integration_type: str,
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_db)
):
    res = await session.execute(select(Tenant).limit(1))
    tenant = res.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant não encontrado.")
        
    int_res = await session.execute(
        select(Integration)
        .where((Integration.tenant_id == tenant.id) & (Integration.type == integration_type))
    )
    integration = int_res.scalars().first()
    if not integration:
        integration = Integration(tenant_id=tenant.id, type=integration_type)
        session.add(integration)
        
    integration.credentials_encrypted = payload.get("credentials", {})
    integration.custom_settings = payload.get("custom_settings", {})
    
    await session.commit()
    return {"status": "ok", "type": integration_type}

@router.get("/{key}")
async def get_setting_by_key(key: str, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Retorna o valor de uma configuração específica pelo seu identificador (key)."""
    res = await session.execute(select(SystemSetting).where(SystemSetting.key == key))
    setting = res.scalars().first()
    if not setting:
        raise HTTPException(status_code=404, detail=f"Configuração '{key}' não encontrada.")
    return {"key": setting.key, "category": setting.category, "value": setting.value}

@router.post("/{key}")
async def update_setting_by_key(
    key: str,
    payload: Dict[str, Any],
    session: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Cria ou atualiza uma configuração no banco de dados."""
    try:
        res = await session.execute(select(SystemSetting).where(SystemSetting.key == key))
        setting = res.scalars().first()
        
        # Decide qual é a categoria
        category = payload.pop("category", "custom")
        if not setting and category == "custom":
            # Tenta mapear chaves padrão para categorias correspondentes
            if key in ("ai_preference",):
                category = "ai_preference"
            elif key in ("company_profile", "products", "reference_clients", "value_propositions"):
                category = "business"
            elif key in ("icp_config",):
                category = "icp"
            elif key in ("hierarchy_config",):
                category = "hierarchy"
                
        # Se vier o payload envolvido em "value", desempacotamos
        value = payload.get("value") if "value" in payload and len(payload) == 1 else payload

        if not setting:
            setting = SystemSetting(key=key, category=category, value=value)
            session.add(setting)
            log.info("settings.created", key=key, category=category)
        else:
            setting.value = value
            log.info("settings.updated", key=key)

        # Se for a preferência de IA, manter compatibilidade com ai_preference.json
        if key == "ai_preference":
            try:
                from core.llm.router import _save_global_preference
                # Garante que os campos necessários existem
                model_name = value.get("model", "gemini-2.5-flash") if isinstance(value, dict) else "gemini-2.5-flash"
                strict_mode = value.get("strict_mode", False) if isinstance(value, dict) else False
                _save_global_preference(model_name, strict_mode)
            except Exception as json_err:
                log.warning("settings.sync_json.failed", error=str(json_err))

        await session.commit()
        return {"status": "ok", "key": key, "value": setting.value}
        
    except Exception as e:
        log.exception("settings.update.failed", key=key, error=str(e))
        raise HTTPException(status_code=500, detail=f"Erro ao salvar configuração: {e}")
