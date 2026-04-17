import asyncio
import sys
import os
import re

# Adiciona o diretório atual ao path para importar core e models
sys.path.append(os.getcwd())

from core.database import async_session
from models import Organization
from sqlalchemy import select

async def cleanup_cnpjs():
    async with async_session() as s:
        stmt = select(Organization).where(Organization.cnpj != None)
        res = await s.execute(stmt)
        orgs = res.scalars().all()
        print(f"--- Cleaning CNPJs of {len(orgs)} organizations ---")
        
        count = 0
        for o in orgs:
            clean = re.sub(r'\D', '', str(o.cnpj))
            if clean != o.cnpj:
                print(f"Cleaning ID {o.id}: {o.cnpj} -> {clean}")
                o.cnpj = clean
                count += 1
        
        if count > 0:
            await s.commit()
            print(f"\n✅ Total cleaned: {count}")
        else:
            print("\n✅ All CNPJs already clean.")

if __name__ == "__main__":
    asyncio.run(cleanup_cnpjs())
