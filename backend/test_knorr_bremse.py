import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from modules.crm.service.pipedrive_service import PipedriveService

async def test():
    service = PipedriveService()
    details = await service.get_organization_details(451)
    org = details.get("org") or {}
    print("Org keys:", org.keys())
    print("Owner Name:", org.get("owner_name"))
    print("Owner Avatar:", org.get("owner_avatar"))
    print("Owner ID:", org.get("owner_id"))

asyncio.run(test())
