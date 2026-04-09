from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

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

async def init_db():
    """Cria as tabelas se não existirem e garante migrações de colunas."""
    # Import models here to ensure they are registered with Base.metadata
    from models import Organization, Employee
    
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
            "ALTER TABLE organizations ADD COLUMN logo_url VARCHAR"
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

    print(f"[Database] ✅ Sistema de Dados Pronto ({engine.url.drivername})")
