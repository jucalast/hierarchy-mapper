import asyncio
import httpx
import sys
import os

# Adiciona o diretório backend ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.pipedrive.pipedrive_service import pipedrive_service

async def check_headers():
    url = f"{pipedrive_service.base_url}/users/me?api_token={pipedrive_service.api_token}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        print(f"Status Code: {resp.status_code}")
        print("\n--- HEADERS DE COTA ---")
        for key, value in resp.headers.items():
            if "ratelimit" in key.lower() or "retry" in key.lower():
                print(f"{key}: {value}")
        
        if resp.status_code == 429:
            print("\nO Pipedrive confirmou o bloqueio.")
            print("Pela documentação oficial, o reset ocorre sempre às 00:00 UTC (21h00 BRT).")

if __name__ == "__main__":
    asyncio.run(check_headers())
