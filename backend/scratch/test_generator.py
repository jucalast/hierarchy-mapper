import asyncio
import os
import sys

# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.intelligence.service.brand_discovery_stream import discover_company_brand_stream

async def main():
    try:
        async for event in discover_company_brand_stream(cnpj="71444475000115", force=True):
            print("EVENT:", event)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
