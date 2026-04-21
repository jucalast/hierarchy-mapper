import asyncio
import sys
import os
from dotenv import load_dotenv
import httpx

# Adiciona o diretório backend ao path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

from services.pipedrive.pipedrive_service import pipedrive_service

async def cleanup_last_activity(org_id: int):
    # API do Pipedrive para listar atividades da org
    token = os.getenv("PIPEDRIVE_API_TOKEN")
    url = f"https://api.pipedrive.com/v1/organizations/{org_id}/activities?api_token={token}&done=0"
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        data = resp.json()
        activities = data.get("data") or []
        
        if not activities:
            print(f"[Cleanup] Nenhuma atividade pendente encontrada para a org {org_id}.")
            return

        # Ordena por ID decrescente para pegar a última
        activities.sort(key=lambda x: x['id'], reverse=True)
        last_id = activities[0]['id']
        subject = activities[0]['subject']
        
        print(f"[Cleanup] Removendo atividade mais recente: {last_id} ({subject})...")
        success = await pipedrive_service.delete_activity(last_id)
        if success:
            print(f"[Cleanup] Atividade {last_id} removida com sucesso.")
        else:
            print(f"[Cleanup] Falha ao remover atividade {last_id}.")

if __name__ == "__main__":
    # Agente Testes S.A. (Ficticia) costuma ser pipedrive_id 122 ou similar
    # Vamos pegar da base de dados se possível, ou usar o ID 122 que vi nos logs
    asyncio.run(cleanup_last_activity(122))
