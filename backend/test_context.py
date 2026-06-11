import asyncio
import os
import sys

sys.path.append(os.getcwd())

from core.infra.database import async_session
from models.organization import Organization
from sqlalchemy import select

async def run():
    async with async_session() as s:
        r = await s.execute(select(Organization.prospecting_context).where(Organization.pipedrive_id == 1068))
        print(r.scalar())

asyncio.run(run())
