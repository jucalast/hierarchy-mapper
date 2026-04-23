
import asyncio
from sqlalchemy import select
from core.database import get_db
from models.organization import Organization

async def check():
    async for session in get_db():
        stmt = select(Organization).where(Organization.id == 52)
        res = await session.execute(stmt)
        org = res.scalar_one_or_none()
        if org:
            print(f"ID 52 Name: {org.name}")
            print(f"ID 52 Pipedrive ID: {org.pipedrive_id}")
        else:
            print("ID 52 not found")

if __name__ == "__main__":
    asyncio.run(check())
