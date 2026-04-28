
import asyncio
import sys
import os

# Add current directory to sys.path
sys.path.append(os.getcwd())

from services.pipedrive.pipedrive_service import pipedrive_service

async def main():
    try:
        org_id = 809
        print(f"--- Searching Deals for Org {org_id} (Dva) ---")
        
        # 1. Try organizations/{id}/deals
        resp = await pipedrive_service._request('GET', f'organizations/{org_id}/deals', params={'user_id': pipedrive_service.user_id})
        deals = resp.json().get('data') or [] if resp and resp.status_code == 200 else []
        print(f"Deals found via org endpoint: {len(deals)}")
        for d in deals:
            print(f"  Deal ID: {d['id']}, Title: {d['title']}, Status: {d['status']}")

        # 2. Try global search if nothing found
        if not deals:
            print("\n--- Searching all open deals ---")
            resp_all = await pipedrive_service._request('GET', 'deals', params={'status': 'open', 'limit': 500})
            all_deals = resp_all.json().get('data') or [] if resp_all and resp_all.status_code == 200 else []
            for d in all_deals:
                d_org_id = d.get('org_id')
                if isinstance(d_org_id, dict):
                    d_org_id = d_org_id.get('value')
                
                if d_org_id == org_id:
                    print(f"  MATCH FOUND: Deal ID: {d['id']}, Title: {d['title']}")
                    deals.append(d)

        if not deals:
            print("NO DEALS FOUND for this organization.")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == '__main__':
    asyncio.run(main())
