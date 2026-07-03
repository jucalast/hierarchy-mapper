import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.infra.http_client import get_http_client
from core.config import settings

async def main():
    client = get_http_client()
    token = os.getenv("PIPEDRIVE_API_TOKEN")
    url = f"https://api.pipedrive.com/v1/users/me?api_token={token}"
    
    print("Iniciando rajada de requisições...")
    tasks = []
    
    for i in range(100):
        tasks.append(client.get(url))
        
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, resp in enumerate(responses):
        if isinstance(resp, Exception):
            continue
        if resp.status_code == 429:
            print(f"\n[429 RATE LIMIT] Requisição #{i+1}")
            print("Headers:")
            for k, v in resp.headers.items():
                if "limit" in k.lower() or "retry" in k.lower():
                    print(f"  {k}: {v}")
            print("\nBody:")
            print(resp.text)
            break
    else:
        print("Nenhum 429 recebido em 100 requisições simultâneas.")

if __name__ == "__main__":
    asyncio.run(main())
