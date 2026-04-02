from googlesearch import search
import json

try:
    results = list(search('python programming', num_results=5, advanced=True))
    print([r.url for r in results])
except Exception as e:
    print("Error:", e)
