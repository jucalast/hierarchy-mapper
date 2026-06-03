from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging
import asyncio
import json
import queue
from services.realtime_call import assistant_manager
from core.external.ai_gateway import ask_gemini

log = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws")
async def call_assistant_websocket(websocket: WebSocket):
    await websocket.accept()
    log.info("WebSocket connected for Real-time Call Assistant")
    
    # Start the manager
    success = assistant_manager.start()
    if not success:
        await websocket.send_json({"type": "error", "message": "Failed to initialize audio devices."})
        await websocket.close()
        return

    try:
        while True:
            # Drena a fila inteira o mais rápido possível para não haver latência
            try:
                while True:
                    msg = assistant_manager.transcription_queue.get_nowait()
                    if msg["type"] == "trigger_insight":
                        asyncio.create_task(handle_ai_insight(websocket, msg["history"]))
                    else:
                        await websocket.send_json(msg)
            except queue.Empty:
                pass
                
            # Check for messages from client
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                try:
                    payload = json.loads(data)
                    msg_type = payload.get("type")
                    if msg_type == "STOP":
                        break
                    elif msg_type == "vendedor_transcription":
                        # O frontend gerou a transcrição do mic, o backend apenas arquiva para a IA
                        assistant_manager.add_to_history("Vendedor", payload.get("text", ""))
                except json.JSONDecodeError:
                    if data == "STOP": break
            except (asyncio.TimeoutError, Exception):
                pass
            
    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    finally:
        assistant_manager.stop()
        log.info("Real-time Call Assistant stopped")

async def handle_ai_insight(websocket: WebSocket, history: str):
    prompt = f"""Você é um assistente de vendas B2B observando uma ligação em tempo real.
Trecho recente:
{history}
Forneça UMA dica rápida (1-2 frases)."""
    try:
        ai_response = await ask_gemini(prompt=prompt, json_mode=False)
        await websocket.send_json({"type": "insight", "text": ai_response})
    except Exception as e:
        log.error(f"Error AI Insight: {e}")
