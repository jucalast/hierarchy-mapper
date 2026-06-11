import asyncio
import httpx

async def main():
    api_key = "a7561d8cf9a342abb24c7040a008d677"
    email = "suporte@github.com"
    url = "https://emailvalidation.abstractapi.com/v1/"
    params = {"api_key": api_key, "email": email}
    
    print("Enviando requisição para a Abstract API...")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params)
            print(f"Status Code: {r.status_code}")
            print(f"Headers: {dict(r.headers)}")
            print(f"Response Body: {r.text}")
    except Exception as e:
        print(f"Ocorreu um erro: {e}")

if __name__ == "__main__":
    asyncio.run(main())
