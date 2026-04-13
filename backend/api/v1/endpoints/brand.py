from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional, AsyncGenerator
import json
from services.intelligence.brand_discovery import discover_company_brand
from services.intelligence.brand_discovery_stream import discover_company_brand_stream

router = APIRouter()

@router.get("/discover")
async def discover_brand(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    domain: Optional[str] = Query(None, description="Domínio da empresa"),
    raw_name: Optional[str] = Query(None, description="Nome base da empresa"),
    force: bool = Query(False, description="Forçar nova busca OSINT"),
    stream: bool = Query(False, description="Se True, faz streaming dos candidatos. Se False, retorna tudo de uma vez.")
):
    """
    Busca sugestões de nomes de marca (LinkedIn-ready) antes de iniciar o scan.
    Se stream=true, retorna um stream de Server-Sent Events com cada candidato.
    """
    if not stream:
        # Modo compatível: retorna tudo de uma vez
        try:
            return await discover_company_brand(cnpj, domain, raw_name, force=force)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))
    
    # Modo streaming: SSE
    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in discover_company_brand_stream(cnpj, domain, raw_name, force=force):
                yield f"data: {json.dumps(event)}\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
