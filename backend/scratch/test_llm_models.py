
import asyncio
import os
import sys

# Adiciona o diretório backend ao path para importar core e services
sys.path.append(os.getcwd())

from core.config import settings
from core.http_client import get_http_client
from services.ai.llm.base import LLMMessage

async def test_gemini_model(model_name: str):
    print(f"Testing Gemini model: {model_name}...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={settings.GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 5}
    }
    client = get_http_client()
    try:
        resp = await client.post(url, json=payload, timeout=10.0)
        if resp.status_code == 200:
            print(f"  SUCCESS: {model_name}")
            return True
        else:
            print(f"  FAILED: {model_name} ({resp.status_code}) - {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"  ERROR: {model_name} - {str(e)}")
        return False

async def test_groq_model(model_name: str):
    print(f"Testing Groq model: {model_name}...")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }
    client = get_http_client()
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=10.0)
        if resp.status_code == 200:
            print(f"  SUCCESS: {model_name}")
            return True
        else:
            print(f"  FAILED: {model_name} ({resp.status_code}) - {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"  ERROR: {model_name} - {str(e)}")
        return False

async def main():
    print("--- STARTING LLM MODEL TESTS ---")
    
    gemini_candidates = [
        "gemini-flash-latest",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-2.0-flash-exp",
        "gemini-3-flash-preview",
        "gemini-1.5-pro",
        "gemini-2.0-pro-exp"
    ]
    
    groq_candidates = [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama-3.1-8b-instant",
        "llama3-70b-8192",
        "llama3-8b-8192",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
        "llama-3.2-11b-text-preview",
        "llama-3.2-3b-preview"
    ]
    
    working_gemini = []
    exists_gemini = []
    for m in gemini_candidates:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={settings.GEMINI_API_KEY}"
        client = get_http_client()
        try:
            resp = await client.post(url, json={"contents": [{"parts": [{"text": "hi"}]}]}, timeout=10.0)
            if resp.status_code == 200:
                working_gemini.append(m)
                exists_gemini.append(m)
                print(f"  SUCCESS: {m}")
            elif resp.status_code == 429:
                exists_gemini.append(m)
                print(f"  RATE_LIMIT (exists): {m}")
            else:
                print(f"  FAILED ({resp.status_code}): {m}")
        except Exception as e:
            print(f"  ERROR: {m} - {e}")
            
    working_groq = []
    exists_groq = []
    for m in groq_candidates:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
        client = get_http_client()
        try:
            resp = await client.post(url, json={"model": m, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                working_groq.append(m)
                exists_groq.append(m)
                print(f"  SUCCESS: {m}")
            elif resp.status_code == 429:
                exists_groq.append(m)
                print(f"  RATE_LIMIT (exists): {m}")
            else:
                print(f"  FAILED ({resp.status_code}): {m}")
        except Exception as e:
            print(f"  ERROR: {m} - {e}")
            
    print("\n--- SUMMARY ---")
    print(f"Working Gemini: {working_gemini}")
    print(f"Existing Gemini (but maybe rate limited): {exists_gemini}")
    print(f"Working Groq: {working_groq}")
    print(f"Existing Groq (but maybe rate limited): {exists_groq}")

if __name__ == "__main__":
    asyncio.run(main())
