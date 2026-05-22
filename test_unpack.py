import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.core.infra.database import async_session
from backend.sqlalchemy import select
from backend.models.people.employee import Employee

async def main():
    async with async_session() as db:
        res = await db.execute(select(Employee.email, Employee.phone, Employee.whatsapp_number, Employee.profile_pic).limit(2))
        rows = res.all()
        for r in rows:
            print("ROW:", r)
            a,b,c,d = r
            print("UNPACKED:", a,b,c,d)

if __name__ == "__main__":
    asyncio.run(main())