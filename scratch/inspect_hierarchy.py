import asyncio
import sys
import os

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from core.infra.database import async_session
from modules.hierarchy.service.hierarchy_loader import get_stored_hierarchy

async def main():
    async with async_session() as session:
        hierarchy = await get_stored_hierarchy(268, session)
        print("COMPANY:", hierarchy["company_name"])
        print("STATUS:", hierarchy["status"])
        print("NODES:")
        for idx, node in enumerate(hierarchy["nodes"]):
            print(f"{idx}: id={node.get('id')}, name={node.get('name')}, department={node.get('department')}, manager_id={node.get('manager_id')}, level={node.get('level')}")

if __name__ == "__main__":
    asyncio.run(main())
