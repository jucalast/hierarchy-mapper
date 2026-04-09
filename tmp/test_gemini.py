import os
import httpx
import asyncio
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def test_gemini():
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("❌ GEMINI_API_KEY não encontrada no .env")
        return

    model = "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
    
    payload = {
        "contents": [{"parts": [{"text": "Diga 'Gemini Online' se você estiver funcionando."}]}],
        "generationConfig": {"maxOutputTokens": 20}
    }
    
    print(f"📡 Testando {model}...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                text = resp.json()['candidates'][0]['content']['parts'][0]['text']
                print(f"✅ RESSPOSTA: {text.strip()}")
            else:
                print(f"❌ ERRO {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"💥 EXCEÇÃO: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
