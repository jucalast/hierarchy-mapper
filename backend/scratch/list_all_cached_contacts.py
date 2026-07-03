import asyncio
import os
import sys

backend_path = r"c:\Users\João Luccas\Desktop\LINKB2B\hierarchy-mapper\backend"
sys.path.append(backend_path)
os.chdir(backend_path)

from core.infra.database import async_session
from models.communication.contact_cache import ContactConversationCache
from sqlalchemy import select

async def run():
    async with async_session() as session:
        res = await session.execute(select(ContactConversationCache))
        records = res.scalars().all()
        print(f"Total Cache Records: {len(records)}")
        print("-" * 60)
        for r in records:
            print(f"ID: {r.id}")
            print(f"  Identifier: {r.contact_identifier}")
            print(f"  Name: {r.contact_name}")
            print(f"  Channel: {r.channel}")
            print(f"  Org ID: {r.org_id}")
            print(f"  Org Name: {r.org_name}")
            print("-" * 60)

if __name__ == "__main__":
    asyncio.run(run())
