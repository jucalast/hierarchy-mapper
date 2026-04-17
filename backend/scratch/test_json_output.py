import httpx
import asyncio

async def test_search():
    async with httpx.AsyncClient() as client:
        # Testa o serviço de email diretamente
        resp = await client.get("http://localhost:8002/api/email/search?q=joaoluccas637")
        print(f"Email Service Response: {resp.status_code}")
        print(resp.json())
        
        # Testa a busca universal
        resp = await client.get("http://localhost:8000/api/v1/search/universal?q=@email%20joaoluccas637")
        print(f"\nUniversal Search Response: {resp.status_code}")
        print(resp.json())

if __name__ == "__main__":
    asyncio.run(test_search())
