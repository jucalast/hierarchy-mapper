import httpx
import asyncio

async def main():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get('http://localhost:8002/api/email/messages?folder=conversations&q=axt.com.br', timeout=30.0)
            print(r.status_code, len(r.json()))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
