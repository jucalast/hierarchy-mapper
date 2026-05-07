import sys
import os
import asyncio
from pathlib import Path

# Adiciona o diretório backend ao sys.path para importações funcionarem
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from core.database import async_session
from models.organization import Organization
from services.intelligence.brand_discovery import fetch_linkedin_logo
from sqlalchemy import select

async def update_all_logos():
    print("Iniciando atualizacao de logos das organizacoes mapeadas...")
    
    async with async_session() as session:
        # Busca todas as organizações que têm linkedin_url
        stmt = select(Organization).where(Organization.linkedin_url.isnot(None))
        result = await session.execute(stmt)
        orgs = result.scalars().all()
        
        total = len(orgs)
        print(f"Encontradas {total} organizacoes com link do LinkedIn.")
        
        updated_count = 0
        failed_count = 0
        
        for idx, org in enumerate(orgs):
            print(f"[{idx+1}/{total}] Processando: {org.name} ({org.linkedin_url})")
            
            try:
                # Tenta buscar o logo usando o link do LinkedIn
                logo_url = fetch_linkedin_logo(org.linkedin_url)
                
                if logo_url:
                    org.logo_url = logo_url
                    updated_count += 1
                    print(f"  Logo encontrado: {logo_url[:50]}...")
                else:
                    failed_count += 1
                    print(f"  Logo nao encontrado via LinkedIn.")
                
                # Commit a cada 5 para não perder progresso
                if (idx + 1) % 5 == 0:
                    await session.commit()
            
            except Exception as e:
                print(f"  Erro ao processar {org.name}: {e}")
                failed_count += 1
            
            # Pequeno delay para evitar rate limit
            await asyncio.sleep(0.5)
            
        await session.commit()
        print(f"\nFinalizado!")
        print(f"Atualizadas: {updated_count}")
        print(f"Nao encontradas: {failed_count}")

if __name__ == "__main__":
    asyncio.run(update_all_logos())
