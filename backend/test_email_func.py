import sys
import asyncio
import json
sys.path.append('c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/backend')

from modules.agent.service.tools.communication import exec_email_get_contact_history

async def main():
    args = {
        "org_name": "axt terminais eletricos"
    }
    print("Testando exec_email_get_contact_history para a organização...")
    res = await exec_email_get_contact_history(args)
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
