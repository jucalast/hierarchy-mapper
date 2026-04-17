import sys
import os
import asyncio

# Adiciona o diretório backend ao sys.path
backend_path = r'c:\Users\João Luccas\Desktop\LINKB2B\hierarchy-mapper\backend'
sys.path.append(backend_path)

from services.communication.email_client import EmailClient

async def debug_search():
    print("--- Detailed Search Debug ---")
    query = "João Luccas"
    print(f"Original Query: '{query}'")
    
    client = EmailClient(use_outlook_app=True)
    norm_query = client._normalize_str(query)
    print(f"Normalized Query: '{norm_query}'")
    
    # Simula a busca de contatos
    print(f"\nBuscando...")
    results = client.search_contacts(query)
    
    print(f"\nResultados encontrados: {len(results)}")
    if results:
        for r in results:
            print(f" - {r['name']} <{r['email']}>")
    else:
        print("Nenhum resultado encontrado. Analisando o cache para 'joao' e 'luccas' separadamente...")
        for c in client._contacts_cache:
            if "joao" in c['norm_name'] and "luccas" in c['norm_name']:
                print(f"MATCH TOTAL NO CACHE: '{c['name']}' | Norm: '{c['norm_name']}'")
                print(f"Compact match test ('joaoluccas' in '{c['norm_name'].replace(' ','')}'): {'joaoluccas' in c['norm_name'].replace(' ','')}")

if __name__ == "__main__":
    asyncio.run(debug_search())
