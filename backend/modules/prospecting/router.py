from fastapi import APIRouter, HTTPException, Query

from .schemas import SearchRequest
from .service import (
    start_prospect_search,
    get_session,
    get_session_leads,
    list_sessions,
    approve_lead,
    reject_lead,
    stop_prospect_search,
    clear_prospecting_data,
)

router = APIRouter()


@router.post("/search")
async def create_prospect_search(body: SearchRequest):
    """
    Inicia prospecção por coordenadas + raio.
    O sistema busca automaticamente todos os segmentos ICP da J.Ferres.
    Retorna session_id imediatamente; use GET /sessions/{id} para acompanhar.
    """
    session_id = await start_prospect_search(
        lat=body.lat,
        lng=body.lng,
        radius_km=body.radius_km,
    )
    return {"session_id": session_id, "status": "running"}


@router.get("/sessions")
async def get_sessions(limit: int = Query(20, ge=1, le=100)):
    return await list_sessions(limit=limit)


@router.get("/leads/pending")
async def get_all_pending_leads():
    from .service.prospect import get_all_pending_leads as get_pending
    leads = await get_pending()
    return {"leads": leads, "total": len(leads)}


@router.get("/sessions/{session_id}")
async def get_session_status(session_id: str):
    sess = await get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    return sess


@router.get("/sessions/{session_id}/leads")
async def get_leads(session_id: str):
    sess = await get_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")
    leads = await get_session_leads(session_id)
    return {"session": sess, "leads": leads, "total": len(leads)}


@router.post("/leads/{lead_id}/approve")
async def approve(lead_id: str):
    try:
        return await approve_lead(lead_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar no Pipedrive: {e}")


@router.post("/leads/{lead_id}/reject")
async def reject(lead_id: str):
    try:
        return await reject_lead(lead_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str):
    ok = await stop_prospect_search(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Sessão não encontrada ou já encerrada.")
    return {"status": "stopped"}


@router.delete("/clear")
async def clear_all():
    return await clear_prospecting_data()
