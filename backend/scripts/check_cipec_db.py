import sys
import os
import asyncio
from pathlib import Path

# Adiciona o diretório backend ao sys.path
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from core.database import async_session
from models.prospect import ProspectLead
from sqlalchemy import select

async def check_db():
    async with async_session() as session:
        # Busca leads que contenham "Cipec" no nome
        q = select(ProspectLead).where(ProspectLead.name.like("%Cipec%"))
        res = await session.execute(q)
        leads = res.scalars().all()
        
        print(f"--- Verificando Leads de 'Cipec' no Banco Local ---")
        if not leads:
            print("Nenhum lead encontrado com esse nome.")
            return
            
        for lead in leads:
            print(f"\nLead: {lead.name}")
            print(f"  - Status Pipedrive: {lead.pipedrive_status}")
            print(f"  - Org ID Pipedrive: {lead.pipedrive_org_id}")
            print(f"  - Deal Info: {lead.pipedrive_deal_info}")

if __name__ == "__main__":
    asyncio.run(check_db())
