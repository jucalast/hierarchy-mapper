import httpx
import asyncio

async def main():
    url = "http://localhost:8002/api/email/messages"
    params = {"folder": "conversations", "q": "helena.santana@axt.com.br", "limit": 10}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, params=params, timeout=30.0)
            print("Status:", r.status_code)
            import json
            print("Response:", json.dumps(r.json(), indent=2, ensure_ascii=False))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
