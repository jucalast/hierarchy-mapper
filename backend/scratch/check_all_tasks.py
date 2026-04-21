import asyncio
import sys
import os
from dotenv import load_dotenv

# Adiciona o diretório backend ao path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

from services.pipedrive.pipedrive_service import pipedrive_service

async def check_tasks(org_id: int):
    details = await pipedrive_service.get_organization_details(org_id)
    activities = details.get("activities", [])
    print(f"\n--- ATIVIDADES DA ORG {org_id} ---")
    for act in activities:
        print(f"ID: {act['id']} | Subject: {act['subject']} | Done: {act['done']} (Type: {type(act['done'])})")

if __name__ == "__main__":
    asyncio.run(check_tasks(122))
