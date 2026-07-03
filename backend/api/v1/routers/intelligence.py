"""
api.v1.routers.intelligence
===========================
Endpoints para ferramentas de inteligência e enriquecimento manual.
"""
from __future__ import annotations

from typing import Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from core.observability.logging_config import get_logger

router = APIRouter()
log = get_logger(__name__)

class EmailDiscoveryRequest(BaseModel):
    contact_name: str
    org_name: Optional[str] = None
    domain: Optional[str] = None
    job_title: Optional[str] = None
    person_id: Optional[Any] = None
    org_id: Optional[int] = None
    force: bool = False

@router.post("/discover-email")
async def discover_email(payload: EmailDiscoveryRequest):
    """
    Endpoint manual para a ferramenta discover_and_validate_email.
    """
    from modules.agent.service.tools.intelligence import exec_discover_and_validate_email

    try:
        log.info("intelligence.discover_email.started", contact=payload.contact_name, org=payload.org_name, force=payload.force)

        args = {
            "contact_name": payload.contact_name,
            "org_name": payload.org_name,
            "domain": payload.domain,
            "job_title": payload.job_title,
            "person_id": payload.person_id,
            "org_id": payload.org_id,
            "force": payload.force,
        }

        result = await exec_discover_and_validate_email(args)
        
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error")}
            
        return result
        
    except Exception as e:
        log.exception("intelligence.discover_email.failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Erro ao processar descoberta de e-mail: {str(e)}")
