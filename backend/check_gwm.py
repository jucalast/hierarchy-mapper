import asyncio
import sys
import os

# Adiciona o diretório atual ao path para importar core e models
sys.path.append(os.getcwd())

from core.database import async_session
from models import Organization
from sqlalchemy import select

async def check_db():
    async with async_session() as s:
        stmt = select(Organization).where(Organization.cnpj != None)
        res = await s.execute(stmt)
        orgs = res.scalars().all()
        print("--- All Orgs with CNPJ ---")
        for o in orgs:
            print(f"ID: {o.id} | Name: {o.name} | Pipedrive ID: {o.pipedrive_id} | CNPJ: {o.cnpj}")

if __name__ == "__main__":
    asyncio.run(check_db())
