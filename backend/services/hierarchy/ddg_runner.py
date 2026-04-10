
import json
import sys
from duckduckgo_search import DDGS

def main():
    query = sys.argv[1]
    max_results = int(sys.argv[2])
    results = []
    import time
    time.sleep(1.0) # Delay tático p/ evitar sequencialismo puro
    try:
        # Tenta usar a biblioteca com o padrão estável se possível
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, region="br-pt", max_results=max_results))
            for r in raw:
                # Simplificação para o dumper
                results.append(r)
        print(json.dumps(results))
    except Exception as e:
        # Erro vai para o stderr
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
