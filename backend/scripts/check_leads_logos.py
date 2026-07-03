import sys
import os
import asyncio
from pathlib import Path

# Adiciona o diretório backend ao sys.path
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from core.infra.database import async_session
from models.people.prospect import ProspectLead
from sqlalchemy import select

async def check_leads_data():
    names_to_check = ["Palmetal", "Topco International", "Aurum"]
    
    async with async_session() as session:
        print(f"{'Nome':<25} | {'Domain':<20} | {'Logo URL':<30}")
        print("-" * 80)
        
        for name in names_to_check:
            # Busca por nome aproximado
            stmt = select(ProspectLead).where(ProspectLead.name.like(f"%{name}%"))
            result = await session.execute(stmt)
            leads = result.scalars().all()
            
            for lead in leads:
                logo_status = "Preenchido" if lead.logo_url else "Vazio"
                domain_status = lead.domain if lead.domain else "Vazio"
                url_preview = (lead.logo_url[:50] + "...") if lead.logo_url else "N/A"
                print(f"{lead.name[:25]:<25} | {domain_status:<20} | {url_preview}")

if __name__ == "__main__":
    asyncio.run(check_leads_data())
