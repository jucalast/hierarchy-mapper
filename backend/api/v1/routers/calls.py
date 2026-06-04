from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import logging
import asyncio
import json
import queue
from typing import Optional
from services.realtime_call import assistant_manager
from core.llm.router import ask_llm
from core.llm.base import LLMTier
from core.infra.database import async_session
from models.conversation.conversation import CallSession, CallMessage
from sqlalchemy import select

log = logging.getLogger(__name__)

router = APIRouter()


async def save_call_message(role: str, text: str, activity_id: str | None, phone: str | None, latency_ms: int | None = None, buffer_secs: float | None = None):
    try:
        async with async_session() as session:
            stmt = select(CallSession).where(
                (CallSession.pipedrive_activity_id == activity_id) if activity_id else (CallSession.phone == phone)
            )
            res = await session.execute(stmt)
            db_session = res.scalar_one_or_none()
            
            if db_session:
                db_msg = CallMessage(
                    call_session_id=db_session.id,
                    role=role,
                    text=text,
                    latency_ms=latency_ms,
                    buffer_secs=int(buffer_secs) if buffer_secs else None
                )
                session.add(db_msg)
                await session.commit()
                log.debug(f"CallMessage persistida: role={role}, text={text[:30]}")
    except Exception as e:
        log.error(f"Erro ao salvar CallMessage: {e}")


async def save_call_insight(insight_data: dict, activity_id: str | None, phone: str | None):
    try:
        async with async_session() as session:
            stmt = select(CallSession).where(
                (CallSession.pipedrive_activity_id == activity_id) if activity_id else (CallSession.phone == phone)
            )
            res = await session.execute(stmt)
            db_session = res.scalar_one_or_none()
            
            if db_session:
                db_session.latest_insight = insight_data
                await session.commit()
                log.debug("CallSession latest_insight atualizada no banco")
    except Exception as e:
        log.error(f"Erro ao atualizar insight de ligação: {e}")


@router.get("/session")
async def get_call_session(
    activity_id: Optional[str] = Query(None),
    phone: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None)
):
    if not activity_id and not phone and not session_id:
        return {"ok": False, "error": "Forneça activity_id, phone ou session_id"}
        
    try:
        async with async_session() as session:
            if session_id:
                stmt = select(CallSession).where(CallSession.id == session_id)
            else:
                stmt = select(CallSession).where(
                    (CallSession.pipedrive_activity_id == activity_id) if activity_id else (CallSession.phone == phone)
                )
            res = await session.execute(stmt)
            db_session = res.scalar_one_or_none()
            
            if not db_session:
                return {"ok": False, "error": "Sessão de ligação não encontrada"}
                
            # Buscar mensagens
            stmt_msg = select(CallMessage).where(CallMessage.call_session_id == db_session.id).order_by(CallMessage.timestamp.asc())
            res_msg = await session.execute(stmt_msg)
            db_messages = res_msg.scalars().all()
            
            messages_list = []
            for m in db_messages:
                messages_list.append({
                    "id": m.id,
                    "type": "transcription",
                    "role": m.role,
                    "text": m.text,
                    "latency_ms": m.latency_ms,
                    "buffer_secs": m.buffer_secs
                })
                
            return {
                "ok": True,
                "id": db_session.id,
                "pipedrive_activity_id": db_session.pipedrive_activity_id,
                "org_id": db_session.org_id,
                "contact_name": db_session.contact_name,
                "phone": db_session.phone,
                "profile_pic": db_session.profile_pic,
                "flight_plan": db_session.flight_plan,
                "latest_insight": db_session.latest_insight,
                "messages": messages_list
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/history")
async def get_call_history():
    try:
        async with async_session() as session:
            stmt = select(CallSession).order_by(CallSession.created_at.desc())
            res = await session.execute(stmt)
            sessions = res.scalars().all()
            
            result = []
            for s in sessions:
                stmt_count = select(CallMessage).where(CallMessage.call_session_id == s.id)
                res_count = await session.execute(stmt_count)
                msg_count = len(res_count.scalars().all())
                
                # Exibe apenas chamadas finalizadas que possuam mensagens gravadas
                if msg_count > 0:
                    result.append({
                        "id": s.id,
                        "pipedrive_activity_id": s.pipedrive_activity_id,
                        "org_id": s.org_id,
                        "contact_name": s.contact_name,
                        "phone": s.phone,
                        "profile_pic": s.profile_pic,
                        "flight_plan": s.flight_plan,
                        "latest_insight": s.latest_insight,
                        "message_count": msg_count,
                        "created_at": s.created_at.isoformat() if s.created_at else None
                    })
            return {"ok": True, "calls": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.websocket("/ws")
async def call_assistant_websocket(websocket: WebSocket):
    await websocket.accept()
    log.info("WebSocket connected for Real-time Call Assistant")
    
    activity_id = websocket.query_params.get("activity_id")
    phone = websocket.query_params.get("phone")
    
    # Start the manager
    success = await assistant_manager.start()
    if not success:
        await websocket.send_json({"type": "error", "message": "Failed to initialize audio devices."})
        await websocket.close()
        return

    # Acumuladores em memória temporários para esta sessão websocket
    session_messages = []
    should_save = False

    try:
        while True:
            # Drena a fila inteira o mais rápido possível para não haver latência
            try:
                while True:
                    msg = assistant_manager.transcription_queue.get_nowait()
                    if msg["type"] == "trigger_insight":
                        asyncio.create_task(handle_ai_insight(websocket, msg["history"], activity_id, phone))
                    else:
                        await websocket.send_json(msg)
                        if msg["type"] == "transcription" and msg.get("role") == "Cliente":
                            session_messages.append({
                                "role": "Cliente",
                                "text": msg.get("text", ""),
                                "latency_ms": msg.get("latency_ms"),
                                "buffer_secs": msg.get("buffer_secs")
                            })
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
                    elif msg_type == "FINALIZE":
                        should_save = True
                        break
                    elif msg_type == "vendedor_transcription":
                        text_content = payload.get("text", "")
                        # O frontend gerou a transcrição do mic, o backend apenas arquiva para a IA
                        assistant_manager.add_to_history("Vendedor", text_content)
                        session_messages.append({
                            "role": "Vendedor",
                            "text": text_content,
                            "latency_ms": None,
                            "buffer_secs": None
                        })
                except json.JSONDecodeError:
                    if data == "STOP":
                        break
                    elif data == "FINALIZE":
                        should_save = True
                        break
            except (asyncio.TimeoutError, Exception):
                pass
            
    except WebSocketDisconnect:
        log.info("WebSocket disconnected")
    finally:
        await assistant_manager.stop(success)
        log.info("Real-time Call Assistant stopped")
        
        # Se a chamada foi encerrada de forma bem-sucedida (FINALIZE), persistimos no banco
        if should_save:
            log.info(f"[calls] Salvando sessao de ligacao finalizada com {len(session_messages)} mensagens no banco de dados.")
            try:
                async with async_session() as session:
                    stmt = select(CallSession).where(
                        (CallSession.pipedrive_activity_id == activity_id) if activity_id else (CallSession.phone == phone)
                    )
                    res = await session.execute(stmt)
                    db_session = res.scalar_one_or_none()
                    
                    if db_session:
                        # Salva mensagens
                        for m in session_messages:
                            db_msg = CallMessage(
                                call_session_id=db_session.id,
                                role=m["role"],
                                text=m["text"],
                                latency_ms=m.get("latency_ms"),
                                buffer_secs=int(m["buffer_secs"]) if m.get("buffer_secs") else None
                            )
                            session.add(db_msg)
                        
                        # Salva último insight do copiloto associado à conexão
                        latest_ins = getattr(websocket, "latest_insight", None)
                        if latest_ins:
                            db_session.latest_insight = latest_ins
                        
                        await session.commit()
                        log.info("[calls] Sessao de ligacao salva com sucesso no banco SQLite.")
            except Exception as e:
                log.error(f"[calls] Erro ao persistir ligacao no banco de dados: {e}")


async def handle_ai_insight(websocket: WebSocket, history: str, activity_id: str | None, phone: str | None):
    from modules.ai.service.context.business_context_service import BusinessContextService
    
    plan_text = "Nenhum plano de voo ativo."
    if assistant_manager.active_coaching_plan:
        plan_text = json.dumps(assistant_manager.active_coaching_plan, ensure_ascii=False, indent=2)

    # Busca contexto dinâmico da empresa
    ctx = await BusinessContextService.get_tenant_context()
    company_name = ctx.get("company_name", "a Empresa")
    seller_name = ctx.get("seller_name", "o Vendedor")

    prompt = f"""Você é um Copiloto de Vendas B2B da {company_name} acompanhando uma ligação em tempo real.
Seu objetivo é ajudar o vendedor ({seller_name}) a seguir o plano de voo de alta performance e converter a visita presencial.

DIRETRIZES DE COACHING:
1. Tonalidade: Recomende um tom de voz calmo, de consultor especialista, não de vendedor insistente.
2. Silêncio: Após perguntas de Implicação, sugira que o vendedor faça silêncio para deixar o prospect falar.
3. Objeção "Já tenho fornecedor": Instrua a responder que o objetivo não é trocar o fornecedor, mas ser uma segunda opção homologada para emergências.
4. Foco: O objetivo final é sempre o agendamento da visita técnica presencial.

PLANO DE VOO ATIVO:
{plan_text}

TRANSCRIÇÃO RECENTE:
{history}

Analise a transcrição e retorne EXATAMENTE um JSON:
- "current_step": Passo atual (ABERTURA, SITUAÇÃO + PROBLEMA, IMPLICAÇÃO, NECESSIDADE, FECHAMENTO).
- "suggestion": Sugestão curta, direta e "matadora" para o momento.
- "objection_detected": true/false.
- "objection_handling": Como contornar de forma elegante se detectado.

Seja cirúrgico. Ajude o vendedor a manter o controle da conversa.
"""
    try:
        res = await ask_llm(
            prompt=prompt, 
            system="Retorne apenas JSON estruturado válido.", 
            json_mode=True, 
            tier=LLMTier.STANDARD
        )
        data = res.json_data or {}
        
        # Salva o insight no objeto do websocket para persistência futura
        websocket.latest_insight = data
        
        await websocket.send_json({
            "type": "live_coaching", 
            "data": data
        })
    except Exception as e:
        log.error(f"Error AI Insight: {e}")
