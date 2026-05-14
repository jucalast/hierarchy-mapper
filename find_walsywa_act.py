
import asyncio
import os
import sys

# Add backend to path
sys.path.append('backend')

from services.pipedrive.pipedrive_service import pipedrive_service

async def main():
    orgs = await pipedrive_service.search_organization('Walsywa')
    if not orgs:
        print('Org not found')
        return
    org = orgs[0]
    org_id = org['id']
    
    resp = await pipedrive_service.make_request('GET', 'activities', params={'org_id': org_id, 'user_id': 0, 'done': 0})
    if resp and resp.status_code == 200:
        data = resp.json().get('data', [])
        if not data:
            print('No pending activities found')
        else:
            for act in data:
                subject = act.get('subject', '').lower()
                if 'orçamento' in subject or 'follow-up' in subject or 'retorno' in subject:
                    print(f"ACT_ID: {act['id']}, Subject: {act['subject']}, Due: {act['due_date']}, Status: {act['done']}")
    else:
        print(f'Error fetching activities: {resp.status_code if resp else "No response"}')

if __name__ == '__main__':
    asyncio.run(main())
