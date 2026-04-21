import asyncio
import sys
import os
from dotenv import load_dotenv

# Adiciona o diretório backend ao path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

from services.pipedrive.pipedrive_service import pipedrive_service

async def cleanup_test_activity(activity_id: int):
    print(f"[Cleanup] Removendo atividade {activity_id}...")
    success = await pipedrive_service.delete_activity(activity_id)
    if success:
        print(f"[Cleanup] Atividade {activity_id} removida.")
    else:
        print(f"[Cleanup] Falha ao remover {activity_id}.")

if __name__ == "__main__":
    # ID da tarefa criada na última rodada
    asyncio.run(cleanup_test_activity(7807))
