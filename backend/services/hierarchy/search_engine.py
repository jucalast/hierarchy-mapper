import asyncio
import random
import re
import httpx
import urllib.parse
import sys
from typing import List, Dict, Optional
from duckduckgo_search import DDGS

async def get_duck_results(query: str, max_results: int = 50, is_company: bool = False) -> List[Dict]:
    """
    Motor Híbrido Multimotor (DDG + Google) para Burlar Bloqueios.
    is_company: Se True, permite links de /company/ e /school/.
    """    # 🛡️ Lista ampliada de User-Agents modernos para evitar fingerprints genéricos
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
    ]
    
    # 💤 Delay randômico BASE para evitar sequenciamento robótico
    await asyncio.sleep(random.uniform(4.0, 8.0))
    
    results = []

    # --- RESILIÊNCIA DE REDE (Verificação de DNS) ---
    for dns_attempt in range(2):
        try:
            # Tenta resolver um domínio confiável para garantir que a rede está OK
            import socket
            socket.gethostbyname('google.com')
            break
        except Exception as e:
            print(f"[SearchEngine] ⚠️ Problema de Conexão/DNS detectado: {e}")
            if dns_attempt == 0:
                print("      Aguardando 5s para estabilização da rede...")
                await asyncio.sleep(5.0)
            else:
                print("      🚨 Falha crítica de DNS. Abortando busca para evitar loops de erro.")
                return []

    # --- MOTOR 1: DUCKDUCKGO (Focado em volume - Modo Simples igual ao Teste) ---
    for attempt in range(2):
        try:
            print(f"[SearchEngine] Tentando DuckDuckGo (Tentativa {attempt+1})...")
            from ddgs import DDGS
            with DDGS() as ddgs:
                # Forçamos o backend 'api' para evitar que a biblioteca tente rodar Yahoo/Mojeek
                # que estão bloqueando e causando SSLError/403.
                raw_results = list(ddgs.text(query, region="br-pt", max_results=max_results, backend="api"))
                if raw_results:
                    filtered_results = []
                    for r in raw_results:
                        href = r.get("href", "")
                        if is_company:
                            valid_patterns = ["linkedin.com/company/", "linkedin.com/school/"]
                        else:
                            valid_patterns = ["linkedin.com/in/"]
                            
                        if any(p in href for p in valid_patterns):
                            filtered_results.append(r)
                    
                    if filtered_results:
                        print(f"[SearchEngine] Sucesso (DDG Simples)! {len(filtered_results)} perfis LinkedIn filtrados.")
                        return filtered_results
            
            await asyncio.sleep(2.0)
        except Exception as e:
            print(f"[SearchEngine] Falha no DDG (Tentativa {attempt+1}): {e}")
            await asyncio.sleep(3.0)
            continue

    # --- MOTOR 2: GOOGLE (Last Resort Stealth) ---
    print(f"[SearchEngine] Ativando Motor de Reserva (Google Stealth)...")
    try:
        # Usamos uma técnica de raspagem direta via HTTPX com User-Agent rotativo
        # para evitar detecção imediata.
        headers = {
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.5,en-US;q=0.3",
            "Referer": "https://www.google.com/",
            "Upgrade-Insecure-Requests": "1"
        }
        
        google_url = f"https://www.google.com.br/search?q={urllib.parse.quote(query)}&filter=0"
        async with httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(google_url)
            if resp.status_code == 200:
                html_content = resp.text
                pattern = r'https://[a-z]+\.linkedin\.com/(?:in|company|school)/[a-zA-Z0-9\-_%]+'
                raw_links = re.findall(pattern, html_content)
                
                for link in list(set(raw_links))[:max_results]:
                    results.append({
                        "title": "Perfil LinkedIn",
                        "href": link,
                        "body": "Extraído via Google Stealth",
                        "snippet": "Extraído via Google Stealth"
                    })
                
                if results:
                    print(f"[SearchEngine] Sucesso via Google Stealth! {len(results)} resultados.")
                    return results
            elif resp.status_code == 429:
                print(f"[SearchEngine] Google bloqueou por 429.")
            else:
                print(f"[SearchEngine] Google retornou status {resp.status_code}")
                
    except Exception as e:
        print(f"[SearchEngine] Erro no Google Stealth: {e}")

    return results
