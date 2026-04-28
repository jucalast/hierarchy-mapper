
import asyncio
import sys
import os

# Add current directory to sys.path
sys.path.append(os.getcwd())

from services.pipedrive.pipedrive_service import pipedrive_service

async def main():
    try:
        # Check specific activities created in the log
        target_ids = [7985, 7986]
        for aid in target_ids:
            resp = await pipedrive_service._request('GET', f'activities/{aid}')
            if resp and resp.status_code == 200:
                data = resp.json().get('data', {})
                print(f"Activity {aid}: Found! Subject: {data.get('subject')}, Org: {data.get('org_id')}, Done: {data.get('done')}")
            else:
                print(f"Activity {aid}: Not found or error ({resp.status_code if resp else 'No response'})")
        
        # List all open activities for org 796 just to be sure
        print("\n--- All Open Activities for Bottcher (Org 796) ---")
        resp_list = await pipedrive_service._request('GET', 'activities', params={'org_id': 796, 'done': 0})
        if resp_list and resp_list.status_code == 200:
            activities = resp_list.json().get('data') or []
            for act in activities:
                print(f"ID: {act['id']}, Subject: {act['subject']}, Done: {act['done']}")
        else:
            print(f"Could not list activities for org 796")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == '__main__':
    asyncio.run(main())
