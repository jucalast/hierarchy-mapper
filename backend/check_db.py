
import asyncio
from core.database import async_session
from models import Organization, Employee
from sqlalchemy import select

async def check():
    async with async_session() as session:
        res = await session.execute(select(Organization).where(Organization.name.ilike('%SPCom%')))
        orgs = res.scalars().all()
        print(f"SPCom search: {len(orgs)} found")
        for o in orgs:
            print(f" - ID: {o.id}, Name: {o.name}, CNPJ: {o.cnpj}")
            res_e = await session.execute(select(Employee).where(Employee.company_id == o.id))
            emps = res_e.scalars().all()
            print(f"   Employees: {len(emps)}")

if __name__ == "__main__":
    asyncio.run(check())
