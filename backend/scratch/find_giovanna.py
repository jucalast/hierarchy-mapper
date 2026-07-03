import asyncio
import os
import sys

backend_path = r"c:\Users\João Luccas\Desktop\LINKB2B\hierarchy-mapper\backend"
sys.path.append(backend_path)
os.chdir(backend_path)

from core.infra.database import async_session
from models.people.employee import Employee
from models.organization.organization import Organization
from sqlalchemy import select

async def run():
    async with async_session() as session:
        # Search by name
        res = await session.execute(select(Employee).where(Employee.name.like("%Giovanna%")))
        emps = res.scalars().all()
        print(f"Found {len(emps)} employees matching 'Giovanna':")
        for e in emps:
            print(f"Employee ID: {e.id}")
            print(f"  Name: {e.name}")
            print(f"  Phone: {e.phone}")
            print(f"  WA Number: {e.whatsapp_number}")
            print(f"  Email: {e.email}")
            print(f"  Company ID: {e.company_id}")
            
            # Get organization info
            if e.company_id:
                org_res = await session.execute(select(Organization).where(Organization.id == e.company_id))
                org = org_res.scalar_one_or_none()
                if org:
                    print(f"  Organization: {org.name} (Local ID: {org.id}, Pipedrive ID: {org.pipedrive_id})")
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(run())
