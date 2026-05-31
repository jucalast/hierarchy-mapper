from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
import asyncio
import os
import sys
import threading

if sys.platform == "win32":
    import asyncio
    from asyncio import WindowsProactorEventLoopPolicy
    if not isinstance(asyncio.get_event_loop_policy(), WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())

# Adicionar o root ao path para localizar os módulos de serviços
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from modules.communication.service.email.client import EmailClient

app = FastAPI(title="Email Discovery Service (Outlook Integrated)")

# CORS configurations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_EMAIL = os.getenv("EMAIL_USER", "joao.moura@jferres.com.br")

# Inicialização lazy — o EmailClient conecta ao COM do Outlook (pywin32) e leva
# ~30s. Fazer isso no nível do módulo bloqueia o import e impede o uvicorn de
# registrar o processo filho. A inicialização acontece em asyncio.Task no startup
# usando asyncio.to_thread para não bloquear o event loop.
_client: Optional[EmailClient] = None
_client_ready: Optional[asyncio.Event] = None  # criado no startup (precisa do event loop)


def _create_client_sync() -> Optional[EmailClient]:
    """Cria o EmailClient de forma síncrona (roda em thread pool via asyncio.to_thread)."""
    try:
        c = EmailClient(email_address=DEFAULT_EMAIL, use_outlook_app=True)
        print(f"[Email Service] Cliente Outlook inicializado para {DEFAULT_EMAIL}")
        return c
    except Exception as e:
        print(f"[Email Service] Falha ao inicializar cliente Outlook: {e}")
        return None


async def get_client() -> EmailClient:
    """Retorna o cliente se pronto; 503 imediato caso contrário.

    Retornar 503 imediatamente (sem esperar) evita que a conexão httpx do
    backend principal expire enquanto o Outlook ainda inicializa (~30s). O
    chamador trata 503 como "serviço indisponível" e continua sem bloquear.
    """
    if _client is None:
        raise HTTPException(
            status_code=503,
            detail="Outlook ainda inicializando. Tente novamente em instantes.",
        )
    return _client


@app.on_event("startup")
async def startup_event():
    """Dispara a inicialização do Outlook em thread pool sem bloquear o event loop."""
    global _client, _client_ready
    _client_ready = asyncio.Event()

    async def _init():
        global _client
        _client = await asyncio.to_thread(_create_client_sync)
        _client_ready.set()

    asyncio.create_task(_init())

@app.get("/health")
def health_check():
    ready = _client_ready.is_set() and _client is not None
    return {
        "status": "ok" if ready else "initializing",
        "method": "Outlook Desktop" if (ready and _client.use_outlook_app) else "pending",
    }

@app.post("/api/email/send")
async def send_email(
    to: str = Body(..., embed=True),
    subject: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
    tracking_id: Optional[str] = Body(None, embed=True),
    request_receipt: bool = Body(False, embed=True)
):
    """Envia um email utilizando o Outlook Desktop ou SMTP."""
    c = await get_client()
    try:
        success = c.send_outbound_email(to, subject, body, tracking_id, request_read_receipt=request_receipt)
        if success:
            return {"success": True, "to": to, "subject": subject}
        raise HTTPException(status_code=500, detail="Erro ao enviar email.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/email/reply")
async def reply_email(
    entry_id: str = Body(..., embed=True),
    body: str = Body(..., embed=True),
    reply_all: bool = Body(True, embed=True)
):
    """Responde a um email existente (Thread) usando o EntryID do Outlook."""
    c = await get_client()
    try:
        success = c.reply_to_email(entry_id, body, reply_all)
        if success:
            return {"success": True, "entry_id": entry_id}
        raise HTTPException(status_code=500, detail="Erro ao responder email.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/email/folders")
async def get_folders():
    """Lista todas as pastas da conta conectada."""
    return {"folders": (await get_client()).list_folders()}

@app.get("/api/email/messages")
async def get_messages(
    folder: str = "Inbox",
    limit: int = 10,
    q: Optional[str] = None
):
    """Busca mensagens de uma pasta específica."""
    messages = (await get_client()).get_messages_from(folder, limit, query=q)
    return {"folder": folder, "count": len(messages), "messages": messages}

@app.get("/api/email/unread")
async def get_unread(
    folder: str = "Inbox",
    limit: int = 10
):
    """Busca apenas mensagens não lidas."""
    replies = (await get_client()).scan_inbound_replies(folder, limit)
    return {"folder": folder, "count": len(replies), "messages": replies}

@app.post("/api/email/read-status")
async def mark_read(entry_id: str = Body(..., embed=True)):
    """Marca um email como lido."""
    success = (await get_client()).mark_as_read(entry_id)
    return {"success": success}

@app.get("/api/email/search")
async def search_contacts(
    q: str = Query(..., min_length=1),
    limit: int = 10
):
    """Busca contatos no catálogo do Outlook."""
    results = (await get_client()).search_contacts(q, limit)
    return {"results": results}

@app.get("/api/email/contacts/all")
async def get_all_contacts():
    """Retorna todos os contatos atualmente no cache do Outlook."""
    return {"results": EmailClient._contacts_cache}

@app.get("/api/email/signature")
async def get_signature():
    """Retorna a assinatura padrão do Outlook."""
    sig = (await get_client()).get_default_signature()
    return {"signature": sig}

@app.get("/api/email/cache-status")
async def cache_status():
    return {
        "count": len(EmailClient._contacts_cache),
        "is_syncing": EmailClient._is_syncing,
        "timestamp": EmailClient._cache_timestamp,
        "ttl": EmailClient._CACHE_TTL,
        "has_pywin32": "win32com" in sys.modules,
        "client_ready": _client_ready.is_set() and _client is not None,
    }

if __name__ == "__main__":
    import uvicorn
    PORT = int(os.getenv("EMAIL_PORT", 8002))
    print(f"[Email Service] (Outlook Magic) rodando na porta {PORT} para {DEFAULT_EMAIL}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
