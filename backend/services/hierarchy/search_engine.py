import asyncio
import random
import re
import httpx
import urllib.parse
from typing import List, Dict, Optional
from ddgs import DDGS

async def get_duck_results(query: str, max_results: int = 50, is_company: bool = False) -> List[Dict]:
    """
    Motor Híbrido Multimotor (DDG + Google) para Burlar Bloqueios.
    is_company: Se True, permite links de /company/ e /school/.
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
    ]
    
    # 💤 Delay randômico menor p/ não parecer travado mas ainda evitar detecção
    await asyncio.sleep(random.uniform(2.0, 5.0))
    
    results = []

    # --- MOTOR 1: DUCKDUCKGO (Focado em volume) ---
    try:
        print(f"[SearchEngine] Tentando DuckDuckGo...")
        # A biblioteca DDGS pode não ser nativamente async em loop, então rodamos num executor se necessário
        # Mas para simplificar vamos tentar o wrapper padrão aqui
        with DDGS() as ddgs:
            search_iter = ddgs.text(query, region="br-pt", max_results=max_results)
            if search_iter:
                raw_results = list(search_iter)
                filtered_results = []
                for r in raw_results:
                    href = r.get("href", "")
                    # Filtro inteligente: Pessoas vs Empresas (MUTUAMENTE EXCLUSIVO)
                    if is_company:
                        valid_patterns = ["linkedin.com/company/", "linkedin.com/school/"]
                    else:
                        valid_patterns = ["linkedin.com/in/"]
                        
                    if any(p in href for p in valid_patterns):
                        filtered_results.append(r)
                
                if filtered_results:
                    print(f"[SearchEngine] Sucesso (DDG)! {len(filtered_results)} perfis LinkedIn filtrados.")
                    return filtered_results
    except Exception as e:
        print(f"[SearchEngine] DDG limitado: {e}. Tentando Modo Reserva (Manual)...")

    # --- MOTOR 2: GOOGLE (Raspagem Direta em Modo Stealth) ---
    print(f"[SearchEngine] Ativando Motor de Reserva (Google Stealth)...")
    try:
        encoded_query = urllib.parse.quote(query)
        google_url = f"https://www.google.com/search?q={encoded_query}"
        
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.google.com/",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        
        async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
            response = await client.get(google_url, headers=headers)
            if response.status_code == 200:
                html_content = response.text
                
                # 🧼 Extração de Resultados (Links + Títulos + Snippets)
                # Regex mais flexível para capturar blocos de resultado
                blocks = re.findall(r'<div[^>]*class="g"[^>]*>.*?</div></div>', html_content, re.DOTALL)
                if not blocks:
                    blocks = html_content.split('<div class="g">')[1:] 
                
                for block in blocks[:max_results]:
                    try:
                        # Tenta achar o link real (direto ou via /url?q=)
                        link_match = re.search(r'href="/url\?q=(https://[^&]+)', block)
                        if not link_match:
                            link_match = re.search(r'href="(https?://[^"]*linkedin\.com/in/[^"]*)"', block)
                        
                        if link_match:
                            link = link_match.group(1).replace("%2F", "/").replace("%3A", ":").replace("%3F", "?").replace("%3D", "=").replace("%2D", "-")
                            title_match = re.search(r'<h3[^>]*>(.*?)</h3>', block)
                            title = re.sub(r'<[^>]*>', '', title_match.group(1)) if title_match else "Perfil LinkedIn"
                            
                            # Snippet (Geralmente em um span ou div com classe VwiC3b)
                            snippet_match = re.search(r'class="VwiC3b[^>]*>(.*?)</div>', block, re.DOTALL)
                            if snippet_match:
                                snippet = re.sub(r'<[^>]*>', '', snippet_match.group(1))
                            else:
                                snippet_data = re.sub(r'<[^>]*>', ' ', block).strip()
                                snippet = " ".join(snippet_data.split()[:50])

                            results.append({
                                "title": title,
                                "href": link,
                                "body": snippet,
                                "snippet": snippet
                            })
                    except:
                        continue
                
                if results:
                    print(f"[SearchEngine] Sucesso (Google Stealth)! {len(results)} resultados encontrados.")
                    return results
            elif response.status_code == 429:
                print(f"[SearchEngine] Google bloqueou por 429.")
            elif response.status_code == 403:
                print(f"[SearchEngine] Google bloqueou por 403.")
                
    except Exception as eg:
        print(f"[SearchEngine] Falha Crítica no Motor de Reserva Google: {eg}")

    # --- MOTOR 3: QWANT (Antiblock Europeu) ---
    try:
        print(f"[SearchEngine] Tentando Qwant (Reserva Europeia)...")
        qwant_url = f"https://www.qwant.com/?q={urllib.parse.quote(query)}&t=web"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(qwant_url, headers={"User-Agent": random.choice(user_agents)})
            if resp.status_code == 200:
                html = resp.text
                # 🧹 Extração de LinkedIn com filtro de Pessoas vs Empresas Estrito
                if is_company:
                    pattern = r'https?://(?:br\.)?linkedin\.com/(?:company|school)/[a-zA-Z0-9\-_%]+'
                else:
                    pattern = r'https?://(?:br\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+'
                
                links = re.findall(pattern, html)
                for link in links:
                    if link not in [r["href"] for r in results]:
                        results.append({
                            "title": "Perfil LinkedIn",
                            "href": link,
                            "body": "Resultado via Qwant",
                            "snippet": "Resultado via Qwant"
                        })
                if results:
                    print(f"[SearchEngine] Sucesso (Qwant)! {len(results)} resultados.")
                    return results
    except Exception as eq:
        print(f"[SearchEngine] Qwant falhou: {eq}")

    # --- MOTOR 4: BRAVE SEARCH (Stealth) ---
    try:
        print(f"[SearchEngine] Tentando Brave Search...")
        brave_url = f"https://search.brave.com/search?q={urllib.parse.quote(query)}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(brave_url, headers={"User-Agent": random.choice(user_agents)})
            if resp.status_code == 200:
                html = resp.text
                # 🧹 Extração de LinkedIn com filtro de Pessoas vs Empresas Estrito
                if is_company:
                    pattern = r'https?://(?:br\.)?linkedin\.com/(?:company|school)/[a-zA-Z0-9\-_%]+'
                else:
                    pattern = r'https?://(?:br\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+'
                
                links = re.findall(pattern, html)
                for link in links:
                    if link not in [r["href"] for r in results]:
                        results.append({
                            "title": "Perfil LinkedIn",
                            "href": link,
                            "body": "Resultado via Brave",
                            "snippet": "Resultado via Brave"
                        })
                if results:
                    print(f"[SearchEngine] Sucesso (Brave)! {len(results)} resultados.")
                    return results
    except Exception as eb:
        print(f"[SearchEngine] Brave falhou: {eb}")

    # --- MOTOR 5: BING (Stealth) ---
    try:
        print(f"[SearchEngine] Tentando Bing Search...")
        bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(bing_url, headers={"User-Agent": random.choice(user_agents)})
            if resp.status_code == 200:
                html = resp.text
                # 🧹 Extração de LinkedIn com filtro de Pessoas vs Empresas Estrito
                if is_company:
                    pattern = r'https?://(?:br\.)?linkedin\.com/(?:company|school)/[a-zA-Z0-9\-_%]+'
                else:
                    pattern = r'https?://(?:br\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+'
                
                links = re.findall(pattern, html)
                for link in links:
                    if link not in [r["href"] for r in results]:
                        results.append({
                            "title": "Perfil LinkedIn",
                            "href": link,
                            "body": "Resultado via Bing",
                            "snippet": "Resultado via Bing"
                        })
                if results:
                    print(f"[SearchEngine] Sucesso (Bing)! {len(results)} resultados.")
                    return results
    except Exception as eb:
        print(f"[SearchEngine] Bing falhou: {eb}")

    # --- MOTOR 6: MOJEEK (Ultima instância) ---
    try:
        print(f"[SearchEngine] Tentando Mojeek (Antiblock)...")
        mojeek_url = f"https://www.mojeek.com/search?q={urllib.parse.quote(query)}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(mojeek_url, headers={"User-Agent": random.choice(user_agents)})
            if resp.status_code == 200:
                html = resp.text
                matches = re.findall(r'class="ob">.*?href="(https://[^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL)
                for link, title in matches:
                    # Filtro inteligente: Pessoas vs Empresas (MUTUAMENTE EXCLUSIVO)
                    if is_company:
                        is_match = "/company/" in link or "/school/" in link
                    else:
                        is_match = "/in/" in link
                        
                    if is_match:
                        results.append({
                            "title": re.sub(r'<[^>]*>', '', title),
                            "href": link,
                            "body": "Via Mojeek",
                            "snippet": "Via Mojeek"
                        })
                if results:
                    print(f"[SearchEngine] Sucesso (Mojeek)! {len(results)} resultados.")
                    return results
    except: pass

    return results
