from duckduckgo_search import DDGS
import json

with DDGS() as ddgs:
    results = list(ddgs.text('python programming', max_results=2))
    print(json.dumps(results, indent=2))
