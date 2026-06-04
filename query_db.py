import asyncio
import sys
import os

# Ensure the backend directory is in the path
sys.path.insert(0, os.path.abspath('backend'))

from core.infra.database import async_session
from models import Organization
from sqlalchemy import select

async def main():
    async with async_session() as session:
        stmt = select(Organization).filter(Organization.name.ilike('%Goovi%'))
        result = await session.execute(stmt)
        orgs = result.scalars().all()
        if not orgs:
            print("No organization found with name Goovi.")
        for o in orgs:
            print(f"ID: {o.id}, Name: {o.name}, Pipedrive ID: {o.pipedrive_id}, Is Excluded: {o.is_excluded}")

if __name__ == '__main__':
    asyncio.run(main())
