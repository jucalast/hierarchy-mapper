
import asyncio
import os
import sys
import httpx

# Adiciona o diretório backend ao path para importar core
sys.path.append(os.path.join(os.getcwd(), "backend"))
from core.config import settings

async def check(model):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": "hi"}]}]}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=5.0)
            print(f"{model}: {resp.status_code}")
    except Exception as e:
        print(f"{model}: Error {e}")

async def main():
    models = [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-flash-latest"
    ]
    await asyncio.gather(*(check(m) for m in models))

if __name__ == "__main__":
    asyncio.run(main())
