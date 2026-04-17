import asyncio
import os
import sys
import html
from typing import List, Dict

# Ajustar path para importar os servicos
sys.path.append(os.path.join(os.getcwd(), "backend"))

from services.hierarchy.search_engine import get_duck_results

async def test_raw_results(query: str):
    print(f"\n{'='*80}")
    print(f"DEBUG: DADOS BRUTOS DA BUSCA")
    print(f"QUERY: {query}")
    print(f"{'='*80}\n")
    
    results = await get_duck_results(query, max_results=30)
    
    if not results:
        print("Nenhum resultado encontrado.")
        return

    for idx, res in enumerate(results):
        try:
            title = html.unescape(res.get('title', 'N/A'))
            body = html.unescape(res.get('body', res.get('snippet', 'N/A')))
            href = res.get('href', 'N/A')
            
            # Garantir que caracteres especiais nao quebrem o console windows
            print(f"[{idx+1}] TÍTULO: {title.encode('ascii', errors='replace').decode('ascii')}")
            print(f"    LINK: {href}")
            print(f"    BODY: {body.encode('ascii', errors='replace').decode('ascii')}")
            print("-" * 40)
        except Exception as e:
            print(f"[{idx+1}] Erro ao exibir resultado: {e}")

if __name__ == "__main__":
    # Exemplo: A mesma busca que o sistema faz para a Verônica
    target_query = "Verônica Lima Grow Química e Farmacêutica Salto linkedin cargo experiência"
    
    # Se o usuário passou argumentos, usa o primeiro como query
    if len(sys.argv) > 1:
        target_query = " ".join(sys.argv[1:])
        
    asyncio.run(test_raw_results(target_query))
