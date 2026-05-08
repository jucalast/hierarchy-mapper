import logging
from typing import Dict, List, Optional, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import (
    Tenant, BusinessProfile, Product, ReferenceClient, 
    ICPConfig, ICPScoreRule, HierarchyConfig, User
)
from core.database import async_session

logger = logging.getLogger(__name__)

class BusinessContextService:
    """
    Serviço para carregar dinamicamente o contexto de negócio do banco de dados.
    Suporta multi-tenancy e fornece dados para os prompts da IA.
    """

    @staticmethod
    async def get_tenant_context(tenant_id: str = None) -> Dict[str, Any]:
        """
        Carrega todo o contexto de negócio para um Tenant.
        Se tenant_id for None, carrega o primeiro Tenant encontrado (Default).
        """
        async with async_session() as session:
            # 1. Buscar Tenant
            if tenant_id:
                stmt = select(Tenant).where(Tenant.id == tenant_id)
            else:
                stmt = select(Tenant).limit(1)
            
            res = await session.execute(stmt)
            tenant = res.scalars().first()
            if not tenant:
                logger.error("Nenhum Tenant encontrado no banco de dados.")
                return {}

            t_id = tenant.id

            # 2. Buscar Perfil, Produtos, Referências, ICP e Hierarchy em paralelo (via queries separadas por simplicidade)
            profile_res = await session.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == t_id))
            profile = profile_res.scalars().first()

            products_res = await session.execute(select(Product).where(Product.tenant_id == t_id))
            products = products_res.scalars().all()

            refs_res = await session.execute(select(ReferenceClient).where(ReferenceClient.tenant_id == t_id))
            refs = refs_res.scalars().all()

            icp_res = await session.execute(
                select(ICPConfig)
                .options(selectinload(ICPConfig.score_rules))
                .where(ICPConfig.tenant_id == t_id)
            )
            icp = icp_res.scalars().first()

            hier_res = await session.execute(select(HierarchyConfig).where(HierarchyConfig.tenant_id == t_id))
            hier = hier_res.scalars().first()

            user_res = await session.execute(select(User).where(User.tenant_id == t_id).limit(1))
            user = user_res.scalars().first()

            # 3. Formatar para o formato esperado pelos prompts legados
            context = {
                "company_name": tenant.name,
                "company_segment": profile.segment if profile else "",
                "company_differentials": profile.differentials if profile else [],
                "value_propositions": profile.value_propositions if (profile and profile.value_propositions) else {},
                "seller_name": user.name if user else "João Luccas",
                "seller_role": user.role if user else "Representante Comercial",
                "products": {
                    p.name.lower().replace(" ", "_"): {
                        "name": p.name,
                        "description": p.description,
                        "use_cases": p.use_cases
                    } for p in products
                },
                "reference_clients": [
                    {"name": r.name, "segment": r.segment, "pain_solved": r.pain_solved}
                    for r in refs
                ],
                "icp": {
                    "industries": icp.industries_target if icp else [],
                    "company_profiles": icp.company_size_target if icp else [],
                    "decision_makers": icp.decision_makers if icp else [],
                    "disqualifiers": icp.disqualifiers if icp else [],
                    "pain_points": icp.pain_points if (icp and icp.pain_points) else [],
                    "score_rules": [
                        {
                            "type": r.rule_type,
                            "pattern": r.value_pattern,
                            "score": r.weight_score,
                            "reason": r.reason
                        } for r in (icp.score_rules if icp else [])
                    ]
                },
                "hierarchy": {
                    "department_focus": hier.department_focus if hier else "compras",
                    "forbidden_keywords": hier.forbidden_keywords if hier else {},
                    "whitelist_keywords": hier.whitelist_keywords if hier else [],
                    "seniority_rules": hier.seniority_rules if hier else {},
                    "department_mapping": hier.department_mapping_rules if hier else {}
                }
            }

            return context

    @staticmethod
    async def get_integration_credentials(tenant_id: str, integration_type: str) -> Dict[str, Any]:
        """Busca credenciais de integração para um Tenant."""
        from models import Integration
        async with async_session() as session:
            stmt = select(Integration).where(
                (Integration.tenant_id == tenant_id) & (Integration.type == integration_type)
            )
            res = await session.execute(stmt)
            integration = res.scalars().first()
            return integration.credentials_encrypted if integration else {}

    @staticmethod
    async def get_first_tenant_id() -> Optional[str]:
        """Retorna o ID do primeiro Tenant cadastrado."""
        from models import Tenant
        async with async_session() as session:
            res = await session.execute(select(Tenant).limit(1))
            tenant = res.scalars().first()
            return tenant.id if tenant else None
