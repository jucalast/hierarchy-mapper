import sys
import asyncio
import json
sys.path.append('c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/backend')

from core.infra.database import async_session
from sqlalchemy import select
from models.organization import Organization
from modules.agent.service.tools.communication import exec_batch_communication_search

async def main():
    org_name_query = "%axt%"
    domain = None
    
    print("Buscando empresa no banco de dados...")
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Organization).where(Organization.name.ilike(org_name_query))
            )
            org = result.scalars().first()
            if org:
                print(f"Empresa encontrada no DB: {org.name}")
                print(f"Domínio cadastrado: {org.domain}")
                domain = org.domain
            else:
                print("Empresa não encontrada no DB.")
    except Exception as e:
        print(f"Erro ao buscar no DB: {e}")
            
    if not domain:
        # Se não achar no DB, testa só pelo org_name
        contacts = []
    else:
        contacts = [{"name": "AXT", "email": f"@{domain}"}]
        
    args = {
        "org_name": "axt terminais eletricos",
        "contacts": contacts,
        "limit_wa": 10,
        "limit_email": 10
    }
    
    print("\nExecutando batch_communication_search...")
    res = await exec_batch_communication_search(args)
    
    print("\nResultado:")
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
