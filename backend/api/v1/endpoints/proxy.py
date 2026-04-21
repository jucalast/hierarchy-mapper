from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
import httpx
from typing import Optional
from services.intelligence.preview_service import get_url_preview
import hashlib
from core.redis_config import redis_client

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
    """Proxy para carregar imagens do LinkedIn sem bloqueio de CORS com CACHE."""
    # Cache key baseado na URL
    cache_key = f"image_proxy:{hashlib.md5(url.encode()).hexdigest()}"
    
    # Tenta buscar do cache primeiro
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                # Serve da cache (válido por 7 dias)
                return StreamingResponse(
                    iter([cached]), 
                    media_type="image/jpeg"
                )
        except Exception as e:
            print(f"Redis cache read error: {e}")
            pass  # Se cache falha, continua com a requisição
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Connection": "keep-alive"
    }
    
    # Adiciona Referer específico apenas para domínios que o exigem (LinkedIn)
    if "licdn.com" in url or "linkedin.com" in url:
        headers["Referer"] = "https://www.linkedin.com/"
    import asyncio
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Tenta até 4 vezes com jitter incremental para burlar o Rate Limit de Bursts
        for attempt in range(4):
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    image_data = await resp.aread()
                    # Cacheia a imagem por 7 dias (604800 segundos)
                    if redis_client:
                        try:
                            redis_client.setex(cache_key, 604800, image_data)
                        except Exception as e:
                            print(f"Redis cache write error: {e}")
                            pass  # Se cache falha, não bloqueia a resposta
                    
                    return StreamingResponse(
                        iter([image_data]), 
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
