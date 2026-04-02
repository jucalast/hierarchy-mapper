from duckduckgo_search import DDGS
import json

with DDGS(timeout=20) as ddgs:
    results = list(ddgs.text('site:linkedin.com/in/ "Ambev" "compras"', max_results=5))
    print(json.dumps(results, indent=2))
