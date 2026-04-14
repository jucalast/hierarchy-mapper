from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import text
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

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

    print(f"[Database] Sistema de Dados Pronto ({engine.url.drivername})")
