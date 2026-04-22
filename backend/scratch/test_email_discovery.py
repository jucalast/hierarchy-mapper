
import asyncio
import httpx
from datetime import datetime

async def test_email_discovery():
    print("[TEST] Iniciando Teste de Auto-Descoberta de Pastas (Knorr)...")
    
    email_service_url = "http://127.0.0.1:8002/api/email/messages"
    # Buscando por apenas uma palavra forte para ativar a auto-descoberta de pastas
    query_str = "Knorr"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"-> Chamando EmailService para: '{query_str}' (Modo Conversa)...")
        try:
            response = await client.get(f"{email_service_url}?folder=Conversations&limit=30&q={query_str}")
            
            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                print(f"OK: Total de mensagens encontradas: {len(messages)}")
                
                # Vamos listar os remetentes e a pasta de origem se possível
                for msg in messages:
                    sender = msg.get("sender", "").lower()
                    subject = msg.get("subject", "").encode('ascii', 'ignore').decode('ascii')
                    print(f"   [MSG] {sender} | Subj: {subject}")

                if len(messages) > 10:
                    print("\n🏆 SUCESSO ABSOLUTO! O sistema achou mais mensagens do que as 10 padrões dos Enviados.")
                    print("Isso significa que ele leu os e-mails da pasta 'KNORR BRENSE'!")
                else:
                    print("\n⚠️ ALERTA: Ainda achou apenas as mesmas mensagens. Cheque o log do backend para ver se o print 'Auto-descoberta' apareceu.")
            else:
                print(f"ERRO: {response.status_code}")
                
        except Exception as e:
            print(f"ERRO: Failliure: {e}")

if __name__ == "__main__":
    asyncio.run(test_email_discovery())
