import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def main():
    from backend.modules.crm.service.pipedrive_service import pipedrive_service
    from backend.modules.agent.service.tools._utils import _pipedrive_find_org
    
    match, org_id = await _pipedrive_find_org("Hi Gi Sim")
    print(f"Org ID: {org_id}")
    if org_id:
        details = await pipedrive_service.get_organization_details(org_id)
        persons = details.get("persons", [])
        for p in persons:
            print(f"Person: {p.get('name')}")
            for email in p.get("email", []):
                print(f"  Email: {email.get('value')}")
                
if __name__ == "__main__":
    asyncio.run(main())
