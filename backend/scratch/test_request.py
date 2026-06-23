import urllib.request
import urllib.error
import time

url = "http://127.0.0.1:8000/api/v1/brand/discover?cnpj=05753823000108&stream=true"
print(f"Requesting {url} with 60s timeout...")
start_time = time.time()
try:
    with urllib.request.urlopen(url, timeout=60) as response:
        print(f"Response received in {time.time() - start_time:.2f}s. Status Code: {response.status}")
        print("Headers:", dict(response.info()))
        while True:
            chunk = response.read(1024)
            if not chunk:
                break
            print(f"[{time.time() - start_time:.2f}s] Received chunk: {chunk.decode('utf-8', errors='ignore')}")
except Exception as e:
    print(f"[{time.time() - start_time:.2f}s] Error occurred: {type(e).__name__}: {e}")
