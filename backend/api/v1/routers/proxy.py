"""
api.v1.routers.proxy
====================
Proxy de imagens externas e URL preview com cache em dois niveis.

Cache de imagens: disco local (permanente) -> Redis 7 dias (backup).
Chamadas Redis sao feitas via asyncio.to_thread() para nao bloquear o loop.
Fallback para unavatar.io quando LinkedIn retorna 404/403.

Rotas:
    GET /proxy/image?url=   -> FileResponse com imagem cacheada
    GET /proxy/preview?url= -> metadados Open Graph
"""
import asyncio
import hashlib
import os
import re
from typing import Optional

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, FileResponse

from core.infra.redis_config import redis_client
from core.observability.logging_config import get_logger
from modules.intelligence.service.preview_service import get_url_preview

router = APIRouter()
log = get_logger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "tmp", "image_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _redis_get(key: str):
    return redis_client.get(key) if redis_client else None


def _redis_setex(key: str, ttl: int, data: bytes):
    if redis_client:
        redis_client.setex(key, ttl, data)

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
    try:
        cached = await asyncio.to_thread(_redis_get, cache_key)
        if cached:
            with open(file_path, "wb") as f:
                f.write(cached)
            return FileResponse(file_path, media_type="image/jpeg")
    except Exception as e:
        log.warning("proxy.redis.read_failed", error=str(e))
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Connection": "keep-alive"
    }
    
    # Adiciona Referer específico apenas para domínios que o exigem (LinkedIn)
    if "licdn.com" in url or "linkedin.com" in url:
        headers["Referer"] = "https://www.linkedin.com/"
    
    # Reduzimos o timeout para 5.0s para evitar travar as conexões do navegador
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                image_data = await resp.aread()
                
                # 3. Salva a imagem no Disco Local
                try:
                    with open(file_path, "wb") as f:
                        f.write(image_data)
                except OSError as e:
                    log.warning("proxy.image.disk_write_failed", error=str(e))

                # Cacheia a imagem no Redis por 7 dias (Backups)
                try:
                    await asyncio.to_thread(_redis_setex, cache_key, 604800, image_data)
                except Exception as e:
                    log.warning("proxy.redis.write_failed", error=str(e))
                
                return FileResponse(file_path, media_type=resp.headers.get("content-type", "image/jpeg"))
            
            # Se for 429, 404 ou 403, tentamos o fallback unavatar imediatamente sem sleeps bloqueantes
            if resp.status_code in [429, 404, 403] and ("linkedin.com" in url or "licdn.com" in url):
                match = re.search(r'/company/([^/?#]+)', url)
                if match:
                    company_slug = match.group(1)
                    fallback_url = f"https://unavatar.io/linkedin/{company_slug}"
                    try:
                        f_resp = await client.get(fallback_url, timeout=4.0)
                        if f_resp.status_code == 200:
                            image_data = await f_resp.aread()
                            try:
                                with open(file_path, "wb") as f:
                                    f.write(image_data)
                            except OSError as e:
                                log.warning("proxy.fallback.disk_write_failed", error=str(e))
                            return FileResponse(file_path, media_type="image/png")
                    except Exception as fe:
                        log.warning("proxy.fallback.fetch_failed", error=str(fe))
            
            return StreamingResponse(iter([]), status_code=resp.status_code if resp.status_code != 429 else 404)
        except Exception as e:
            log.warning("proxy.image.fetch_failed", error=str(e))
            # Fallback se der timeout ou erro de rede na imagem original
            if "linkedin.com" in url or "licdn.com" in url:
                match = re.search(r'/company/([^/?#]+)', url)
                if match:
                    company_slug = match.group(1)
                    fallback_url = f"https://unavatar.io/linkedin/{company_slug}"
                    try:
                        f_resp = await client.get(fallback_url, timeout=4.0)
                        if f_resp.status_code == 200:
                            image_data = await f_resp.aread()
                            try:
                                with open(file_path, "wb") as f:
                                    f.write(image_data)
                            except OSError as e:
                                log.warning("proxy.fallback.disk_write_failed", error=str(e))
                            return FileResponse(file_path, media_type="image/png")
                    except Exception:
                        pass
            return StreamingResponse(iter([]), status_code=404)
