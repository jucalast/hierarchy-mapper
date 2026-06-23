import asyncio
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'backend'))

from modules.crm.service.pipedrive_service import pipedrive_service

async def main():
    r = await pipedrive_service.make_request('GET', 'users/me')
    if r:
        print(r.json())
    else:
        print("No response")

if __name__ == '__main__':
    asyncio.run(main())
