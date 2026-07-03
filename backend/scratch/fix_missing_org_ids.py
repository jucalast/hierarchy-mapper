import asyncio
import os
import sys

backend_path = r"c:\Users\João Luccas\Desktop\LINKB2B\hierarchy-mapper\backend"
sys.path.append(backend_path)
os.chdir(backend_path)

from core.infra.database import async_session
from models.communication.contact_cache import ContactConversationCache, CHANNEL_EMAIL, CHANNEL_WHATSAPP
from models.people.employee import Employee
from models.organization.organization import Organization
from sqlalchemy import or_, select

async def run():
    async with async_session() as session:
        # Select all cached message threads that are missing an organization ID or name
        res = await session.execute(
            select(ContactConversationCache).where(
                or_(
                    ContactConversationCache.org_id.is_(None),
                    ContactConversationCache.org_id == 0,
                    ContactConversationCache.org_name.is_(None)
                )
            )
        )
        records = res.scalars().all()
        print(f"Encontrados {len(records)} registros com org_id ou org_name ausentes.")
        
        updated_count = 0
        for r in records:
            print(f"Processando registro {r.id}: {r.contact_name} ({r.contact_identifier}) - Canal: {r.channel}")
            
            resolved_org_id = None
            resolved_org_name = None
            
            conditions = []
            if r.channel == CHANNEL_WHATSAPP:
                clean_id = "".join(c for c in r.contact_identifier if c.isdigit())
                conditions.append(Employee.whatsapp_number == r.contact_identifier)
                conditions.append(Employee.phone == r.contact_identifier)
                if clean_id and len(clean_id) >= 8:
                    suffix = clean_id[-8:]
                    conditions.append(Employee.whatsapp_number.like(f"%{suffix}%"))
                    conditions.append(Employee.phone.like(f"%{suffix}%"))
            else: # email
                conditions.append(Employee.email == r.contact_identifier)
                
            if r.contact_name:
                conditions.append(Employee.name == r.contact_name)
                conditions.append(Employee.name.like(f"%{r.contact_name}%"))
                
            if conditions:
                emp_result = await session.execute(
                    select(Employee)
                    .where(or_(*conditions))
                    .order_by(Employee.company_id.isnot(None).desc())
                )
                emp = emp_result.scalars().first()
                if emp and emp.company_id:
                    org_result = await session.execute(
                        select(Organization).where(Organization.id == emp.company_id)
                    )
                    org = org_result.scalar_one_or_none()
                    if org:
                        resolved_org_id = org.pipedrive_id or org.id
                        resolved_org_name = org.name
                        
            if resolved_org_id:
                print(f"  -> RESOLVIDO: {resolved_org_name} (ID Pipedrive/Local: {resolved_org_id})")
                r.org_id = resolved_org_id
                r.org_name = resolved_org_name
                updated_count += 1
            else:
                print(f"  -> Não foi possível resolver para o contato {r.contact_name}")
                
        if updated_count > 0:
            await session.commit()
            print(f"\nSucesso: {updated_count} registros atualizados e salvos no banco de dados!")
        else:
            print("\nNenhum registro pôde ser atualizado.")

if __name__ == "__main__":
    asyncio.run(run())
