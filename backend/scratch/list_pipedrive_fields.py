import asyncio
import sys
import os
import httpx
from dotenv import load_dotenv

# Adiciona o diretório backend ao path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Carrega .env explicitamente
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

from core.config import settings

async def list_custom_fields():
    print("[Setup] Listando campos customizados de Organizacao...")
    
    url = f"https://api.pipedrive.com/v1/organizationFields?api_token={settings.PIPEDRIVE_API_TOKEN}"
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code == 200:
            data = resp.json()
            fields = data.get("data", [])
            for f in fields:
                print(f"Nome: {f['name']} | Key: {f['key']}")
        else:
            print(f"Erro: {resp.status_code}")
            print(resp.text)

if __name__ == "__main__":
    asyncio.run(list_custom_fields())
