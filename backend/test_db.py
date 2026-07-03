import asyncio
import sys
import os

sys.path.insert(0, r"c:\Users\JoãoLuccasFerreiraMo\Desktop\linkb2b\hierarchy-mapper\backend")

from core.infra.database import async_session
from models import Organization
from sqlalchemy import select

async def main():
    async with async_session() as sess:
        res = await sess.execute(select(Organization.pipedrive_id, Organization.is_excluded, Organization.name))
        print("Orgs in local DB:", res.all())

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
