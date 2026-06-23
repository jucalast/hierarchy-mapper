import sys
import asyncio
import json
sys.path.append('c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/backend')

from modules.agent.service.tools.communication import _extract_org_domain

async def main():
    print(await _extract_org_domain("axt terminais eletricos"))

if __name__ == "__main__":
    asyncio.run(main())
