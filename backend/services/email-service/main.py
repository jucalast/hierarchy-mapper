from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
import os
import sys
from apscheduler.schedulers.background import BackgroundScheduler

# Adicionar o root ao path para localizar os módulos de serviços
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from services.communication.email_client import EmailClient

app = FastAPI(title="Email Discovery Service (Outlook Integrated)")

# CORS configurations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuração Padrão do Usuário
DEFAULT_EMAIL = os.getenv("EMAIL_USER", "joao.moura@jferres.com.br")
# Usar Outlook COM para leitura de emails (requer pywin32 + Outlook aberto)
client = EmailClient(email_address=DEFAULT_EMAIL, use_outlook_app=True)

@app.on_event("startup")
async def startup_event():
    """
    Configura sincronização em background e faz o primeiro fetch sem bloquear o startup.
    """
    pass

@app.get("/health")
def health_check():
    return {"status": "ok", "method": "Outlook Desktop" if client.use_outlook_app else "SMTP/IMAP"}

@app.post("/api/email/send")
async def send_email(
    to: str = Body(..., embed=True),
    subject: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
    tracking_id: Optional[str] = Body(None, embed=True),
    request_receipt: bool = Body(False, embed=True)
):
    """
    Envia um email utilizando o Outlook Desktop ou SMTP.
    """
    try:
        success = client.send_outbound_email(to, subject, body, tracking_id, request_read_receipt=request_receipt)
        if success:
            return {"success": True, "to": to, "subject": subject}
        else:
            raise HTTPException(status_code=500, detail="Erro ao enviar email.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/email/reply")
async def reply_email(
    entry_id: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
    reply_all: bool = Body(True, embed=True)
):
    """
    Responde a um email existente (Thread) usando o EntryID do Outlook.
    """
    try:
        success = client.reply_to_email(entry_id, body, reply_all)
        if success:
            return {"success": True, "entry_id": entry_id}
        else:
            raise HTTPException(status_code=500, detail="Erro ao responder email.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/email/folders")
async def get_folders():
    """
    Lista todas as pastas da conta conectada.
    """
    return {"folders": client.list_folders()}

@app.get("/api/email/messages")
async def get_messages(
    folder: str = "Inbox",
    limit: int = 10,
    q: Optional[str] = None
):
    """
    Busca mensagens de uma pasta específica.
    """
    messages = client.get_messages_from(folder, limit, query=q)
    return {"folder": folder, "count": len(messages), "messages": messages}

@app.get("/api/email/unread")
async def get_unread(
    folder: str = "Inbox",
    limit: int = 10
):
    """
    Busca apenas mensagens não lidas.
    """
    replies = client.scan_inbound_replies(folder, limit)
    return {"folder": folder, "count": len(replies), "messages": replies}

@app.post("/api/email/read-status")
async def mark_read(entry_id: str = Body(..., embed=True)):
    """
    Marca um email como lido.
    """
    success = client.mark_as_read(entry_id)
    return {"success": success}

@app.get("/api/email/search")
async def search_contacts(
    q: str = Query(..., min_length=1),
    limit: int = 10
):
    """
    Busca contatos no catálogo do Outlook.
    """
    results = client.search_contacts(q, limit)
    return {"results": results}

@app.get("/api/email/contacts/all")
async def get_all_contacts():
    """
    Retorna todos os contatos atualmente no cache do Outlook.
    """
    return {"results": EmailClient._contacts_cache}

@app.get("/api/email/signature")
async def get_signature():
    """
    Retorna a assinatura padrão do Outlook.
    """
    sig = client.get_default_signature()
    return {"signature": sig}

@app.get("/api/email/cache-status")
async def cache_status():
    return {
        "count": len(EmailClient._contacts_cache),
        "is_syncing": EmailClient._is_syncing,
        "timestamp": EmailClient._cache_timestamp,
        "ttl": EmailClient._CACHE_TTL,
        "has_pywin32": "win32com" in sys.modules
    }

if __name__ == "__main__":
    import uvicorn
    PORT = int(os.getenv("EMAIL_PORT", 8002))
    print(f"[Email Service] (Outlook Magic) rodando na porta {PORT} para {DEFAULT_EMAIL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
