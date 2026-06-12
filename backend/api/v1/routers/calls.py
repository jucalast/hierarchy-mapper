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

# ── Caches de sessão para reduzir latência do coaching em tempo real ──
_cached_static_prompt: str | None = None
_cached_ctx: dict | None = None
_insight_generation = 0  # Contador incremental para descartar insights obsoletos
_insight_lock = asyncio.Lock()


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
        from models.organization import Organization
        async with async_session() as session:
            stmt = select(CallSession, Organization.logo_url, Organization.domain).outerjoin(
                Organization, CallSession.org_id == Organization.id
            ).order_by(CallSession.created_at.desc())
            res = await session.execute(stmt)
            rows = res.all()
            
            result = []
            for s, org_logo, org_domain in rows:
                stmt_count = select(CallMessage).where(CallMessage.call_session_id == s.id)
                res_count = await session.execute(stmt_count)
                msg_count = len(res_count.scalars().all())
                
                # Exibe apenas chamadas finalizadas que possuam mensagens gravadas
                if msg_count > 0:
                    result.append({
                        "id": s.id,
                        "pipedrive_activity_id": s.pipedrive_activity_id,
                        "org_id": s.org_id,
                        "org_logo": org_logo,
                        "org_domain": org_domain,
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
        log.error(f"Error fetching call history: {e}")
        return {"ok": False, "error": str(e)}


@router.websocket("/ws")
async def call_assistant_websocket(websocket: WebSocket):
    await websocket.accept()
    log.info("WebSocket connected for Real-time Call Assistant")
    
    # Limpa cache de prompt estático da sessão anterior
    invalidate_coaching_cache()
    
    activity_id = websocket.query_params.get("activity_id")
    phone = websocket.query_params.get("phone")
    
    # Start the manager
    success = await assistant_manager.start()
    if not success:
        await websocket.send_json({"type": "error", "message": "Failed to initialize audio devices."})
        await websocket.close()
        return

    # Sincronizar plano de voo e histórico a partir do SQLite
    try:
        async with async_session() as session:
            stmt = select(CallSession).where(
                (CallSession.pipedrive_activity_id == activity_id) if activity_id else (CallSession.phone == phone)
            )
            res = await session.execute(stmt)
            db_session = res.scalar_one_or_none()
            org_id = db_session.org_id if db_session else None
            
            mapped_contacts_str = "Nenhum contato mapeado."
            if org_id:
                try:
                    from models import Employee
                    stmt_emps = select(Employee).where(Employee.company_id == org_id)
                    res_emps = await session.execute(stmt_emps)
                    emps = res_emps.scalars().all()
                    if emps:
                        mapped_contacts_str = ", ".join([f"{e.name}" for e in emps if e.name])
                except Exception as e:
                    log.error(f"Erro ao buscar contatos mapeados para o org_id {org_id}: {e}")

            if db_session:
                if db_session.latest_insight and "updated_steps" in db_session.latest_insight:
                    fp = dict(db_session.flight_plan) if db_session.flight_plan else {}
                    fp["steps"] = db_session.latest_insight["updated_steps"]
                    assistant_manager.set_active_coaching_plan(fp)
                elif db_session.flight_plan:
                    assistant_manager.set_active_coaching_plan(db_session.flight_plan)
                
                # Se for reconexão, carregar histórico de mensagens anteriores para a IA
                stmt_msg = select(CallMessage).where(CallMessage.call_session_id == db_session.id).order_by(CallMessage.timestamp.asc())
                res_msg = await session.execute(stmt_msg)
                db_messages = res_msg.scalars().all()
                if db_messages:
                    assistant_manager.context_history = [
                        f"{m.role}: {m.text}" for m in db_messages
                    ][-20:]
    except Exception as e:
        log.error(f"Erro ao carregar detalhes da CallSession para o WebSocket: {e}")

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
                        asyncio.create_task(handle_ai_insight(websocket, msg["history"], activity_id, phone, mapped_contacts_str))
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
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                raise
            except Exception as e:
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
                            if "updated_steps" in latest_ins:
                                fp = dict(db_session.flight_plan) if db_session.flight_plan else {}
                                fp["steps"] = latest_ins["updated_steps"]
                                db_session.flight_plan = fp
                        
                        await session.commit()
                        log.info("[calls] Sessao de ligacao salva com sucesso no banco SQLite.")
            except Exception as e:
                log.error(f"[calls] Erro ao persistir ligacao no banco de dados: {e}")


async def _get_static_prompt() -> tuple[str, str, str]:
    """Retorna (static_prompt_template, seller_name, company_name) com cache por sessão."""
    global _cached_static_prompt, _cached_ctx
    
    if _cached_static_prompt and _cached_ctx:
        return _cached_static_prompt, _cached_ctx.get('seller_name', 'Vendedor'), _cached_ctx.get('company_name', 'Empresa')
    
    from modules.agent.skills.skill_call import CallSkill
    from modules.ai.service.context.business_context_service import BusinessContextService
    
    ctx = await BusinessContextService.get_tenant_context()
    _cached_ctx = ctx
    seller_name = ctx.get('seller_name', 'Vendedor')
    company_name = ctx.get('company_name', 'Empresa')
    differentials = ", ".join(ctx.get("company_differentials", []))
    products_info = []
    for p_key, p_data in ctx.get("products", {}).items():
        products_info.append(f"- {p_data.get('name')}: {p_data.get('description')}")
    products_str = "\n".join(products_info)
    reference_clients = ", ".join([c.get("name", "") for c in ctx.get("reference_clients", [])])

    _cached_static_prompt = f"""Você é o Copiloto de Vendas da {company_name}, analisando uma ligação B2B em tempo real.
Seu objetivo é guiar o vendedor ({seller_name}) pelas etapas do plano de voo, detectar objeções do cliente imediatamente, fornecer contornos assertivos, rápidos e ADAPTAR dinamicamente o plano de voo ao linguajar e revelações do cliente.

CONTEXTO DA EMPRESA E VENDEDOR (Use isso para persuadir e gerar autoridade):
- Vendedor: {seller_name}
- Empresa: {company_name}
- Nossos Diferenciais: {differentials}
- Clientes de Referência: {reference_clients}
- Nossos Produtos:
{products_str}

DIRETRIZES DE VENDAS E CONTORNO DE OBJEÇÕES:
{CallSkill.SPIN_SELLING_RULES}
{CallSkill.OBJECTION_HANDLING_RULES}

INSTRUÇÕES DE ANÁLISE E ADAPTAÇÃO:
1. **MODO SCRIPT COMPLETO (Teleprompter)**: O vendedor precisa do roteiro exato e literal para ler na tela. 
   - A sua resposta em "content" das Etapas Relâmpago ou do plano DEVE ser o bloco de texto completo, conversacional e humano.
   - NÃO use dicas curtas em "content". Escreva a frase exata que o vendedor deve falar em primeira pessoa.
   - Exemplo de Contorno: "[⚡ TÁTICA: 20 SEGS] Entendo perfeitamente que a correria é grande. Prometo não tomar seu tempo. Em 20 segundos: vocês têm sofrido com avarias nas embalagens ultimamente?"
2. **DETECÇÃO DE BRUSH-OFF / OBJEÇÃO**: Analise a ÚLTIMA fala do cliente. Se ela contiver "me manda por e-mail", "agora não posso", "já temos fornecedor", etc. marque "objection_detected" como true.
   - ATENÇÃO: Na indústria B2B, pedir e-mail é um *brush-off* (tentativa de desligar). Trate como objeção grave, não como avanço de etapa.
3. **CONTORNO DE OBJEÇÃO (OBRIGATÓRIO se objection_detected = true)**:
   - INJETE uma Etapa Relâmpago com label "⚡ Contorno" contendo o texto tático curto.
   - NÃO avance o funil SPIN (SITUAÇÃO/PROBLEMA) se a objeção/brush-off não foi superada.
4. Em "suggestion", forneça apenas dicas COMPORTAMENTAIS muito curtas (ex: "Fale devagar", "Ele está fugindo, mude o ângulo").
5. **FLEXIBILIDADE DE FUNIL (Recuo Estratégico)**: Não seja um robô do SPIN. Se o cliente minimizar a dor (ex: "temos problemas isolados, mas resolvemos"), NÃO empurre perguntas de [IMPLICAÇÃO] complexas sobre "custo e retrabalho". Isso afasta o cliente frio. Em vez disso, recue para curiosidade rápida em [QUALIFICAÇÃO]: "[RECUO] Entendi. E quando acontece, como vocês resolvem?".
6. **ADAPTAÇÃO DO PLANO DE VOO (updated_steps)**: Retorne no array `updated_steps` APENAS as etapas que sofreram alteração (para economizar tokens e acelerar a resposta). O backend cuidará de mesclar com o plano atual.
   - **ETAPAS RELÂMPAGO (Lightning Steps)**: Injetadas em caso de brush-off, objeção ou dúvida complexa. Retorne a Etapa Relâmpago no array `updated_steps`. O backend se encarregará de fazer o "append" no histórico da tela.
   - **REGRA DE TRANSFERÊNCIA / GATEKEEPER**: Se a telefonista/recepcionista confirmar que vai transferir a ligação (ex: "um momento, vou transferir", "só um instante", "vou passar"), você DEVE obrigatoriamente marcar `[TRANSFER_DETECTED=true]`. Após a transferência, mesmo que a pessoa se identifique, sua PRIMEIRA Etapa Relâmpago DEVE ser Qualificar o Alvo (ex: "[⚡ TÁTICA: QUALIFICAR] Oi Luciana, é você que cuida da área de embalagens?").
   - **INTELIGÊNCIA DE CONTATOS**: Se a telefonista disser "Vou passar pro Fernando" ou "É com o Fernando", cruze esse nome com os "CONTATOS MAPEADOS DA EMPRESA" (fornecidos abaixo no prompt). Se ele existir lá, diga: "[⚡ TÁTICA: PEDIR TRANSFERÊNCIA] Ah, o Fernando é o Gerente! Consegue me transferir pra ele?".
   - **PROGRESSÃO / SHORT-CIRCUIT**: Se o objetivo foi alcançado (agendou visita), PULE para "FECHAMENTO".
   - Etapas muito distantes continuam "Pendente...".

ATENÇÃO — REGRA CRÍTICA DE MEMÓRIA E DESISTÊNCIA:
Antes de responder, leia minuciosamente o HISTÓRICO. Se o vendedor já usou uma tática (ex: "Só 20 segundos") e o cliente respondeu negando novamente, É PROIBIDO gerar a mesma tática de novo. Se o cliente rejeitar o avanço 3 vezes seguidas, pare de forçar o funil e injete uma Etapa Relâmpago com [TÁTICA: DESLIGAMENTO EDUCADO]. 
**EXCEÇÃO DE OURO (DOR GRAVE)**: Se em QUALQUER momento o cliente revelar uma dor grave (ex: "perdemos 2 dias de produção", "temos muita avaria", "tá custando caro"), **IGNORE TOTALMENTE** a regra de desligamento e o brush-off. Ancore imediatamente na dor para fisgar a reunião: "[⚡ TÁTICA: ANCORAR NA DOR] Luciana, 2 dias perdidos é muito dinheiro no ralo. Posso te mostrar em 5 min como a Toyota zerou isso com a gente?". NUNCA desista se houver dor exposta!
"""
    return _cached_static_prompt, seller_name, company_name


def invalidate_coaching_cache():
    """Chamado ao iniciar nova sessão para limpar o cache."""
    global _cached_static_prompt, _cached_ctx, _insight_generation, _pending_insight_request
    _cached_static_prompt = None
    _cached_ctx = None
    _insight_generation = 0
    _pending_insight_request = None


# Slot para guardar o pedido de insight mais recente (nunca é descartado silenciosamente)
_pending_insight_request: dict | None = None


async def handle_ai_insight(websocket: WebSocket, history: str, activity_id: str | None, phone: str | None, mapped_contacts_str: str = "Nenhum contato mapeado."):
    global _pending_insight_request
    
    # Armazena este pedido como o mais recente
    request_id = id(history)
    _pending_insight_request = {"id": request_id, "history": history, "websocket": websocket, "activity_id": activity_id, "phone": phone}
    
    # Debounce mínimo: apenas 0.05s (frontend já deve garantir eventos corretos)
    await asyncio.sleep(0.05)
    
    # Se o pedido mais recente não for este, abortamos silenciosamente (debounce)
    if _pending_insight_request.get("id") != request_id:
        return
    
    # Se já há um insight em andamento, não duplicamos — o processador atual
    # vai pegar o _pending_insight_request quando terminar
    if _insight_lock.locked():
        log.debug("[coaching] Insight enfileirado (slot pendente) — já há um em andamento")
        return

    async with _insight_lock:
        # Loop: processa o pedido pendente mais recente até não haver mais nenhum
        while _pending_insight_request is not None:
            req = _pending_insight_request
            _pending_insight_request = None  # Consome o slot
            
            ws = req["websocket"]
            hist = req["history"]
            
            static_prompt, seller_name, company_name = await _get_static_prompt()
            
            plan_text = "Nenhum plano de voo ativo."
            if assistant_manager.active_coaching_plan:
                plan_text = json.dumps(assistant_manager.active_coaching_plan, ensure_ascii=False, indent=2)

            prompt = f"""{static_prompt}

PLANO DE VOO DA LIGAÇÃO (ATUAL):
{plan_text}

CONTATOS MAPEADOS DA EMPRESA:
{mapped_contacts_str}

HISTÓRICO RECENTE DA CONVERSA:
{hist}

VOCÊ É UM ASSISTENTE DE STREAMING. SÓ GERE O TEXTO DA PRÓXIMA ETAPA E NADA MAIS.
Retorne a sua resposta no seguinte formato EXATO E OBRIGATÓRIO:

[TRANSFER_DETECTED=true|false]
[OBJECTION_DETECTED=true|false]
[LABEL=NOME EXATO DA ETAPA OU ⚡ CONTORNO]
---
Aqui entra o texto falado que o vendedor vai ler, e NADA MAIS.
"""
            try:
                import time as _time
                from core.llm.router import get_router
                from core.llm.base import LLMMessage
                
                msgs = [
                    LLMMessage(role="system", content="Você é um copiloto de vendas ao vivo. Você DEVE usar o formato de tags exato solicitado."),
                    LLMMessage(role="user", content=prompt)
                ]
                
                router = get_router()
                _t0 = _time.monotonic()
                
                # Envia aviso de inicio de stream para o FrontEnd limpar o texto do card
                await ws.send_json({
                    "type": "insight_stream_start"
                })
                
                full_text = ""
                is_body = False
                metadata = {}
                
                async for chunk in router.stream_complete(
                    messages=msgs,
                    temperature=0.3,
                    tier=LLMTier.FAST,
                    preferred_model="gemini-2.5-flash",
                    bypass_throttle=True
                ):
                    full_text += chunk
                    
                    if not is_body:
                        if "\n---\n" in full_text or "\n---" in full_text:
                            is_body = True
                            # Extrai os metadados
                            header = full_text.split("---")[0]
                            if "[TRANSFER_DETECTED=TRUE]" in header.upper():
                                metadata["transfer_detected"] = True
                            if "[OBJECTION_DETECTED=TRUE]" in header.upper():
                                metadata["objection_detected"] = True
                            
                            import re
                            label_match = re.search(r"\[LABEL=(.*?)\]", header, re.IGNORECASE)
                            metadata["label"] = label_match.group(1).strip() if label_match else "⚡ Sugestão"
                            
                            # Pega o que já foi gerado do corpo e envia
                            body_chunk = full_text.split("---", 1)[1].lstrip()
                            if body_chunk:
                                await ws.send_json({
                                    "type": "insight_chunk",
                                    "chunk": body_chunk,
                                    "label": metadata["label"]
                                })
                    else:
                        # Stream do corpo
                        await ws.send_json({
                            "type": "insight_chunk",
                            "chunk": chunk,
                            "label": metadata.get("label", "⚡ Sugestão")
                        })
                
                # Finaliza stream e atualiza memória do plano
                await ws.send_json({
                    "type": "insight_stream_end"
                })
                
                _elapsed = int((_time.monotonic() - _t0) * 1000)
                log.info(f"[coaching] LLM Stream concluído em {_elapsed}ms")
                
                # Montamos o objeto como era antes para salvar na memória
                body_text = full_text.split("---", 1)[1].strip() if "---" in full_text else full_text.strip()
                label = metadata.get("label", "⚡ Sugestão")
                is_lightning = "⚡" in label or metadata.get("objection_detected", False)
                
                new_step = {
                    "label": label,
                    "content": body_text,
                    "is_lightning": is_lightning
                }
                
                current_steps = []
                if isinstance(assistant_manager.active_coaching_plan, dict) and "steps" in assistant_manager.active_coaching_plan:
                    current_steps = list(assistant_manager.active_coaching_plan["steps"])
                
                if is_lightning:
                    # Insere o card relâmpago na posição cronológica (antes da primeira etapa Pendente)
                    insert_idx = len(current_steps)
                    for idx, s in enumerate(current_steps):
                        content_lower = str(s.get("content", "")).lower()
                        if "pendente" in content_lower or not content_lower.strip():
                            insert_idx = idx
                            break
                    current_steps.insert(insert_idx, new_step)
                else:
                    found = False
                    for idx, old_step in enumerate(current_steps):
                        if old_step.get("label") == label:
                            current_steps[idx] = {**old_step, **new_step}
                            found = True
                            break
                    if not found:
                        current_steps.append(new_step)
                        
                if isinstance(assistant_manager.active_coaching_plan, dict):
                    assistant_manager.active_coaching_plan["steps"] = current_steps
                else:
                    assistant_manager.active_coaching_plan = {"steps": current_steps}
                    
                insight_data = {
                    "transfer_detected": metadata.get("transfer_detected", False),
                    "objection_handling": body_text if is_lightning else "",
                    "suggestion": "",
                    "current_step": label if not is_lightning else "",
                    "updated_steps": current_steps
                }
                
                # Dispara o evento final consolidado para o front-end
                await ws.send_json({
                    "type": "live_coaching",
                    "data": insight_data
                })
                    
                # Se for transfer, dispara evento
                if metadata.get("transfer_detected"):
                    await ws.send_json({
                        "type": "detected_contact",
                        "data": {
                            "name": "Contato Identificado",
                            "isTransferred": True
                        }
                    })
                    
                # Salva o insight no banco de dados para persistência global
                asyncio.create_task(save_call_insight(insight_data, activity_id, phone))

            except Exception as e:
                from starlette.websockets import WebSocketDisconnect
                if isinstance(e, (RuntimeError, WebSocketDisconnect)) or "websocket" in str(e).lower():
                    log.info("[coaching] WebSocket fechado ou desconectado durante stream. Abortando envio de insight.")
                    return
                log.exception("[coaching] Erro ao gerar/streamar insight via LLM")
                try:
                    await ws.send_json({"type": "error", "message": f"Erro interno do Coach: {str(e)}"})
                except Exception:
                    pass

