import asyncio
import sys
import os
from dotenv import load_dotenv

# Adiciona o diretório backend ao path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Carrega .env explicitamente
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

from core.database import async_session
from models import Organization
from sqlalchemy import select
import httpx
from core.config import settings

async def sync_company_to_local_db(pipedrive_id: int):
    print(f"[Sync] Buscando empresa {pipedrive_id} no Pipedrive...")
    
    url = f"https://api.pipedrive.com/v1/organizations/{pipedrive_id}?api_token={settings.PIPEDRIVE_API_TOKEN}"
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            name = data.get("name")
            domain = data.get("website")
            address = data.get("address")
            logo_url = (data.get("picture_id") or {}).get("pictures", {}).get("128") or data.get("logo_url")
            
            async with async_session() as session:
                # Verifica se já existe
                stmt = select(Organization).where(Organization.pipedrive_id == pipedrive_id)
                res = await session.execute(stmt)
                org = res.scalars().first()
                
                if not org:
                    org = Organization(
                        pipedrive_id=pipedrive_id,
                        name=name,
                        domain=domain,
                        address=address,
                        logo_url=logo_url
                    )
                    session.add(org)
                    print(f"[Sync] Empresa {name} adicionada ao banco local.")
                else:
                    org.name = name
                    org.domain = domain
                    org.address = address
                    org.logo_url = logo_url
                    print(f"[Sync] Empresa {name} atualizada no banco local.")
                
                await session.commit()
        else:
            print(f"❌ Erro ao buscar no Pipedrive: {resp.status_code}")

if __name__ == "__main__":
    # ID retornado no passo anterior foi 1040
    asyncio.run(sync_company_to_local_db(1040))
