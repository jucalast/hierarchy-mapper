import httpx
import asyncio
import json

async def test():
    cnpj = "00416170000151"
    urls = [
        f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}",
        f"https://minhareceita.org/{cnpj}",
        f"https://receitaws.com.br/v1/cnpj/{cnpj}"
    ]
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in urls:
            print(f"\n--- Testing {url} ---")
            try:
                resp = await client.get(url)
                print(f"Status Code: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"Email field value: {data.get('email')}")
                    # Se for receitaws, o valor as vezes vem em outro campo
                    if "receitaws" in url:
                        print(f"ReceitaWS email field: {data.get('email')}")
                else:
                    print(f"Error content: {resp.text[:200]}")
            except Exception as e:
                print(f"Error during request to {url}: {e}")

if __name__ == "__main__":
    asyncio.run(test())
