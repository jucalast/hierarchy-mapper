
import asyncio
import httpx
from datetime import datetime

async def test_raw_inbox():
    print("[TEST] Rastreando ÚLTIMOS 20 E-MAILS da Caixa de Entrada (Sem filtro)...")
    
    email_service_url = "http://127.0.0.1:8002/api/email/messages"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Buscamos especificamente no Inbox, sem query, para ver quem são os últimos que te mandaram e-mail
            response = await client.get(f"{email_service_url}?folder=Inbox&limit=20")
            
            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                print(f"OK: Encontrei os {len(messages)} e-mails mais recentes do Inbox.")
                
                for msg in messages:
                    sender = msg.get("sender")
                    subject = msg.get("subject", "")
                    safe_subj = subject.encode('ascii', 'ignore').decode('ascii')
                    print(f"   -> REMETENTE: {sender} | ASSUNTO: {safe_subj}")
            else:
                print(f"ERRO: {response.status_code}")
        except Exception as e:
            print(f"ERRO: {e}")

if __name__ == "__main__":
    asyncio.run(test_raw_inbox())
