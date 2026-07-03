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
        res = await session.execute(select(ContactConversationCache).where(ContactConversationCache.id.in_([11, 12])))
        records = res.scalars().all()
        for r in records:
            print(f"ID: {r.id}")
            print(f"  Contact Identifier: {r.contact_identifier}")
            print(f"  Contact Name: {r.contact_name}")
            print(f"  Org Name: {r.org_name}")
            print(f"  Org ID: {r.org_id}")
            print(f"  Chat ID: {r.chat_id}")
            print(f"  Fetched At: {r.fetched_at}")
            print(f"  Has Unread: {r.has_unread}")
            print(f"  Is Key Contact: {r.is_key_contact}")
            print(f"  Msg Count: {r.message_count}")
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(run())
