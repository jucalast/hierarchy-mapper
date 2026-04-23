
import asyncio
from sqlalchemy import select
from core.database import get_db
from models.organization import Organization

async def check():
    async for session in get_db():
        # Check by ID 887
        stmt = select(Organization).where(Organization.id == 887)
        res = await session.execute(stmt)
        org = res.scalar_one_or_none()
        print(f"Local ID 887: {org.name if org else 'None'} (Pipedrive ID: {org.pipedrive_id if org else 'N/A'})")
        
        # Check by Pipedrive ID 887
        stmt = select(Organization).where(Organization.pipedrive_id == 887)
        res = await session.execute(stmt)
        org = res.scalar_one_or_none()
        print(f"Pipedrive ID 887: {org.name if org else 'None'} (Local ID: {org.id if org else 'N/A'})")

        # Check for Walsywa
        stmt = select(Organization).where(Organization.name.ilike('%Walsywa%'))
        res = await session.execute(stmt)
        orgs = res.scalars().all()
        for o in orgs:
            print(f"Found Walsywa: ID={o.id}, PipedriveID={o.pipedrive_id}")

if __name__ == "__main__":
    asyncio.run(check())
