from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, FileResponse
import httpx
from typing import Optional
from services.intelligence.preview_service import get_url_preview
import hashlib
import os
from core.redis_config import redis_client

router = APIRouter()

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tmp", "image_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

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
    """Proxy para carregar imagens do LinkedIn sem bloqueio de CORS com CACHE (Disco + Redis)."""
    # Cache key baseado na URL
    cache_key = f"img_{hashlib.md5(url.encode()).hexdigest()}"
    file_path = os.path.join(CACHE_DIR, cache_key + ".jpg")
    
    # 1. Tenta servir do Disco Local (PERMANENTE E SUPER RÁPIDO)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/jpeg")

    # 2. Tenta buscar do cache REDIS caso o arquivo tenha sido deletado
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                # Salva no disco pra próxima vez também ser instantâneo
                with open(file_path, "wb") as f:
                    f.write(cached)
                return FileResponse(file_path, media_type="image/jpeg")
        except Exception as e:
            print(f"Redis cache read error: {e}")
            pass 
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Connection": "keep-alive"
    }
    
    # Adiciona Referer específico apenas para domínios que o exigem (LinkedIn)
    if "licdn.com" in url or "linkedin.com" in url:
        headers["Referer"] = "https://www.linkedin.com/"
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Tenta até 4 vezes com jitter incremental para burlar o Rate Limit de Bursts
        for attempt in range(4):
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    image_data = await resp.aread()
                    
                    # 3. Salva a imagem no Disco Local
                    try:
                        with open(file_path, "wb") as f:
                            f.write(image_data)
                    except Exception as e:
                        print(f"Error writing image to disk: {e}")

                    # Cacheia a imagem no Redis por 7 dias (Backups)
                    if redis_client:
                        try:
                            redis_client.setex(cache_key, 604800, image_data)
                        except Exception as e:
                            print(f"Redis cache write error: {e}")
                    
                    return FileResponse(file_path, media_type=resp.headers.get("content-type", "image/jpeg"))
                elif resp.status_code == 429:
                    import asyncio
                    await asyncio.sleep(1.5 + (attempt * 1.5))
                    continue
                elif resp.status_code in [404, 403] and ("linkedin.com" in url or "licdn.com" in url):
                    # 🔥 FALLBACK ESTRATÉGICO: Se o LinkedIn deu 404/403, tenta buscar via unavatar.io
                    # Extrai o nome da empresa da URL do LinkedIn (ex: /company/industrias-nardini)
                    import re
                    match = re.search(r'/company/([^/?#]+)', url)
                    if match:
                        company_slug = match.group(1)
                        # Tenta unavatar via linkedin slug ou tenta deduzir que é um domínio
                        fallback_url = f"https://unavatar.io/linkedin/{company_slug}"
                        f_resp = await client.get(fallback_url)
                        if f_resp.status_code == 200:
                            image_data = await f_resp.aread()
                            # Salva no disco
                            try:
                                with open(file_path, "wb") as f:
                                    f.write(image_data)
                            except: pass
                            return FileResponse(file_path, media_type="image/png")
                    
                    return StreamingResponse(iter([]), status_code=resp.status_code)
                else:
                    return StreamingResponse(iter([]), status_code=resp.status_code)
            except Exception as e:
                return StreamingResponse(iter([]), status_code=404)
                
        return StreamingResponse(iter([]), status_code=429)
