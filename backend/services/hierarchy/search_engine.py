import asyncio
import random
import re
import httpx
import urllib.parse
import sys
from typing import List, Dict, Optional
from ddgs import DDGS

async def get_duck_results(query: str, max_results: int = 50, is_company: bool = False) -> List[Dict]:
    """
    Motor DuckDuckGo Otimizado (Modo Lite).
    Focado em evitar bloqueios e silenciar avisos de depreciação.
    """
    # 🛡️ Lista ampliada de User-Agents modernos
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]
    
    # 💤 Delay randômico BASE aumentado significativamente para segurança extrema
    await asyncio.sleep(random.uniform(10.0, 20.0))
    
    # --- RESILIÊNCIA DE REDE ---
    for dns_attempt in range(2):
        try:
            import socket
            socket.gethostbyname('duckduckgo.com')
            break
        except:
            if dns_attempt == 0: await asyncio.sleep(3.0)
            else: return []

    # --- MOTOR PRINCIPAL: DUCKDUCKGO ---
    for attempt in range(4):
        try:
            # Rotaciona User-Agent aleatoriamente
            ua = random.choice(user_agents)
            print(f"[SearchEngine] Tentando DuckDuckGo (Tentativa {attempt+1}/4) com UA: {ua[:30]}...")
            
            # Usamos o backend 'lite' com um timeout generoso de 30s
            with DDGS(timeout=30) as ddgs:
                # O backend 'lite' costuma ser mais resiliente a bloqueios
                raw_results = list(ddgs.text(query, region="br-pt", max_results=max_results, backend="lite"))
                
                if raw_results:
                    filtered_results = []
                    for r in raw_results:
                        href = r.get("href", "")
                        valid_patterns = ["linkedin.com/company/", "linkedin.com/school/"] if is_company else ["linkedin.com/in/"]
                            
                        if any(p in href for p in valid_patterns):
                            filtered_results.append(r)
                    
                    if filtered_results:
                        print(f"[SearchEngine] Sucesso (DDG)! {len(filtered_results)} perfis LinkedIn filtrados.")
                        return filtered_results
                
                print(f"      [DDG] Nenhum resultado. Aguardando pausa...")
                await asyncio.sleep(5.0)
                
        except Exception as e:
            msg = str(e)
            if "429" in msg or "Ratelimit" in msg:
                 print(f"[SearchEngine] 🚨 Bloqueio 429 detectado no DDG.")
            else:
                 print(f"[SearchEngine] Erro no DDG: {msg}")
            
            wait_time = (attempt + 1) * 20 # 20s, 40s, 60s... Progressão mais lenta
            await asyncio.sleep(wait_time)
            continue

    return []
