
import asyncio
import httpx
from datetime import datetime

async def test_email_archaeology():
    print("[TEST] Iniciando Teste de Arqueologia de E-mail (Pesquisa por DOMINIO: '@knorr-bremse.com')...")
    
    email_service_url = "http://127.0.0.1:8002/api/email/messages"
    # Vamos buscar por @knorr-bremse.com para matar a dúvida se o e-mail dele é diferente
    query_str = "knorr-bremse.com"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"-> Chamando EmailService com query: '{query_str}'...")
        try:
            # Pegamos até 30 mensagens para ver o fluxo
            response = await client.get(f"{email_service_url}?folder=Conversations&limit=30&q={query_str}")
            
            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                print(f"OK: Total de mensagens relacionadas ao dominio: {len(messages)}")
                
                respostas_matheus = 0
                for msg in messages:
                    sender = msg.get("sender", "").lower()
                    to = msg.get("to", "").lower()
                    subject = msg.get("subject", "")
                    date = msg.get("date", "")
                    
                    # Verificamos se o remetente é alguém da Knorr (não você)
                    if "knorr-bremse.com" in sender:
                        respostas_matheus += 1
                        # Usamos encode/decode para evitar erro de encoding no terminal Windows
                        safe_subj = subject.encode('ascii', 'ignore').decode('ascii')
                        print(f"   [IN] RESPOSTA DE {sender}: [{date}] | Assunto: {safe_subj}")
                    else:
                        safe_subj = subject.encode('ascii', 'ignore').decode('ascii')
                        print(f"   [OUT] ENVIADO POR VOCE: [{date}] PARA: {to} | Assunto: {safe_subj}")

                if respostas_matheus == 0:
                    print("\n[ALERTA] CONTINUAMOS SEM RESPOSTAS DELE. Mesmo no dominio knorr-bremse.com, so achei e-mails enviados por voce.")
                else:
                    print(f"\n[SUCESSO] EXPLOSAO! Encontrei {respostas_matheus} respostas da Knorr Bremse.")
            else:
                print(f"ERRO: {response.status_code}")
        except Exception as e:
            print(f"ERRO CRITICO: {e}")

if __name__ == "__main__":
    asyncio.run(test_email_archaeology())
