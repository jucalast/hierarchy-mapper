import asyncio
import sys
from pathlib import Path

# Adjust path to find backend packages
backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from core.infra.database import init_db

async def test_db():
    print("Iniciando verificação de banco de dados no Neon Postgres...")
    try:
        await init_db()
        print("Banco de dados pronto e inicializado com sucesso!")
    except Exception as e:
        print(f"Erro ao inicializar o banco de dados: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if sys.platform == "win32":
        from asyncio import WindowsProactorEventLoopPolicy
        asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
    asyncio.run(test_db())
