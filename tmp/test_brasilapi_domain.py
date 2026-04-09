import httpx
import asyncio
import re

async def extract_domain_from_email(email):
    if not email or "@" not in str(email): return None
    parts = str(email).split("@")
    if len(parts) <= 1: return None
    domain_part = parts[-1].lower().strip()
    generic = [
        "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br",
        "uol.com.br", "terra.com.br", "ig.com.br", "bol.com.br", "icloud.com",
        "contabilidade", "consultoria", "advocacia", "me.com", "outlook.com.br",
        "uol.com", "live.com", "msn.com", "apple.com"
    ]
    if not any(gen in domain_part for gen in generic) and "." in domain_part:
        return domain_part
    return None

async def test_cnpj(cnpj):
    clean_cnpj = re.sub(r'\D', '', cnpj)
    url = f"https://brasilapi.com.br/api/cnpj/v1/{clean_cnpj}"
    print(f"--- Testando CNPJ: {cnpj} ---")
    print(f"URL: {url}")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                import json
                print("--- Full JSON ---")
                print(json.dumps(data, indent=2))
                print("----------------")
                name = data.get("razao_social")
                email = data.get("email")
                domain = await extract_domain_from_email(email)
                
                print(f"Razão Social: {name}")
                print(f"E-mail: {email}")
                print(f"Domínio Extraído: {domain}")
            else:
                print(f"Erro: {resp.text}")
        except Exception as e:
            print(f"Falha na conexão: {e}")

if __name__ == "__main__":
    import sys
    cnpj = sys.argv[1] if len(sys.argv) > 1 else "00.264.588/0002-71"
    asyncio.run(test_cnpj(cnpj))
