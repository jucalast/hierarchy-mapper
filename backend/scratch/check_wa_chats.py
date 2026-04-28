import httpx
import asyncio

async def check_wa():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get("http://localhost:8001/api/whatsapp/chats")
            print("CHATS ATIVOS:")
            print(resp.json())
        except Exception as e:
            print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(check_wa())
