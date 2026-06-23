import httpx
import asyncio
import json

async def main():
    async with httpx.AsyncClient() as client:
        r = await client.get('http://localhost:3005/messages?folder=conversations&q=helena.santana@axt.com.br', timeout=30.0)
        print("Status 3005:", r.status_code)
        try:
            print("Response 3005:", json.dumps(r.json(), indent=2))
        except:
            print("Response text 3005:", r.text)

if __name__ == "__main__":
    asyncio.run(main())
