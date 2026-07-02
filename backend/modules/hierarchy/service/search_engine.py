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
import os
import sys
import json
import time
import subprocess
import concurrent.futures
import httpx
import urllib.parse
from typing import List, Dict, Optional

# Caminho do runner isolado (roda o DDG num subprocess matável — ver _sync_ddg_search).
_DDG_RUNNER_PATH = os.path.join(os.path.dirname(__file__), "ddg_runner.py")
_DDG_SUBPROCESS_TIMEOUT = 15.0

# Executor DEDICADO para o DuckDuckGo. A lib do DDG às vezes pendura a thread quando é
# rate-limitada, e wait_for NÃO mata a thread — ele só abandona a corrotina. Isolando aqui,
# uma thread pendurada nunca esgota o ThreadPoolExecutor padrão do asyncio (que o resto do
# app usa via asyncio.to_thread), evitando que o app inteiro trave. Threads penduradas ficam
# capadas ao tamanho deste pool.
_DDG_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="ddg")
# Limita buscas DDG concorrentes para não empilhar submissões no executor dedicado.
_DDG_SEMAPHORE = asyncio.Semaphore(2)
# Circuit breaker: depois de N timeouts/falhas seguidos, pula o DDG por um tempo e vai direto
# pro Bing — evita ficar penando o timeout a cada busca quando o DDG está claramente bloqueado.
_DDG_CB = {"fails": 0, "open_until": 0.0}
_DDG_CB_THRESHOLD = 5
_DDG_CB_COOLDOWN = 60.0

def normalize_linkedin_url(url: str) -> str:
    """
    Normaliza URLs do LinkedIn para formato canônico:
    1. Força www.linkedin.com (remove br., pt., etc.)
    2. Encode do path (preserva o encoding correto para caracteres especiais)
    """
    if not url or "linkedin.com" not in url:
        return url
    try:
        parsed = urllib.parse.urlparse(url)
        # Substitui subdomínios regionais (br.linkedin.com, pt.linkedin.com) pelo padrão www
        new_netloc = "www.linkedin.com"
        # Limpa e re-encode o path para garantir que caracteres como 'ç' sejam %C3%A7
        clean_path = urllib.parse.unquote(parsed.path)
        encoded_path = urllib.parse.quote(clean_path, safe='/')
        return urllib.parse.urlunparse(parsed._replace(netloc=new_netloc, path=encoded_path))
    except:
        return url

async def _get_bing_fallback(query: str, is_company: bool = False, filter_linkedin: bool = True) -> List[Dict]:
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
                    if not filter_linkedin or "linkedin.com/" in href:
                        title = re.sub(r'<[^>]+>', '', raw_title).strip()
                        results.append({
                            "title": html.unescape(title) or "LinkedIn Profile",
                            "href": normalize_linkedin_url(href),
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
                        "href": normalize_linkedin_url(href),
                        "body": snippet or "Vínculo profissional identificado."
                    })
                
            if filter_linkedin:
                valid_patterns = ["linkedin.com/company/", "linkedin.com/school/"] if is_company else ["linkedin.com/in/"]
                results = [r for r in results if any(p in r.get("href", "") for p in valid_patterns)]
            
            if results:
                print(f"[SearchEngine] ✅ Sucesso no Fallback (Bing)! {len(results)} resultados encontrados.")
                return results
                
    except Exception as e:
        print(f"[SearchEngine] ❌ Falha no Fallback (Bing): {e}")
        
    return []

async def get_duck_results(query: str, max_results: int = 50, is_company: bool = False, filter_linkedin: bool = True) -> List[Dict]:
    """
    Motor DuckDuckGo Otimizado com Fallback imediato para Bing Search.
    Focado em evitar bloqueios, silenciar avisos de rate limit e garantir consistência absoluta.
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]
    
    # Circuit breaker: se o DDG falhou seguidamente há pouco, nem tenta — vai direto pro Bing.
    if time.monotonic() < _DDG_CB["open_until"]:
        print(f"[SearchEngine] ⏭️ DuckDuckGo em cooldown (circuit breaker) — indo direto pro Bing.")
        return await _get_bing_fallback(query, is_company, filter_linkedin)

    # Delay inicial adaptativo
    await asyncio.sleep(random.uniform(0.5, 1.5))

    # --- MOTOR PRINCIPAL: DUCKDUCKGO ---
    consecutive_403 = 0
    ddg_success = False
    ddg_results = []

    def _sync_ddg_search(q: str, n: int) -> list:
        # Roda o DDG num SUBPROCESS matável. A lib ddgs/primp (Rust) pode SEGURAR o GIL
        # durante uma chamada de rede travada — se rodar in-process, congela o event loop
        # inteiro (nem asyncio.wait acorda). O subprocess tem GIL próprio e é MORTO no
        # timeout (subprocess.run(timeout=...) → TimeoutExpired), e o subprocess.run libera
        # o GIL enquanto espera, então o processo pai continua respondendo.
        proc = subprocess.run(
            [sys.executable, _DDG_RUNNER_PATH, q, str(n)],
            capture_output=True, text=True, timeout=_DDG_SUBPROCESS_TIMEOUT,
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            return json.loads(proc.stdout)
        return []

    for attempt in range(2):
        try:
            ua = random.choice(user_agents)
            print(f"[SearchEngine] Tentando DuckDuckGo (Tentativa {attempt+1}/4) com UA: {ua[:30]}...")

            # Roda no executor DEDICADO, sob semáforo. asyncio.wait (não wait_for) é o backstop:
            # o guard principal é o timeout do próprio subprocess, que MATA o processo travado.
            loop = asyncio.get_running_loop()
            async with _DDG_SEMAPHORE:
                _ddg_fut = loop.run_in_executor(_DDG_EXECUTOR, _sync_ddg_search, query, max_results)
                _done, _pending = await asyncio.wait({_ddg_fut}, timeout=_DDG_SUBPROCESS_TIMEOUT + 5.0)
                if _ddg_fut not in _done:
                    raise asyncio.TimeoutError  # não deveria ocorrer (subprocess já tem timeout)
                raw_results = _ddg_fut.result()

            if raw_results:
                if filter_linkedin:
                    valid_patterns = ["linkedin.com/company/", "linkedin.com/school/"] if is_company else ["linkedin.com/in/"]
                    filtered = []
                    for r in raw_results:
                        href = r.get("href", "")
                        if any(p in href for p in valid_patterns):
                            r["href"] = normalize_linkedin_url(href)
                            filtered.append(r)
                else:
                    filtered = raw_results

                if filtered:
                    print(f"[SearchEngine] ✅ Sucesso (DDG)! {len(filtered)} resultados encontrados.")
                    ddg_results = filtered
                    ddg_success = True
                    _DDG_CB["fails"] = 0  # sucesso reseta o circuit breaker
                    _DDG_CB["open_until"] = 0.0
                    break

        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            # DDG travou (subprocess morto no timeout) — não insiste, vai direto pro fallback Bing.
            print(f"[SearchEngine] ⏱️ DuckDuckGo excedeu o tempo limite (tentativa {attempt+1}) — acionando fallback Bing.")
            _DDG_CB["fails"] += 1
            if _DDG_CB["fails"] >= _DDG_CB_THRESHOLD:
                _DDG_CB["open_until"] = time.monotonic() + _DDG_CB_COOLDOWN
                print(f"[SearchEngine] 🧯 Circuit breaker ABERTO — pulando o DDG por {int(_DDG_CB_COOLDOWN)}s.")
            break
        except Exception as e:
            msg = str(e)
            is_403 = "403" in msg or "Forbidden" in msg
            is_429 = "429" in msg or "Ratelimit" in msg

            if is_403:
                consecutive_403 += 1
                print(f"[SearchEngine] 🛡️ Bloqueio 403 (tentativa {attempt+1}) — IP bloqueado no DDG.")
                if consecutive_403 >= 1: # Na primeira falha 403 já prepara fallback se a próxima falhar
                    print(f"[SearchEngine] Acionando Fallback rápido...")
                    if attempt >= 1: break # Se falhou 2 vezes, desiste do DDG
                await asyncio.sleep(1.5)
            elif is_429:
                print(f"[SearchEngine] 🚨 Rate limit 429 no DuckDuckGo — acionando fallback imediatamente.")
                break
            else:
                print(f"[SearchEngine] ⚠️ Erro no DDG: {msg}")
                if attempt >= 1: break
                await asyncio.sleep(1.0)
            continue

    if ddg_success and ddg_results:
        return ddg_results

    # --- FALLBACK DE SEGURANÇA: BING SEARCH ---
    # Acionado se o DuckDuckGo falhar, der rate limit ou não retornar resultados orgânicos
    fallback_res = await _get_bing_fallback(query, is_company, filter_linkedin)
    if fallback_res:
        return fallback_res

    return []
