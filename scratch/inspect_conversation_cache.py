import sys
import os
import asyncio

# Add backend folder to python path
sys.path.append(os.path.abspath("backend"))

# Set environment variable to make sure local settings/configs work
os.environ["ENVIRONMENT"] = "development"

async def test():
    from core.infra.database import async_session
    from models.communication.contact_cache import ContactConversationCache
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(select(ContactConversationCache))
        entries = result.scalars().all()
        print(f"Total cache entries: {len(entries)}")
        for e in entries:
            print(f"- ID: {e.id} | Contact: {e.contact_name} | Ident: {e.contact_identifier} | Channel: {e.channel} | Org: {e.org_name} (ID: {e.org_id}) | Msg Count: {e.message_count}")
            
if __name__ == "__main__":
    asyncio.run(test())
