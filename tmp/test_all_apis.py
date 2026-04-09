import httpx
import asyncio
import re
import json

async def extract_domain_from_email(email):
    if not email or "@" not in str(email): return None
    parts = str(email).split("@")
    if len(parts) <= 1: return None
    domain_part = parts[-1].lower().strip()
    generic = ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br", "uol.com.br", "terra.com.br", "ig.com.br", "bol.com.br", "icloud.com"]
    if not any(gen in domain_part for gen in generic) and "." in domain_part:
        return domain_part
    return None

async def test_source(name, url, email_field="email"):
    print(f"--- Testando {name} ---")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url)
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                print("JSON Completo:")
                print(json.dumps(data, indent=2))
                email = data.get(email_field)
                domain = await extract_domain_from_email(email)
                print(f"E-mail: {email}")
                print(f"Domínio: {domain}")
                return domain
            else:
                print(f"Erro: {resp.status_code}")
        except Exception as e:
            print(f"Falha: {e}")
    return None

async def main(cnpj):
    clean_cnpj = re.sub(r'\D', '', cnpj)
    sources = [
        ("BrasilAPI", f"https://brasilapi.com.br/api/cnpj/v1/{clean_cnpj}"),
        ("MinhaReceita", f"https://minhareceita.org/{clean_cnpj}"),
        ("ReceitaWS", f"https://receitaws.com.br/v1/cnpj/{clean_cnpj}")
    ]
    
    for name, url in sources:
        domain = await test_source(name, url)
        if domain:
            print(f"\n✅ SUCESSO! Domínio '{domain}' encontrado via {name}")
            return
    print("\n❌ NENHUM domínio encontrado nas APIs oficiais.")

if __name__ == "__main__":
    import sys
    cnpj = sys.argv[1] if len(sys.argv) > 1 else "00.264.588/0002-71"
    asyncio.run(main(cnpj))
