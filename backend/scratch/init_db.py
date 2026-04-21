import asyncio
import sys
import os

# Adiciona o diretório backend ao path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.database import engine, Base
import models # Garante que todos os models sejam importados

async def init_db():
    print("[DB] Inicializando tabelas...")
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
    print("[DB] Tabelas criadas com sucesso.")

if __name__ == "__main__":
    asyncio.run(init_db())
