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
    
    # Delay inicial curto para não sobrecarregar em chamadas paralelas
    await asyncio.sleep(random.uniform(1.5, 3.5))

    # --- RESILIÊNCIA DE REDE ---
    for dns_attempt in range(2):
        try:
            import socket
            socket.gethostbyname('duckduckgo.com')
            break
        except:
            if dns_attempt == 0: await asyncio.sleep(2.0)
            else: return []

    # --- MOTOR PRINCIPAL: DUCKDUCKGO ---
    consecutive_403 = 0
    for attempt in range(4):
        try:
            ua = random.choice(user_agents)
            print(f"[SearchEngine] Tentando DuckDuckGo (Tentativa {attempt+1}/4) com UA: {ua[:30]}...")

            with DDGS(timeout=20) as ddgs:
                raw_results = list(ddgs.text(query, region="br-pt", max_results=max_results, backend="lite"))

                if raw_results:
                    valid_patterns = ["linkedin.com/company/", "linkedin.com/school/"] if is_company else ["linkedin.com/in/"]
                    filtered = [r for r in raw_results if any(p in r.get("href", "") for p in valid_patterns)]
                    if filtered:
                        print(f"[SearchEngine] Sucesso (DDG)! {len(filtered)} perfis LinkedIn filtrados.")
                        return filtered

                await asyncio.sleep(2.0)

        except Exception as e:
            msg = str(e)
            is_403 = "403" in msg or "Forbidden" in msg
            is_429 = "429" in msg or "Ratelimit" in msg

            if is_403:
                consecutive_403 += 1
                print(f"[SearchEngine] Bloqueio 403 (tentativa {attempt+1}) — IP bloqueado.")
                # Após 2 bloqueios 403 seguidos, desiste imediatamente (retry não resolve)
                if consecutive_403 >= 2:
                    print(f"[SearchEngine] 2 bloqueios 403 consecutivos — encerrando busca.")
                    return []
                await asyncio.sleep(3.0)
            elif is_429:
                consecutive_403 = 0
                print(f"[SearchEngine] 🚨 Rate limit 429 — aguardando {(attempt+1)*8}s.")
                await asyncio.sleep((attempt + 1) * 8)  # 8s, 16s, 24s, 32s
            else:
                consecutive_403 = 0
                print(f"[SearchEngine] Erro no DDG: {msg}")
                await asyncio.sleep(4.0)
            continue

    return []
