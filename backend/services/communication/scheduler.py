import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from services.communication.email_client import EmailClient
import os

def check_inbox_sync():
    """
    Executa a verificação IMAP sincronamente, pois as libs imaplib são bloqueantes.
    Usando executors do asyncio seria melhor, mas numa thread separada pelo APScheduler.
    """
    client = EmailClient()
    print("[APScheduler] Varrendo pasta de Leads por novas respostas...")
    
    # 2. O Gargalo de Performance do IMAP (Resolvido pela pasta /Leads)
    unreads = client.scan_inbound_replies(folder="Leads")
    
    if unreads:
        print(f"[APScheduler] Encontramos {len(unreads)} respostas novas das empresas!")
        for reply in unreads:
            # Aqui vai chamar o FastAPI, ou salvar no Postgres/SQLite
            print(f"-> Analisar intenção (Positiva/Negativa) de: {reply['sender']}")

scheduler = AsyncIOScheduler()

def start_email_scheduler():
    # O Background será orquestrado a cada 10 min
    # 3. O Risco de "Queimar" o Domínio Principal (Atrasos nos disparos e coletas assíncronas espalhadas)
    scheduler.add_job(check_inbox_sync, 'interval', minutes=10)
    scheduler.start()
    print("[APScheduler] Tarefa de IMAP configurada para rodar a cada 10 min.")
