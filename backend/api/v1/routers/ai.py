"""
Endpoint /ai — thin router. Orquestração via agent_v2.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.infra.database import get_db
from core.observability.logging_config import get_logger

router = APIRouter()
log = get_logger(__name__)


class RefineMessageRequest(PydanticBaseModel):
    action_id: str
    feedback: str


class PreferenceRequest(PydanticBaseModel):
    model: str
    strict_mode: Optional[bool] = False


@router.post("/preference")
async def update_ai_preference(payload: PreferenceRequest):
    """Atualiza o modelo de IA preferido globalmente."""
    from core.llm.router import set_preferred_model
    set_preferred_model(payload.model, strict_mode=payload.strict_mode or False)
    return {"status": "ok", "preferred_model": payload.model, "strict_mode": payload.strict_mode or False}


@router.get("/preference")
async def get_ai_preference():
    """Retorna o modelo de IA preferido atualmente."""
    from core.llm.router import get_preferred_model, get_strict_mode_preference
    return {"preferred_model": get_preferred_model(), "strict_mode": get_strict_mode_preference()}


@router.get("/quotas")
async def get_live_quotas():
    """Retorna os limites de cota em tempo real (0-100%) para todos os provedores."""
    from core.llm.quota_manager import get_quota_manager
    return get_quota_manager().get_summary()


@router.get("/search-entities")
async def search_entities(q: str, session: AsyncSession = Depends(get_db)):
    """Busca entidades (empresas/pessoas) para autocomplete no chat."""
    from sqlalchemy import select, or_
    from core.models import CompanyResult, PersonResult

    stmt_orgs = select(CompanyResult).where(
        or_(
            CompanyResult.name.ilike(f"%{q}%"),
            CompanyResult.domain.ilike(f"%{q}%")
        )
    ).limit(5)

    stmt_persons = select(PersonResult).where(
        or_(
            PersonResult.name.ilike(f"%{q}%"),
            PersonResult.role.ilike(f"%{q}%")
        )
    ).limit(5)

    res_orgs = await session.execute(stmt_orgs)
    res_persons = await session.execute(stmt_persons)

    orgs = res_orgs.scalars().all()
    persons = res_persons.scalars().all()

    results = []
    for o in orgs:
        results.append({
            "id": o.id,
            "name": o.name,
            "type": "company",
            "domain": o.domain,
            "logo": o.logo_url
        })
    for p in persons:
        results.append({
            "id": p.id,
            "name": p.name,
            "type": "person",
            "role": p.role,
            "avatar": p.avatar_url
        })

    return results


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """
    Transcreve áudio via Groq Whisper (whisper-large-v3-turbo).
    Aceita webm, ogg, mp4, wav, m4a — qualquer formato que o MediaRecorder produza.
    """
    from core.config import settings
    from core.infra.http_client import get_http_client

    if not settings.GROQ_API_KEY:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY não configurada")

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Arquivo de áudio vazio")

    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"

    client = get_http_client()
    try:
        resp = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            files={"file": (filename, audio_bytes, content_type)},
            data={"model": "whisper-large-v3-turbo", "language": "pt", "response_format": "json"},
            timeout=30.0,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao chamar Groq Whisper: {e}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Groq Whisper retornou {resp.status_code}: {resp.text[:200]}")

    transcript = resp.json().get("text", "").strip()
    return {"transcript": transcript}


@router.post("/refine-message")
async def refine_message(payload: RefineMessageRequest):
    """Refina a mensagem de uma ação pendente com base no feedback do usuário e atualiza em memória."""
    from modules.ai.service.context.business_context_service import BusinessContextService
    from core.llm.router import ask_llm
    from core.llm.base import LLMTier
    import json

    from modules.agent.core.loop import _PENDING as _V2_PENDING
    pending = _V2_PENDING.get(payload.action_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Ação não encontrada ou já expirou.")

    args = pending.get("args", {})
    current_message = args.get("message") or args.get("body") or ""
    contact_name = args.get("contact") or args.get("contact_name") or ""
    channel = "email" if "email" in pending.get("tool", "") else "whatsapp"

    business_context = await BusinessContextService.get_tenant_context()
    biz_data_str = json.dumps(business_context, indent=2, ensure_ascii=False) if business_context else ""

    system_prompt = (
        "Você é um redator comercial B2B sênior. Reescreva a mensagem de vendas abaixo aplicando "
        "exatamente o ajuste solicitado — não altere o que não foi pedido.\n\n"
        f"## CONTEXTO DA EMPRESA (mantenha os diferenciais):\n{biz_data_str}\n\n"
        "REGRAS:\n"
        "- Aplique APENAS o ajuste pedido. Preserve tom, dados concretos (nomes, preços, códigos) e estratégia geral.\n"
        "- Nunca adicione placeholders como [x] ou [y].\n"
        f"- Canal: {channel}. Tom natural e direto.\n"
        "RETORNE APENAS O TEXTO DA MENSAGEM REESCRITA. Sem introdução, sem explicação."
    )
    prompt_user = (
        f"MENSAGEM ORIGINAL:\n{current_message}\n\n"
        f"AJUSTE SOLICITADO: {payload.feedback}\n\n"
        "Reescreva a mensagem aplicando o ajuste."
    )

    try:
        res = await ask_llm(
            prompt=prompt_user,
            system=system_prompt,
            json_mode=False,
            temperature=0.4,
            tier=LLMTier.STANDARD
        )
        refined = res.text.strip()

        args = _V2_PENDING[payload.action_id].get("args", {})
        if "message" in args:
            args["message"] = refined
        if "body" in args:
            args["body"] = refined

        return {"ok": True, "refined_message": refined}
    except Exception as e:
        log.exception("ai.refine_message.failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
