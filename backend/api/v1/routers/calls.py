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
            stmt = select(CallSession, Organization.logo, Organization.domain).outerjoin(
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
1. Identifique em qual etapa do plano de voo a conversa está. O valor do campo "current_step" DEVE corresponder EXATAMENTE ao nome (ou label) de uma das etapas presentes no plano de voo (ex: "ABERTURA", "SITUAÇÃO + PROBLEMA", "IMPLICAÇÃO", "QUALIFICAÇÃO", "NECESSIDADE", "FECHAMENTO", ou uma "Etapa Relâmpago" previamente criada). Se não houver correspondência clara, use o nome mais próximo possível dentre os definidos no plano de voo.
2. **USO DE CONTEXTO**: Ao redigir as falas do vendedor (em Etapas Relâmpago ou na Próxima Etapa), use sutilmente os diferenciais, produtos e clientes de referência acima. Ex: se ele tem objeção de confiança, cite um cliente; se ele tem problema de qualidade, conecte com o nosso produto. Construa um "pitch" inteligente e persuasivo.
3. **DETECÇÃO DE OBJEÇÃO (CRÍTICO)**: Analise a ÚLTIMA fala do cliente. Se ela contiver QUALQUER variação das frases abaixo, você DEVE marcar "objection_detected" como true:
   - "não é um bom momento" / "agora não posso" / "me liga depois" / "estou ocupado"
   - "me manda por e-mail" / "me envia um material" / "manda uma proposta"
   - "já temos fornecedor" / "já estamos atendidos" / "estamos satisfeitos"
   - "não tenho interesse" / "não tenho necessidade" / "no momento não preciso"
   - "não conheço vocês" / "está caro" / "não temos orçamento"
   ATENÇÃO: Citar dores próprias (ex: "temos avarias", "temos custos altos") NÃO é objeção — é sinal de compra. Objeção é RESISTÊNCIA a continuar a conversa.
4. **CONTORNO DE OBJEÇÃO (OBRIGATÓRIO se objection_detected = true)**:
   - Preencha "objection_handling" com o script de contorno COMPLETO, pronto para o vendedor ler (2-3 frases, NÃO apenas 15 palavras).
   - INJETE uma Etapa Relâmpago com label "⚡ Contorno de Objeção" contendo o mesmo script. Essa etapa deve ser posicionada ANTES da próxima etapa SPIN nos updated_steps.
   - NÃO avance o funil SPIN enquanto a objeção não for contornada. Se o cliente disse "me liga depois", a próxima etapa NÃO é SITUAÇÃO + PROBLEMA — é o contorno.
   - **REGRA DE OURO**: Consulte as REGRAS DE CONTORNO DE OBJEÇÃO acima para montar o script de contorno adequado ao tipo de objeção detectada.
5. Em "suggestion", forneça apenas dicas COMPORTAMENTAIS muito curtas (ex: "Fale mais devagar", "Deixe ele terminar de falar"). Dicas de roteiro NÃO devem vir aqui.
6. **TRANSFERÊNCIA AUTOMÁTICA**: Detecte se a conversa indica que a recepção/PABX transferiu a ligação para o alvo. Se sim, defina "transfer_detected" como true.
7. **ADAPTAÇÃO DO PLANO DE VOO (updated_steps)**: Você deve retornar todas as etapas do plano de voo sob a chave "updated_steps", com as seguintes regras:
   - **ETAPAS RELÂMPAGO (Lightning Steps)**: INJETE uma Etapa Relâmpago se o cliente resistiu, levantou objeção, ou desviou do assunto exigindo uma parada estratégica.
   - **REGRA DE TRANSFERÊNCIA (PABX para ALVO)**: Quando transferido, analise quem atendeu:
     A) Se NÃO disser o nome, crie Relâmpago "Confirmar Alvo" para perguntar: "Alô, falo com o(a) [Nome]?".
     B) Se disser NOME DIFERENTE do alvo (Gatekeeper), crie Relâmpago "Qualificar Interlocutor": "Oi (nome), boa tarde. Meu nome é {seller_name} da {company_name}... Gostaria de saber quem seria a pessoa certa...".
     C) **EXTRAÇÃO DE CONTATO DIRETO**: Se revelarem quem é o decisor, seu ÚNICO objetivo é pedir ramal/e-mail/WhatsApp direto dessa pessoa. Crie Relâmpago para isso. NUNCA tente agendar "através" do gatekeeper.
     D) Se for o Alvo, crie Relâmpago "Reintrodução e Hook".
   - **PROIBIÇÃO DE REDUNDÂNCIA (EFEITO PAPAGAIO)**: NUNCA crie uma Etapa Relâmpago se o conteúdo dela for similar ao roteiro que você está gerando para a PRÓXIMA ETAPA lógica do S.P.I.N. Escolha apenas UM bloco para colocar o roteiro! Se a próxima etapa já resolve (ex: Necessidade), preencha apenas a Necessidade. Se você gerar dois blocos dizendo a mesma coisa, o vendedor lerá duplicado e perderá a venda.
   - REGRA CRÍTICA: NUNCA crie uma Etapa Relâmpago se a última pessoa a falar no histórico foi o "Vendedor". As Etapas Relâmpago são exclusivas para reagir à última fala do CLIENTE.
   - **PROGRESSÃO DO FUNIL (CRUCIAL)**: Se o cliente respondeu bem (ex: confirmou os custos/problemas na Implicação), PULE IMEDIATAMENTE para a PRÓXIMA etapa (Necessidade) substituindo "Pendente..." pelo roteiro exato. O funil não pode parar.
   - **ATALHO DE SUCESSO (SHORT-CIRCUIT)**: Se o objetivo foi alcançado (agendou reunião ou pegou contato do decisor), PULE imediatamente para "FECHAMENTO". Preencha as do meio com "Não se aplica".
   - **BREVIDADE EXTREMA**: Gere roteiros de no máximo 1 a 2 frases curtas. O objetivo é dar a INTENÇÃO da fala para o vendedor, não um monólogo longo.
   - **UMA PERGUNTA POR VEZ**: NUNCA faça múltiplas perguntas ("metralhadora") na mesma fala. Escolha a pergunta mais importante.
   - **NATURALIDADE**: Mantenha um tom coloquial, de conversa B2B ágil (bate-bola). Evite "ler panfleto" ou despejar jargões técnicos antes do cliente aprofundar a dor.
   - O texto deve estar pronto para o vendedor ler. Você já sabe que o nome do vendedor é {seller_name} e a empresa é {company_name}. Nunca use colchetes/chaves.
   - Etapas muito distantes continuam "Pendente...".
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


async def handle_ai_insight(websocket: WebSocket, history: str, activity_id: str | None, phone: str | None):
    global _pending_insight_request
    
    # Armazena este pedido como o mais recente
    _pending_insight_request = {
        "websocket": websocket,
        "history": history,
        "activity_id": activity_id,
        "phone": phone,
    }
    
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

HISTÓRICO RECENTE DA CONVERSA:
{hist}

Retorne estritamente um JSON com a seguinte estrutura:
{{
  "current_step": "Nome exato da etapa do plano de voo",
  "suggestion": "Dica comportamental rápida ou string vazia",
  "objection_detected": true ou false,
  "objection_handling": "Frase de contorno se houver objeção, senão string vazia",
  "transfer_detected": true ou false,
  "updated_steps": [
    {{
      "label": "Nome da Etapa",
      "content": "Roteiro adaptado com base no diálogo",
      "is_lightning": false
    }}
  ]
}}
"""
            try:
                import time as _time
                _t0 = _time.monotonic()
                res = await ask_llm(
                    prompt=prompt, 
                    system="Você é um assistente de vendas em tempo real. Respostas ultra-curtas em JSON.", 
                    json_mode=True, 
                    tier=LLMTier.FAST,
                    preferred_model="gemini-2.5-flash",
                    bypass_throttle=True
                )
                _elapsed = int((_time.monotonic() - _t0) * 1000)
                log.info(f"[coaching] LLM insight concluído em {_elapsed}ms")
                
                # Se chegou um pedido MAIS RECENTE durante a chamada LLM,
                # descarta este resultado e processa o novo no próximo loop
                if _pending_insight_request is not None:
                    log.info(f"[coaching] Insight obsoleto após LLM (há pedido mais recente), descartando resultado")
                    continue
                
                data = res.json_data or {}
                
                # Se houver passos atualizados, atualizamos o plano em memória
                if data and "updated_steps" in data and isinstance(data["updated_steps"], list) and len(data["updated_steps"]) > 0:
                    if isinstance(assistant_manager.active_coaching_plan, dict):
                        assistant_manager.active_coaching_plan["steps"] = data["updated_steps"]
                    else:
                        assistant_manager.active_coaching_plan = {"steps": data["updated_steps"]}
                
                # Salva o insight no objeto do websocket para persistência futura
                ws.latest_insight = data
                
                await ws.send_json({
                    "type": "live_coaching", 
                    "data": data
                })
            except Exception as e:
                log.error(f"Error AI Insight: {e}")

