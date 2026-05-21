from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import sqlite3
import time
import uuid
import asyncio
from sqlalchemy.future import select
from sqlalchemy import func
from core.infra.database import async_session
from models.people.employee import Employee
from .service.email import EmailClient

_cache_status: dict = {}
_CACHE_TTL_SEC = 30

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
    attachment_paths: Optional[List[str]] = None


@router.post("/send")
async def send_email(payload: SendEmailRequest):
    tracking_id = str(uuid.uuid4())
    conn = _get_db()
    conn.execute("INSERT INTO emails_sent (tracking_id, to_email, subject) VALUES (?, ?, ?)",
                 (tracking_id, payload.to_email, payload.subject))
    conn.commit()
    conn.close()

    client = EmailClient()
    loop = asyncio.get_event_loop()
    success = await loop.run_in_executor(
        None,
        lambda: client.send_outbound_email(
            payload.to_email, payload.subject, payload.body, tracking_id,
            False, payload.attachment_paths,
        )
    )
    if success:
        return {"status": "success", "tracking_id": tracking_id, "message": "Email enfileirado/enviado com sucesso!"}
    return {"status": "error", "message": "Falha ao enviar email."}


@router.get("/metrics")
async def get_metrics():
    conn = _get_db()
    cur = conn.execute("SELECT tracking_id, to_email, subject, timestamp FROM emails_sent ORDER BY timestamp DESC LIMIT 50")
    sent = [{"tracking_id": row[0], "to": row[1], "subject": row[2], "date": row[3]} for row in cur.fetchall()]
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
    ip = request.client.host
    user_agent = request.headers.get("user-agent", "Unknown")
    conn = _get_db()
    conn.execute("INSERT INTO opens (tracking_id, ip) VALUES (?, ?)", (id, f"{ip} | {user_agent}"))
    conn.commit()
    conn.close()

    pixel_path = os.path.join(os.path.dirname(__file__), "pixel.gif")
    if not os.path.exists(pixel_path):
        with open(pixel_path, "wb") as f:
            f.write(b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')
    return FileResponse(pixel_path, media_type="image/gif")


@router.get("/email/cache-status")
async def get_email_cache_status():
    cache_key = "email_cache_status"
    entry = _cache_status.get(cache_key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL_SEC:
        return entry["data"]
    try:
        async with async_session() as session:
            stmt = select(func.count()).select_from(Employee).where(Employee.source == "outlook")
            res = await session.execute(stmt)
            result = {"is_syncing": False, "count": res.scalar() or 0}
    except Exception as e:
        result = {"is_syncing": False, "count": 0, "error": str(e)}
    _cache_status[cache_key] = {"data": result, "ts": time.time()}
    return result


@router.get("/whatsapp/cache-status")
async def get_whatsapp_cache_status():
    cache_key = "whatsapp_cache_status"
    entry = _cache_status.get(cache_key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL_SEC:
        return entry["data"]
    try:
        async with async_session() as session:
            stmt = select(func.count()).select_from(Employee).where(Employee.source == "whatsapp")
            res = await session.execute(stmt)
            result = {"is_syncing": False, "count": res.scalar() or 0}
    except Exception as e:
        result = {"is_syncing": False, "count": 0, "error": str(e)}
    _cache_status[cache_key] = {"data": result, "ts": time.time()}
    return result
