import urllib.request
import time

url = "http://127.0.0.1:8000/api/v1/brand/discover?cnpj=71444475000115&stream=true&force=true"
print(f"Requesting stream from {url}...")
start = time.time()
try:
    with urllib.request.urlopen(url, timeout=60) as response:
        print(f"[{time.time() - start:.2f}s] Response status: {response.status}")
        while True:
            line = response.readline()
            if not line:
                break
            print(f"[{time.time() - start:.2f}s] {line.decode('utf-8', errors='ignore').strip()}")
except Exception as e:
    print(f"[{time.time() - start:.2f}s] Request failed: {type(e).__name__}: {e}")
