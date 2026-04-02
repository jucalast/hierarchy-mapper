from googlesearch import search
import json

results = list(search('site:linkedin.com/in/ "Ambev" "compras"', num_results=5))
print(json.dumps(results, indent=2))
