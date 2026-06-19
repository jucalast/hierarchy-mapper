import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.crm.service.pipedrive_service import pipedrive_service

async def main():
    details = await pipedrive_service.get_organization_details(1080)
    deals = details.get('deals', [])
    if deals:
        print("KEYS:", deals[0].keys())
        print("PERSON_ID:", deals[0].get('person_id'))
        print("PERSON_NAME:", deals[0].get('person_name'))
    else:
        print("No deals")

if __name__ == "__main__":
    asyncio.run(main())
