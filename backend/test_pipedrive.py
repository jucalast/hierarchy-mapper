import asyncio
import sys
import os
import logging

logging.basicConfig(level=logging.DEBUG)

sys.path.insert(0, r"c:\Users\JoãoLuccasFerreiraMo\Desktop\linkb2b\hierarchy-mapper\backend")

from core.infra.database import async_session
from modules.crm.service import pipedrive_service
from core.infra.http_client import init_http_client, close_http_client

async def main():
    await init_http_client()
    try:
        print("Forcing cache refresh...")
        pipedrive_service._open_org_ids_cache_ts = 0.0
        await pipedrive_service.refresh_open_org_ids_cache()
        print("Cache refreshed. IDs:", pipedrive_service._open_org_ids_cache)
        
        print("Listing organizations...")
        orgs = await pipedrive_service.list_organizations()
        print("Count:", len(orgs))
    finally:
        await close_http_client()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
