"""
modules.hierarchy.service.search_engine
========================================
Motor de busca DuckDuckGo com rotation de User-Agent e retry com jitter.

Executa o ddg_runner.py em subprocess para evitar conflitos de event loop.
is_company=True ativa filtros especificos para nomes de empresa.

Funcao publica: get_duck_results(query, max_results, is_company) -> list[dict]
"""
import asyncio
import random
import re
import html
import httpx
import urllib.parse
import sys
from typing import List, Dict, Optional
from ddgs import DDGS

async def _get_bing_fallback(query: str, is_company: bool = False) -> List[Dict]:
    """
    Scraper tático de fallback usando o Bing Search.
    Extremamente leve, resiliente a rate limits e sem dependências externas.
    """
    print(f"[SearchEngine] 🔄 Iniciando fallback de segurança via Bing Search...")
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
    ]
    
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3",
        "Referer": "https://www.bing.com/",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={encoded_query}&count=50"
    
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                print(f"[SearchEngine] ⚠️ Bing respondeu com status {response.status_code}")
                return []
                
            html_content = response.text
            
            # Regex ultra robusto para capturar os blocos de resultados do Bing
            blocks = re.findall(r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', html_content, re.DOTALL)
            
            results = []
            if not blocks:
                print("[SearchEngine] ⚠️ Estrutura padrão do Bing não encontrada. Tentando extração genérica de links...")
                links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_content)
                for href, raw_title in links:
                    if "linkedin.com/" in href:
                        title = re.sub(r'<[^>]+>', '', raw_title).strip()
                        results.append({
                            "title": html.unescape(title) or "LinkedIn Profile",
                            "href": href,
                            "body": "Perfil profissional encontrado via busca orgânica."
                        })
            else:
                for block in blocks:
                    # 1. Extrai o Link e o Título
                    link_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block)
                    if not link_match:
                        continue
                        
                    href = link_match.group(1)
                    raw_title = link_match.group(2)
                    title = re.sub(r'<[^>]+>', '', raw_title).strip()
                    
                    # 2. Extrai o Snippet (Descrição)
                    snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
                    if not snippet_match:
                        snippet_match = re.search(r'<div[^>]+class="[^"]*b_caption[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
                    if not snippet_match:
                        snippet_match = re.search(r'<div[^>]+class="[^"]*b_snippet[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
                        
                    raw_snippet = snippet_match.group(1) if snippet_match else ""
                    snippet = re.sub(r'<[^>]+>', '', raw_snippet).strip()
                    
                    # Descodifica entidades HTML básicas
                    title = html.unescape(title)
                    snippet = html.unescape(snippet)
                    
                    results.append({
                        "title": title or "Perfil no LinkedIn",
                        "href": href,
                        "body": snippet or "Vínculo profissional identificado."
                    })
                
            valid_patterns = ["linkedin.com/company/", "linkedin.com/school/"] if is_company else ["linkedin.com/in/"]
            filtered = [r for r in results if any(p in r.get("href", "") for p in valid_patterns)]
            
            if filtered:
                print(f"[SearchEngine] ✅ Sucesso no Fallback (Bing)! {len(filtered)} perfis LinkedIn encontrados.")
                return filtered
                
    except Exception as e:
        print(f"[SearchEngine] ❌ Falha no Fallback (Bing): {e}")
        
    return []

async def get_duck_results(query: str, max_results: int = 50, is_company: bool = False) -> List[Dict]:
    """
    Motor DuckDuckGo Otimizado com Fallback imediato para Bing Search.
    Focado em evitar bloqueios, silenciar avisos de rate limit e garantir consistência absoluta.
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]
    
    # Delay inicial curto para não sobrecarregar
    await asyncio.sleep(random.uniform(1.0, 2.0))

    # --- RESILIÊNCIA DE REDE ---
    for dns_attempt in range(2):
        try:
            import socket
            socket.gethostbyname('duckduckgo.com')
            break
        except:
            if dns_attempt == 0: await asyncio.sleep(1.0)
            else: return []

    # --- MOTOR PRINCIPAL: DUCKDUCKGO ---
    consecutive_403 = 0
    ddg_success = False
    ddg_results = []
    
    for attempt in range(4):
        try:
            ua = random.choice(user_agents)
            print(f"[SearchEngine] Tentando DuckDuckGo (Tentativa {attempt+1}/4) com UA: {ua[:30]}...")

            with DDGS(timeout=15) as ddgs:
                raw_results = list(ddgs.text(query, region="br-pt", max_results=max_results, backend="lite"))

                if raw_results:
                    valid_patterns = ["linkedin.com/company/", "linkedin.com/school/"] if is_company else ["linkedin.com/in/"]
                    filtered = [r for r in raw_results if any(p in r.get("href", "") for p in valid_patterns)]
                    if filtered:
                        print(f"[SearchEngine] Sucesso (DDG)! {len(filtered)} perfis LinkedIn filtrados.")
                        ddg_results = filtered
                        ddg_success = True
                        break

                await asyncio.sleep(1.5)

        except Exception as e:
            msg = str(e)
            is_403 = "403" in msg or "Forbidden" in msg
            is_429 = "429" in msg or "Ratelimit" in msg

            if is_403:
                consecutive_403 += 1
                print(f"[SearchEngine] Bloqueio 403 (tentativa {attempt+1}) — IP bloqueado no DDG.")
                if consecutive_403 >= 2:
                    print(f"[SearchEngine] 2 bloqueios 403 consecutivos no DDG — migrando para fallback.")
                    break
                await asyncio.sleep(2.0)
            elif is_429:
                print(f"[SearchEngine] 🚨 Rate limit 429 no DuckDuckGo — acionando fallback de segurança imediatamente.")
                break
            else:
                print(f"[SearchEngine] Erro no DDG: {msg}")
                await asyncio.sleep(2.0)
            continue

    if ddg_success and ddg_results:
        return ddg_results

    # --- FALLBACK DE SEGURANÇA: BING SEARCH ---
    # Acionado se o DuckDuckGo falhar, der rate limit ou não retornar resultados orgânicos
    fallback_res = await _get_bing_fallback(query, is_company)
    if fallback_res:
        return fallback_res

    return []
