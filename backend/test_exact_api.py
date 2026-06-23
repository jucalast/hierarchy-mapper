import sys
import asyncio
import json
import httpx
sys.path.append('c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/backend')

from modules.agent.service.tools.communication import EMAIL_SERVICE_BASE

async def main():
    async with httpx.AsyncClient(timeout=15.0) as client:
        url = f"{EMAIL_SERVICE_BASE}/messages"
        params = {"folder": "conversations", "limit": 20, "q": "helena.santana@axt.com.br"}
        print("URL:", url)
        print("Params:", params)
        r = await client.get(url, params=params)
        print("Status:", r.status_code)
        data = r.json()
        print("Count in API:", data.get("count"))
        messages = data.get("messages", [])
        print("Num messages:", len(messages))
        if messages:
            print("First msg ID:", messages[0].get("entryId"))

if __name__ == "__main__":
    asyncio.run(main())
