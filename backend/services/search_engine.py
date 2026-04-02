import time
import random
import re
import httpx
from typing import List, Dict, Optional
from ddgs import DDGS

def get_duck_results(query: str, max_results: int = 50) -> List[Dict]:
    """
    Motor Híbrido Multimotor (DDG + Google) para Burlar Bloqueios.
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
    ]
    
    time.sleep(random.uniform(10.0, 20.0))
    results = []

    # --- MOTOR 1: DUCKDUCKGO (Focado em volume) ---
    try:
        print(f"[SearchEngine] Tentando DuckDuckGo...")
        with DDGS() as ddgs:
            search_iter = ddgs.text(query, region="br-pt", max_results=max_results)
            if search_iter:
                results = list(search_iter)
                if results:
                    print(f"[SearchEngine] Sucesso (DDG)! {len(results)} resultados.")
                    return results
    except Exception as e:
        print(f"[SearchEngine] DDG limitado: {e}. Tentando Modo Reserva (Manual)...")

    # --- MOTOR 2: GOOGLE (Raspagem Direta em Modo Stealth) ---
    print(f"[SearchEngine] Ativando Motor de Reserva (Google Stealth)...")
    try:
        # Simplifica query para o Google (Dorks exatas)
        google_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.google.com/"
        }
        
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(google_url, headers=headers)
            if response.status_code == 200:
                html_content = response.text
                
                # 🧼 Extração de Resultados (Links + Títulos + Snippets)
                # O Google separa resultados por classes que mudam, mas o padrão de link /url?q= é persistente
                blocks = re.findall(r'<div[^>]*class="g"[^>]*>.*?</div></div>', html_content, re.DOTALL)
                if not blocks:
                    blocks = html_content.split('<div class="g">')[1:] 
                
                for block in blocks[:max_results]:
                    try:
                        # 🔗 Busca Link (/url?q=) ou link direto
                        link_match = re.search(r'href="/url\?q=(https://[^&]+)', block)
                        if not link_match:
                            link_match = re.search(r'href="(https?://br\.linkedin\.com/[^"]*)"', block)
                        
                        if link_match:
                            link = link_match.group(1).replace("%2F", "/").replace("%3A", ":").replace("%3F", "?").replace("%3D", "=")
                            
                            # 📝 Busca Título
                            title_match = re.search(r'<h3[^>]*>(.*?)</h3>', block)
                            title = re.sub(r'<[^>]*>', '', title_match.group(1)) if title_match else "Perfil LinkedIn"

                            # 📄 Busca Snippet
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
    except Exception as eg:
        print(f"[SearchEngine] Falha Crítica no Motor de Reserva: {eg}")

    time.sleep(random.uniform(20, 30))
    return results
