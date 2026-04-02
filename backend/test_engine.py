import asyncio
from services.search_engine import get_duck_results_async
import time

async def main():
    start = time.time()
    results = await get_duck_results_async('site:br.linkedin.com/in/ "Ambev" "compras"')
    print(f"Time: {time.time() - start:.2f}s")
    print(f"Found {len(results)} employees")
    for r in results[:5]:
        print(r)

asyncio.run(main())
