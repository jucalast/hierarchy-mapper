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

async def setup_test_environment():
    print("[Setup] Configurando ambiente de testes para Agente...")
    
    url = f"https://api.pipedrive.com/v1/organizations?api_token={settings.PIPEDRIVE_API_TOKEN}"
    payload = {
        "name": "Agente Testes S.A. (Ficticia)",
        "address": "Av. Paulista, 1000, SP",
        "website": "agenteteste.com.br"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload)
        print(f"[Setup] Status Code: {resp.status_code}")
        try:
            res_data = resp.json()
            if res_data.get("success"):
                org_id = res_data["data"]["id"]
                print(f"[Setup] Empresa Criada com Sucesso: ID {org_id}")
            else:
                print(f"[Setup] Erro Pipedrive: {res_data}")
        except Exception as e:
            print(f"[Setup] Erro ao decodificar JSON: {e}")
            print(f"[Setup] RAW: {resp.text}")

if __name__ == "__main__":
    asyncio.run(setup_test_environment())
