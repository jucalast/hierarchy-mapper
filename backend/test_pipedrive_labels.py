import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from modules.crm.service.pipedrive_service import pipedrive_service

async def main():
    # Update person 16 with a verified label directly bypassing update_person bug
    payload = {
        "email": [{"value": "test@tuberfil.com.br", "primary": True, "label": "verified"}]
    }
    resp = await pipedrive_service._request("PUT", "persons/16", json=payload)
    if resp:
        print("Updated person 16. Checking...")
        resp2 = await pipedrive_service._request("GET", "persons/16")
        if resp2:
            print(resp2.json()["data"]["email"])

if __name__ == "__main__":
    asyncio.run(main())
