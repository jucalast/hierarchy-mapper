# -*- coding: utf-8 -*-
import asyncio
from core.infra.database import async_session
from models import Employee
from sqlalchemy import select

async def run():
    async with async_session() as db:
        res = await db.execute(select(Employee).where(Employee.role == 'Análise Humana'))
        emps = res.scalars().all()
        print([{'id': e.id, 'name': e.name, 'role': e.role, 'company_id': e.company_id} for e in emps])

asyncio.run(run())
