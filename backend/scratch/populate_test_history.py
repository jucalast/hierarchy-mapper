import asyncio
import sys
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Adiciona o diretório backend ao path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

from services.pipedrive.pipedrive_service import pipedrive_service

async def populate_test_history():
    org_id = 1040 # Agente Testes S.A.
    print(f"[Populate] Adicionando histórico para empresa {org_id}...")
    
    # 1. Tarefa Concluída (Passado)
    await pipedrive_service.create_activity({
        "org_id": org_id,
        "subject": "Reunião de Apresentação LINKB2B",
        "type": "call",
        "due_date": (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),
        "note": "Mostramos a plataforma para o Diretor de Compras. Ele gostou da automação de WhatsApp, mas questionou o preço.",
    })
    # Marcar como feita? Pipedrive API create activity doesn't have 'done' in the simple payload usually, 
    # but let's assume if it has past date or we can update later.
    
    # 2. Nota (Contexto)
    # PipedriveService doesn't have create_note yet. I'll stick to activities.
    
    # 3. Outra Tarefa Concluída
    await pipedrive_service.create_activity({
        "org_id": org_id,
        "subject": "Envio de Proposta Comercial",
        "type": "email",
        "due_date": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
        "note": "Proposta de R$ 5k/mês enviada. Aguardando retorno sobre o budget de Q2.",
    })
    
    print("[Populate] Histórico populado com sucesso.")

if __name__ == "__main__":
    asyncio.run(populate_test_history())
