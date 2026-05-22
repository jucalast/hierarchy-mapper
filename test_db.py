from core.infra.database import async_session
from sqlalchemy import select
from models.people.employee import Employee
import asyncio
async def main():
    async with async_session() as db:
        res = await db.execute(select(Employee.email, Employee.phone, Employee.whatsapp_number, Employee.profile_pic).limit(2))
        rows = res.all()
        for r in rows:
            print("ROW:", r)
            a,b,c,d = r
            print("UNPACKED:", a,b,c,d)
asyncio.run(main())
