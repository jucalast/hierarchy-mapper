import asyncio
import os
import sys

backend_path = r"c:\Users\João Luccas\Desktop\LINKB2B\hierarchy-mapper\backend"
sys.path.append(backend_path)
os.chdir(backend_path)

from api.v1.routers.calls import get_call_history

async def run():
    # Test with org_id = 830 (Torcetex Pipedrive ID)
    res = await get_call_history(org_id=830)
    print("For org_id = 830:")
    print(res)
    print("-" * 50)
    
    # Test with org_id = 1072 (Alessandra Cardoso's company)
    res_2 = await get_call_history(org_id=1072)
    print("For org_id = 1072:")
    print(res_2)
    print("-" * 50)

if __name__ == "__main__":
    asyncio.run(run())
