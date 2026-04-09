
import asyncio
from services.hierarchy.search_engine import get_duck_results

async def test():
    query = 'site:br.linkedin.com/in/ "Spcom" (Comprador OR Compradora OR Buyer OR "Analista de Compras" OR "Analista de Suprimentos")'
    print(f"Testing query: {query}")
    results = await get_duck_results(query)
    print(f"Results found: {len(results)}")
    for res in results:
        print(f"DEBUG RESULT: {res}")
        print(f" - {res.get('href')} | {res.get('title')}")

if __name__ == "__main__":
    asyncio.run(test())
