
import asyncio
import os
import sys

# Adiciona o diretório backend ao path para importar core e models
sys.path.append(os.path.join(os.getcwd(), "backend"))

from core.infra.database import init_db, async_session, engine
from models import Tenant, BusinessProfile, Product, User
from sqlalchemy import select

async def verify_saas_refactor():
    print("--- Verificando Refatoração SaaS ---")
    
    # 1. Inicializar banco (cria tabelas e roda seeds)
    try:
        await init_db()
        print("[OK] Tabelas criadas e seeds executados.")
    except Exception as e:
        print(f"[ERRO] Falha ao inicializar banco: {e}")
        return

    # 2. Verificar se o Tenant padrão (J.Ferres) foi criado
    async with async_session() as session:
        res = await session.execute(select(Tenant).where(Tenant.name == "J.Ferres"))
        tenant = res.scalars().first()
        
        if tenant:
            print(f"[OK] Tenant '{tenant.name}' encontrado (ID: {tenant.id})")
            
            # Verificar Perfil
            p_res = await session.execute(select(BusinessProfile).where(BusinessProfile.tenant_id == tenant.id))
            profile = p_res.scalars().first()
            if profile:
                print(f"[OK] Perfil Comercial encontrado: {profile.segment}")
            else:
                print("[ERRO] Perfil Comercial não encontrado para o Tenant.")
                
            # Verificar Produtos
            prod_res = await session.execute(select(Product).where(Product.tenant_id == tenant.id))
            products = prod_res.scalars().all()
            print(f"[OK] {len(products)} produtos encontrados.")
            
            # Verificar Integracoes
            from models.crm.integration import Integration
            int_res = await session.execute(select(Integration).where(Integration.tenant_id == tenant.id))
            integrations = int_res.scalars().all()
            print(f"[OK] {len(integrations)} integrações encontradas:")
            for integration in integrations:
                print(f"     - {integration.type}: {list(integration.credentials_encrypted.keys()) if integration.credentials_encrypted else 'vazia'}")

            # Verificar Regras de Score/ICP
            from models.crm.icp import ICPConfig
            from sqlalchemy.orm import selectinload
            icp_res = await session.execute(
                select(ICPConfig)
                .options(selectinload(ICPConfig.score_rules))
                .where(ICPConfig.tenant_id == tenant.id)
            )
            icp = icp_res.scalars().first()
            if icp:
                print(f"[OK] ICPConfig encontrado (ID: {icp.id})")
                print(f"     - Dores Cadastradas: {icp.pain_points}")
                print(f"     - Regras de Pontuação: {len(icp.score_rules) if icp.score_rules else 0} regras")
            else:
                print("[ERRO] ICPConfig não encontrado.")

            # Verificar Regras de Hierarquia
            from models.hierarchy import HierarchyConfig
            hier_res = await session.execute(select(HierarchyConfig).where(HierarchyConfig.tenant_id == tenant.id))
            hier = hier_res.scalars().first()
            if hier:
                print(f"[OK] HierarchyConfig encontrado (ID: {hier.id})")
                print(f"     - Keywords Proibidas: {hier.forbidden_keywords}")
                print(f"     - Keywords Whitelist: {hier.whitelist_keywords}")
            else:
                print("[ERRO] HierarchyConfig não encontrado.")
            
            # Verificar User
            user_res = await session.execute(select(User).where(User.tenant_id == tenant.id))
            user = user_res.scalars().first()
            if user:
                print(f"[OK] Usuário '{user.name}' encontrado ({user.role})")
            else:
                print("[ERRO] Usuário não encontrado para o Tenant.")
        else:
            print("[ERRO] Tenant 'J.Ferres' não foi criado pelo seed.")

    print("--- Verificação Concluída ---")

if __name__ == "__main__":
    asyncio.run(verify_saas_refactor())
