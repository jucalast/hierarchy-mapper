import sys
import asyncio
import json
sys.path.append('c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/backend')

from modules.agent.service.tools.communication import exec_batch_communication_search

async def main():
    args = {
        "org_name": "axt terminais eletricos",
        "contacts": [
            {"name": "Helena Santana", "email": "helena.santana@axt.com.br"}
        ]
    }
    
    print("\nExecutando batch_communication_search como o Agente...")
    res = await exec_batch_communication_search(args)
    
    print("\nResultado final que o LLM vai ler:")
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    import asyncio
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
