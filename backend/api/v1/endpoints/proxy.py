from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
import httpx
from typing import Optional
from services.intelligence.preview_service import get_url_preview

router = APIRouter()

@router.get("/preview")
async def fetch_url_preview(
    url: str,
    role_hint: Optional[str] = Query(None),
    company_hint: Optional[str] = Query(None)
):
    """Retorna metadados Open Graph de uma URL para preview com fallbacks inteligentes."""
    return await get_url_preview(url, role_hint, company_hint)

@router.get("/image")
async def proxy_linkedin_image(url: str):
    """Proxy para carregar imagens do LinkedIn sem bloqueio de CORS."""
    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://www.linkedin.com/",
        "Connection": "keep-alive"
    }
    import asyncio
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Tenta até 4 vezes com jitter incremental para burlar o Rate Limit de Bursts
        for attempt in range(4):
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return StreamingResponse(
                        resp.aiter_bytes(), 
                        media_type=resp.headers.get("content-type", "image/jpeg")
                    )
                elif resp.status_code == 429:
                    # Se bateu o limite do unavatar, dorme e tenta de novo (Trickle Down)
                    await asyncio.sleep(1.5 + (attempt * 1.5))
                    continue
                else:
                    return StreamingResponse(iter([]), status_code=resp.status_code)
            except Exception as e:
                # Falha silenciosa para não quebrar a UI
                return StreamingResponse(iter([]), status_code=404)
                
        return StreamingResponse(iter([]), status_code=429)
