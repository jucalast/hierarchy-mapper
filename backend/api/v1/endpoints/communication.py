from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import sqlite3
import uuid
import asyncio

from services.communication.email_client import EmailClient

router = APIRouter()

def _get_db():
    conn = sqlite3.connect("leads_tracking.db")
    conn.execute('''CREATE TABLE IF NOT EXISTS opens 
                    (id INTEGER PRIMARY KEY, tracking_id TEXT, ip TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS emails_sent 
                    (id INTEGER PRIMARY KEY, tracking_id TEXT, to_email TEXT, subject TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    return conn

class SendEmailRequest(BaseModel):
    to_email: str
    subject: str
    body: str

@router.post("/send")
async def send_email(payload: SendEmailRequest):
    tracking_id = str(uuid.uuid4())
    
    # Salvar no DB para cruzar depois
    conn = _get_db()
    conn.execute("INSERT INTO emails_sent (tracking_id, to_email, subject) VALUES (?, ?, ?)", 
                 (tracking_id, payload.to_email, payload.subject))
    conn.commit()
    conn.close()

    client = EmailClient()
    # Enviando numa thread em background para não bloquear o servidor (time.sleep do envio falso humano)
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(
        None, 
        client.send_outbound_email, 
        payload.to_email, 
        payload.subject, 
        payload.body, 
        tracking_id
    )

    if success:
        return {"status": "success", "tracking_id": tracking_id, "message": "Email enfileirado/enviado com sucesso!"}
    else:
        return {"status": "error", "message": "Falha ao enviar email."}

@router.get("/metrics")
async def get_metrics():
    conn = _get_db()
    # Buscar os últimos emails enviados
    cur = conn.execute("SELECT tracking_id, to_email, subject, timestamp FROM emails_sent ORDER BY timestamp DESC LIMIT 50")
    sent = [{"tracking_id": row[0], "to": row[1], "subject": row[2], "date": row[3]} for row in cur.fetchall()]
    
    # Buscar aberturas e cruzar
    results = []
    for s in sent:
        cur_opens = conn.execute("SELECT ip, timestamp FROM opens WHERE tracking_id = ? ORDER BY timestamp DESC", (s["tracking_id"],))
        opens = [{"ip_agent": r[0], "date": r[1]} for r in cur_opens.fetchall()]
        s["opens"] = opens
        s["open_count"] = len(opens)
        results.append(s)

    conn.close()
    return {"data": results}

@router.get("/track")
async def track_email_open(id: str, request: Request):
    """
    Registra a abertura do e-mail.
    Cuidado com falsos positivos: o ideal é registrar cada hit e tratar
    depois quantas vezes o mesmo IP/UserAgent acessou.
    """
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "Unknown")
    
    # Gravando a abertura (pode usar o Postgres do MVP ou esse SQLite embutido para métricas rápidas)
    conn = _get_db()
    conn.execute("INSERT INTO opens (tracking_id, ip) VALUES (?, ?)", (id, f"{ip} | {user_agent}"))
    conn.commit()
    conn.close()

    # Retorna um pixel transparente (1x1 GIF)
    pixel_path = os.path.join(os.path.dirname(__file__), "pixel.gif")
    if not os.path.exists(pixel_path):
        with open(pixel_path, "wb") as f:
            f.write(b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')
            
    return FileResponse(pixel_path, media_type="image/gif")
