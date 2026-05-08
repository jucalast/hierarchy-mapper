from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
from pathlib import Path

from core.config import settings

DATABASE_URL = settings.DATABASE_URL

# Resolver caminho SQLite para encontrar o arquivo correto
if DATABASE_URL and "sqlite" in DATABASE_URL.lower():
    # Extrair o caminho do arquivo do DATABASE_URL
    # Exemplos: sqlite:///./intelligence.db ou sqlite+aiosqlite:///./intelligence.db
    db_path = DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    
    # Tentar encontrar o arquivo em localizações comuns
    possible_paths = [
        Path(db_path),  # Caminho relativo como está
        Path(__file__).parent.parent / db_path.lstrip("./"),  # Relativo a backend/
        Path(__file__).parent.parent.parent / db_path.lstrip("./"),  # Relativo a raiz
    ]
    
    resolved_path = None
    for path in possible_paths:
        if path.exists():
            resolved_path = path.resolve()
            print(f"[Database] Usando banco: {resolved_path}")
            break
    
    if resolved_path:
        # Reconstruct DATABASE_URL com caminho absoluto
        if "aiosqlite" in DATABASE_URL:
            DATABASE_URL = f"sqlite+aiosqlite:///{resolved_path}"
        else:
            DATABASE_URL = f"sqlite:///{resolved_path}"
    else:
        # Se não encontrar, usar o caminho padrão
        default_backend_db = Path(__file__).parent.parent / "intelligence.db"
        print(f"[Database] Banco não encontrado em {possible_paths}. Usando: {default_backend_db}")
        if "aiosqlite" in DATABASE_URL:
            DATABASE_URL = f"sqlite+aiosqlite:///{default_backend_db}"
        else:
            DATABASE_URL = f"sqlite:///{default_backend_db}"

Base = declarative_base()

# Motor Assíncrono
engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL.lower() else {}
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    """Gerador de sessões assíncronas para as rotas do FastAPI."""
    async with async_session() as session:
        yield session

async def seed_system_settings(session):
    from models.system_setting import SystemSetting
    from sqlalchemy import select

    # Check if we have any settings
    res = await session.execute(select(SystemSetting))
    if res.scalars().first() is not None:
        print("[Database] Configurações de sistema já existem. Ignorando seed.")
        return

    print("[Database] Semeando configurações padrão no banco de dados...")

    # Load defaults safely from source files
    try:
        from services.ai import business_context as bc
        company_profile = {
            "company_name": getattr(bc, "COMPANY_NAME", "J.Ferres"),
            "company_segment": getattr(bc, "COMPANY_SEGMENT", "Embalagens de Papelão Ondulado Sob Medida"),
            "company_differentials": getattr(bc, "COMPANY_DIFFERENTIALS", []),
            "seller_name": getattr(bc, "SELLER_NAME", "João Luccas"),
            "seller_role": getattr(bc, "SELLER_ROLE", "Representante Comercial"),
            "prospecting_methodology": getattr(bc, "PROSPECTING_METHODOLOGY", ""),
        }
        products = [
            {"id": k, "name": v["name"], "description": v["description"], "use_cases": v["use_cases"]}
            for k, v in getattr(bc, "PRODUCTS", {}).items()
        ]
        reference_clients = getattr(bc, "REFERENCE_CLIENTS", [])
        value_propositions = getattr(bc, "VALUE_PROPOSITIONS", {})
        icp_config = {
            "target_industries": getattr(bc, "ICP", {}).get("industries", []),
            "company_profiles": getattr(bc, "ICP", {}).get("company_profiles", []),
            "decision_makers": getattr(bc, "ICP", {}).get("decision_makers", []),
            "pain_points": getattr(bc, "ICP", {}).get("pain_points", []),
            "disqualifiers": getattr(bc, "ICP", {}).get("disqualifiers", []),
            "icp_segments": [
                "autopeças",
                "montadora automotiva",
                "máquinas industriais",
                "ferramentas industriais",
                "motores industriais",
                "exportação industrial",
                "metalúrgica",
            ]
        }
    except Exception as e:
        print(f"[Database Seed] Erro ao carregar business_context: {e}")
        company_profile = {
            "company_name": "J.Ferres",
            "company_segment": "Embalagens de Papelão Ondulado Sob Medida",
            "company_differentials": [],
            "seller_name": "João Luccas",
            "seller_role": "Representante Comercial",
            "prospecting_methodology": "",
        }
        products = []
        reference_clients = []
        value_propositions = {}
        icp_config = {
            "target_industries": [],
            "company_profiles": [],
            "decision_makers": [],
            "pain_points": [],
            "disqualifiers": [],
            "icp_segments": [
                "autopeças",
                "montadora automotiva",
                "máquinas industriais",
                "ferramentas industriais",
                "motores industriais",
                "exportação industrial",
                "metalúrgica",
            ]
        }

    try:
        from services.hierarchy import filters
        from services.hierarchy.role_engine import RoleEngine
        engine = RoleEngine()
        hierarchy_config = {
            "forbidden_keywords": getattr(engine, "FORBIDDEN_KEYWORDS", {}),
            "negative_keywords": getattr(filters, "negative_keywords", []),
            "purchasing_keywords": getattr(filters, "PURCHASING_KEYWORDS", []),
            "logistics_keywords": getattr(filters, "LOGISTICS_KEYWORDS", []),
        }
    except Exception as e:
        print(f"[Database Seed] Erro ao carregar filtros/hierarchy: {e}")
        hierarchy_config = {
            "forbidden_keywords": {
                "compras": ["sales", "vendas", "comercial", "production", "produção", "operation", "operador", "rh", "hr", "marketing", "atendimento", "customer"],
                "logistica": ["rh", "hr", "marketing", "vendas", "sales", "financeiro", "accounting"]
            },
            "negative_keywords": [],
            "purchasing_keywords": [],
            "logistics_keywords": [],
        }

    # Load from ai_preference.json if exists
    try:
        from services.ai.llm.router import get_preferred_model, get_strict_mode_preference
        ai_pref = {
            "model": get_preferred_model() or "gemini-2.5-flash",
            "strict_mode": get_strict_mode_preference(),
        }
    except Exception:
        ai_pref = {
            "model": "gemini-2.5-flash",
            "strict_mode": False
        }

    # Add settings to database
    settings_to_seed = [
        SystemSetting(key="ai_preference", category="ai_preference", value=ai_pref),
        SystemSetting(key="company_profile", category="business", value=company_profile),
        SystemSetting(key="products", category="business", value={"list": products}),
        SystemSetting(key="reference_clients", category="business", value={"list": reference_clients}),
        SystemSetting(key="value_propositions", category="business", value=value_propositions),
        SystemSetting(key="icp_config", category="icp", value=icp_config),
        SystemSetting(key="hierarchy_config", category="hierarchy", value=hierarchy_config),
    ]

    for setting in settings_to_seed:
        session.add(setting)

    await session.commit()
    print("[Database Seed] Configurações de sistema semeadas com sucesso!")

async def seed_tenant_data(session: AsyncSession):
    """Semeia os dados do Tenant padrão se não existirem."""
    from models import Tenant, User, BusinessProfile, Product, ReferenceClient, ICPConfig, ICPScoreRule, HierarchyConfig
    from sqlalchemy import select

    # 1. Verificar se já existe um Tenant
    res = await session.execute(select(Tenant).limit(1))
    tenant = res.scalars().first()
    if tenant is not None:
        # Se o tenant já existe, garante que as integrações dele foram criadas/migradas
        from models.integration import Integration
        from core.config import settings
        from core.security import hash_password

        # Garante que os usuários pré-existentes possuam senha para login de fallback (admin123)
        user_res = await session.execute(select(User).where(User.tenant_id == tenant.id))
        for u in user_res.scalars().all():
            if not u.hashed_password:
                u.hashed_password = hash_password("admin123")
                session.add(u)
                print(f"[Database Seed] Migração SaaS: Criada senha padrão para usuário '{u.email}'.")

        for int_type, int_creds in [
            ("pipedrive", {"api_token": settings.PIPEDRIVE_API_TOKEN, "user_id": settings.PIPEDRIVE_USER_ID}),
            ("whatsapp", {
                "service_url": settings.WHATSAPP_SERVICE_URL,
                "app_id": settings.WHATSAPP_APP_ID,
                "app_secret": settings.WHATSAPP_APP_SECRET,
                "access_token": settings.WHATSAPP_ACCESS_TOKEN,
                "phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID,
                "verify_token": settings.WHATSAPP_VERIFY_TOKEN
            }),
            ("outlook", {
                "email_user": settings.EMAIL_USER,
                "email_password": settings.EMAIL_PASSWORD,
                "email_port": settings.EMAIL_PORT
            })
        ]:
            check_stmt = select(Integration).where((Integration.tenant_id == tenant.id) & (Integration.type == int_type))
            check_res = await session.execute(check_stmt)
            if not check_res.scalars().first():
                new_int = Integration(
                    tenant_id=tenant.id,
                    type=int_type,
                    credentials_encrypted=int_creds,
                    custom_settings={}
                )
                session.add(new_int)
                print(f"[Database Seed] Migração SaaS: Criada integração {int_type} para Tenant '{tenant.name}'.")
        await session.commit()
        return

    print("[Database] Semeando dados de Tenant (SaaS)...")

    # 2. Carregar dados atuais (Priorizar SystemSetting, depois arquivos hardcoded)
    from models.system_setting import SystemSetting
    
    async def get_val(key, default):
        r = await session.execute(select(SystemSetting).where(SystemSetting.key == key))
        s = r.scalars().first()
        return s.value if s else default

    profile_data = await get_val("company_profile", {})
    products_data = await get_val("products", {"list": []})
    refs_data = await get_val("reference_clients", {"list": []})
    icp_data = await get_val("icp_config", {})
    hier_data = await get_val("hierarchy_config", {})
    value_props_data = await get_val("value_propositions", {})

    # Se SystemSetting estiver vazio, tenta carregar dos arquivos .py (fallback do fallback)
    if not profile_data:
        try:
            from services.ai import business_context as bc
            profile_data = {
                "company_name": bc.COMPANY_NAME,
                "company_segment": bc.COMPANY_SEGMENT,
                "company_differentials": bc.COMPANY_DIFFERENTIALS,
                "seller_name": bc.SELLER_NAME,
                "seller_role": bc.SELLER_ROLE,
            }
        except: pass

    # 3. Criar Tenant e User
    tenant = Tenant(name=profile_data.get("company_name", "J.Ferres"), domain="jferres.com.br")
    session.add(tenant)
    await session.flush() # Gerar ID do tenant

    user = User(
        tenant_id=tenant.id,
        name=profile_data.get("seller_name", "João Luccas"),
        email="joao@jferres.com.br",
        role=profile_data.get("seller_role", "Representante Comercial"),
        user_role="admin",
        hashed_password=hash_password("admin123")
    )
    session.add(user)

    # 4. Perfil de Negócio
    business_profile = BusinessProfile(
        tenant_id=tenant.id,
        segment=profile_data.get("company_segment"),
        differentials=profile_data.get("company_differentials"),
        methodology=profile_data.get("prospecting_methodology", ""),
        value_propositions=value_props_data
    )
    session.add(business_profile)

    # 5. Produtos
    for p in products_data.get("list", []):
        product = Product(
            tenant_id=tenant.id,
            name=p.get("name"),
            description=p.get("description"),
            use_cases=p.get("use_cases")
        )
        session.add(product)

    # 6. Clientes de Referência
    for r in refs_data.get("list", []):
        ref = ReferenceClient(
            tenant_id=tenant.id,
            name=r.get("name"),
            segment=r.get("segment"),
            pain_solved=r.get("pain_solved", "")
        )
        session.add(ref)

    # 7. ICP Config
    icp_config = ICPConfig(
        tenant_id=tenant.id,
        industries_target=icp_data.get("target_industries"),
        company_size_target=icp_data.get("company_profiles"),
        decision_makers=icp_data.get("decision_makers"),
        disqualifiers=icp_data.get("disqualifiers"),
        pain_points=icp_data.get("pain_points", [])
    )
    session.add(icp_config)
    await session.flush()

    # Score Rules (Defaults do J.Ferres)
    rules = [
        ("segment", "autopeça", 40, "Setor automotivo estratégico"),
        ("segment", "metalúrgica", 25, "Setor metalúrgico"),
        ("export", "exportação", 25, "Foco em exportação (CKD)"),
        ("size", "100+", 20, "Porte industrial médio/grande"),
    ]
    for rtype, pattern, score, reason in rules:
        rule = ICPScoreRule(icp_config_id=icp_config.id, rule_type=rtype, value_pattern=pattern, weight_score=score, reason=reason)
        session.add(rule)

    # 8. Hierarchy Config
    hierarchy = HierarchyConfig(
        tenant_id=tenant.id,
        department_focus="compras",
        forbidden_keywords=hier_data.get("forbidden_keywords"),
        whitelist_keywords={
            "compras": ["compras", "suprimentos", "procurement", "buyer", "strategic sourcing"],
            "logistica": ["logística", "supply chain", "almoxarifado", "expedição", "transportes", "pcp"]
        },
        seniority_rules={
            "diretor": 5, "gerente": 4, "coordenador": 3, "analista": 2, "comprador": 2, "especialista": 3
        },
        department_mapping_rules={
            "compras": "Suprimentos", "logistica": "Logística", "supply": "Supply Chain"
        }
    )
    session.add(hierarchy)

    # 9. Integrações Padrão (SaaS Migration)
    from models.integration import Integration
    from core.config import settings

    pipedrive_int = Integration(
        tenant_id=tenant.id,
        type="pipedrive",
        credentials_encrypted={
            "api_token": settings.PIPEDRIVE_API_TOKEN,
            "user_id": settings.PIPEDRIVE_USER_ID
        },
        custom_settings={}
    )
    session.add(pipedrive_int)

    whatsapp_int = Integration(
        tenant_id=tenant.id,
        type="whatsapp",
        credentials_encrypted={
            "service_url": settings.WHATSAPP_SERVICE_URL,
            "app_id": settings.WHATSAPP_APP_ID,
            "app_secret": settings.WHATSAPP_APP_SECRET,
            "access_token": settings.WHATSAPP_ACCESS_TOKEN,
            "phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID,
            "verify_token": settings.WHATSAPP_VERIFY_TOKEN
        },
        custom_settings={}
    )
    session.add(whatsapp_int)

    outlook_int = Integration(
        tenant_id=tenant.id,
        type="outlook",
        credentials_encrypted={
            "email_user": settings.EMAIL_USER,
            "email_password": settings.EMAIL_PASSWORD,
            "email_port": settings.EMAIL_PORT
        },
        custom_settings={}
    )
    session.add(outlook_int)

    await session.commit()
    print(f"[Database Seed] Tenant '{tenant.name}' e Integrações criados com sucesso!")

async def init_db():
    """Cria as tabelas se não existirem e garante migrações de colunas."""
    # Import models here to ensure they are registered with Base.metadata
    from models import (
        Organization, Employee, ConversationThread, ConversationMessage, 
        ActivityLog, ProspectSession, ProspectLead, SystemSetting,
        Tenant, User, BusinessProfile, Product, ReferenceClient,
        ICPConfig, ICPScoreRule, HierarchyConfig, Integration
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Migrações Manuais Resilientes
    async with engine.connect() as conn:
        for query in [
            "ALTER TABLE employees ADD COLUMN email VARCHAR",
            "ALTER TABLE organizations ADD COLUMN description TEXT",
            "ALTER TABLE employees ADD COLUMN description TEXT",
            "ALTER TABLE employees ADD COLUMN location VARCHAR",
            "ALTER TABLE employees ADD COLUMN manager_id VARCHAR",
            "ALTER TABLE organizations ADD COLUMN category VARCHAR",
            "ALTER TABLE organizations ADD COLUMN product_focus VARCHAR",
            "ALTER TABLE employees ADD COLUMN department VARCHAR",
            "ALTER TABLE organizations ADD COLUMN linkedin_url VARCHAR",
            "ALTER TABLE organizations ADD COLUMN logo_url VARCHAR",
            "ALTER TABLE organizations ADD COLUMN is_excluded INTEGER DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN temperature VARCHAR",
            "ALTER TABLE employees ADD COLUMN phone VARCHAR",
            "ALTER TABLE employees ADD COLUMN whatsapp_number VARCHAR",
            "ALTER TABLE organizations ADD COLUMN source VARCHAR DEFAULT 'pipedrive'",
            "ALTER TABLE employees ADD COLUMN source VARCHAR DEFAULT 'pipedrive'",
            "ALTER TABLE employees ADD COLUMN is_discovery INTEGER DEFAULT 0",
            "ALTER TABLE prospect_leads ADD COLUMN pipedrive_deal_id INTEGER",
            "ALTER TABLE business_profiles ADD COLUMN value_propositions JSON",
            "ALTER TABLE icp_configs ADD COLUMN pain_points JSON",
            "ALTER TABLE users ADD COLUMN hashed_password VARCHAR"
        ]:
            try:
                await conn.execute(text(query))
                await conn.commit()
            except Exception:
                pass
            
        try:
            await conn.execute(text("DROP INDEX IF EXISTS ix_organizations_cnpj"))
            await conn.commit()
        except: pass

    # Seed System Settings and Tenant Data
    async with async_session() as session:
        try:
            await seed_system_settings(session)
            await seed_tenant_data(session)
        except Exception as seed_err:
            print(f"[Database Seed] Erro ao rodar seeds: {seed_err}")

    print(f"[Database] Sistema de Dados Pronto ({engine.url.drivername})")
