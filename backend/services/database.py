from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

Base = declarative_base()

class Organization(Base):
    __tablename__ = "organizations"
    
    id = Column(Integer, primary_key=True, index=True) # Pipedrive ID ou Sequencial
    pipedrive_id = Column(Integer, unique=True, index=True)
    name = Column(String, index=True)
    cnpj = Column(String, index=True, nullable=True) # Removido unique=True para suportar filiais/duplicatas
    domain = Column(String, index=True, nullable=True)
    address = Column(Text, nullable=True)
    description = Column(Text, nullable=True) # 📝 Novo: Descrição ou Source
    owner_id = Column(Integer, index=True)
    last_enrichment = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    role = Column(String)
    seniority = Column(Integer, default=0) # Rank da hierarquia (1-Director, 2-Manager, etc)
    linkedin_url = Column(String, unique=True, index=True)
    profile_pic = Column(Text, nullable=True)
    email = Column(String, nullable=True) # 📧 Novo campo restaurado!
    description = Column(Text, nullable=True) # 📝 Snippet ou Bio
    location = Column(String, nullable=True) # 📍 Cidade/Estado
    company_id = Column(Integer, ForeignKey("organizations.id"))
    last_scanned = Column(DateTime(timezone=True), server_default=func.now())

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Motor Assíncrono para SQLite Local (Desenvolvimento Instantâneo)
engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    connect_args={"check_same_thread": False} # Requisito do SQLite para multiprocessamento
)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    """Gerador de sessões assíncronas para as rotas do FastAPI."""
    async with async_session() as session:
        yield session

async def init_db():
    """Cria as tabelas se não existirem e garante migrações de colunas."""
    async with engine.begin() as conn:
        # 1. Cria tabelas se não existirem
        await conn.run_sync(Base.metadata.create_all)
    
    # 2. Migração Manual Resiliente (Trata SQLite e Postgres)
    async with engine.connect() as conn:
        try:
            # 1. Adiciona coluna 'email' se não existir
            await conn.execute(text("ALTER TABLE employees ADD COLUMN email VARCHAR"))
            await conn.commit()
            print("[Database] 🛡️ Coluna 'email' adicionada com sucesso.")
        except Exception:
            pass # Coluna já existe
            
        try:
            # 2. Adiciona coluna 'description' se não existir
            await conn.execute(text("ALTER TABLE organizations ADD COLUMN description TEXT"))
            await conn.commit()
        except Exception: pass

        try:
            # 3. Adiciona colunas extras em employees se não existirem
            await conn.execute(text("ALTER TABLE employees ADD COLUMN description TEXT"))
            await conn.execute(text("ALTER TABLE employees ADD COLUMN location VARCHAR"))
            await conn.commit()
            print("[Database] 🛡️ Colunas extras (metadata) adicionadas a employees.")
        except Exception: pass

        try:
            # 3. Remove o índice UNIQUE do CNPJ se ele existir
            await conn.execute(text("DROP INDEX IF EXISTS ix_organizations_cnpj"))
            await conn.commit()
            print("[Database] 🛡️ Índice UNIQUE do CNPJ removido para suporte a filiais.")
        except Exception:
            pass

    print(f"[Database] ✅ Sistema de Dados Pronto ({engine.url.drivername})")
