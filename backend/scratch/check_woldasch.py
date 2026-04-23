
import asyncio
from sqlalchemy import select
from core.database import get_db
from models.organization import Organization

async def check():
    async for session in get_db():
        stmt = select(Organization).where(Organization.name.ilike('%WOLDASCH%'))
        res = await session.execute(stmt)
        orgs = res.scalars().all()
        for o in orgs:
            print(f"Found WOLDASCH: ID={o.id}, PipedriveID={o.pipedrive_id}")

if __name__ == "__main__":
    asyncio.run(check())
