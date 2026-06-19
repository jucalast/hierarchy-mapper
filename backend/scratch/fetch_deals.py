import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.crm.service.pipedrive_service import pipedrive_service

async def main():
    try:
        deals_count = 0
        start = 0
        limit = 500
        has_more = True
        
        while has_more:
            resp = await pipedrive_service._request("GET", "deals", params={"org_id": 1080, "start": start, "limit": limit})
            if resp and resp.status_code == 200:
                json_data = resp.json()
                data = json_data.get("data") or []
                deals_count += len(data)
                
                pagination = json_data.get("additional_data", {}).get("pagination", {})
                has_more = pagination.get("more_items_in_collection", False)
                if has_more:
                    start = pagination.get("next_start")
            else:
                print("Failed to fetch deals", resp.status_code if resp else "None")
                break
                
        print(f"Total Metasil Deals: {deals_count}")
    except Exception as e:
        print(f"Error fetching deals: {e}")

asyncio.run(main())
