import sys
import os
import asyncio
from pathlib import Path

# Adiciona o diretório backend ao sys.path
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

from core.database import async_session
from models.prospect import ProspectLead, ProspectSession
from models.organization import Organization
from sqlalchemy import delete

async def clear_prospecting_data():
    print("Iniciando limpeza total dos dados de prospecção...")
    
    async with async_session() as session:
        try:
            # 1. Deletar todos os Leads
            print("- Removendo todos os ProspectLeads...")
            await session.execute(delete(ProspectLead))
            
            # 2. Deletar todas as Sessões
            print("- Removendo todas as ProspectSessions...")
            await session.execute(delete(ProspectSession))
            
            # 3. Deletar Organizations vindas de prospecção que ainda não são oficiais
            print("- Removendo Organizations temporárias (source='prospecting')...")
            await session.execute(
                delete(Organization).where(Organization.source == "prospecting")
            )
            
            await session.commit()
            print("\nLimpeza concluída com sucesso! O radar está limpo para novas buscas.")
            
        except Exception as e:
            print(f"Erro durante a limpeza: {e}")
            await session.rollback()

if __name__ == "__main__":
    asyncio.run(clear_prospecting_data())
