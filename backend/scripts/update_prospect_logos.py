import sys
import os
import asyncio
from pathlib import Path

# Adiciona o diretório backend ao sys.path
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from core.infra.database import async_session
from models.people.prospect import ProspectLead
from modules.intelligence.service.brand_discovery import fetch_linkedin_logo
from sqlalchemy import select

async def update_prospect_logos():
    print("Iniciando atualizacao de logos para LEADS de prospecção...")
    
    async with async_session() as session:
        # Busca leads pendentes que têm linkedin_url
        stmt = select(ProspectLead).where(ProspectLead.linkedin_url.isnot(None))
        result = await session.execute(stmt)
        leads = result.scalars().all()
        
        total = len(leads)
        print(f"Encontrados {total} leads com link do LinkedIn.")
        
        updated_count = 0
        
        for idx, lead in enumerate(leads):
            print(f"[{idx+1}/{total}] Processando lead: {lead.name}")
            
            try:
                # Tenta buscar o logo usando o link do LinkedIn
                logo_url = fetch_linkedin_logo(lead.linkedin_url)
                
                if logo_url:
                    lead.logo_url = logo_url
                    updated_count += 1
                    print(f"  Logo encontrado: {logo_url[:50]}...")
                
                if (idx + 1) % 5 == 0:
                    await session.commit()
            
            except Exception as e:
                print(f"  Erro ao processar {lead.name}: {e}")
            
            await asyncio.sleep(0.3)
            
        await session.commit()
        print(f"\nFinalizado! {updated_count} leads atualizados.")

if __name__ == "__main__":
    asyncio.run(update_prospect_logos())
