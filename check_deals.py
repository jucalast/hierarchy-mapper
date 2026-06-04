import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath('backend'))

from modules.crm.service.pipedrive_service import PipedriveService
import json

async def main():
    service = PipedriveService()
    service.user_id = 1
    
    from core.infra.http_client import init_http_client, close_http_client
    init_http_client()
    try:
        resp = await service._request("GET", "deals", params={"org_id": 1109})
        if resp:
            data = resp.json()
            deals = data.get("data") or []
            print(f"Deals for Goovi (org 1109):")
            for d in deals:
                print(f"Deal ID: {d.get('id')}, Status: {d.get('status')}, Title: {d.get('title')}")
            if not deals:
                print("No deals found for this organization.")
        else:
            print("Failed to fetch deals.")
            
        print("Now checking the open cache.")
        await service.refresh_open_org_ids_cache()
        cache = PipedriveService._open_org_ids_cache
        print(f"Is 1109 in open cache? {1109 in cache if cache else False}")
            
    finally:
        await close_http_client()

if __name__ == '__main__':
    asyncio.run(main())
