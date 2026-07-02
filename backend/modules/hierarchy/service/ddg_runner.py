"""
modules.hierarchy.service.ddg_runner
=====================================
Script CLI isolado para executar buscas DuckDuckGo em subprocess separado.

Executado via asyncio.create_subprocess_exec() para isolar o event loop
do duckduckgo_search (incompativel com o loop principal do FastAPI).
Retorna JSON no stdout; erros vao para stderr com sys.exit(1).
"""

import json
import sys

# Aceita os dois nomes de pacote: 'ddgs' (novo) e 'duckduckgo_search' (legado).
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

def main():
    query = sys.argv[1]
    max_results = int(sys.argv[2])
    results = []
    import time
    time.sleep(0.3)  # Pequeno delay tático p/ evitar sequencialismo puro
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, region="br-pt", max_results=max_results))
            for r in raw:
                results.append(r)
        print(json.dumps(results))
    except Exception as e:
        # Erro vai para o stderr
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
