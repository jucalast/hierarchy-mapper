import httpx

url = "http://127.0.0.1:8000/api/v1/proxy/image?url=https%3A%2F%2Fusericons.pipedrive.com%2Fprofile_120x120_24921888_23e9baccd306f81d76fc39e3909d2701.jpg"
try:
    resp = httpx.get(url)
    print(f"Proxy Response Status: {resp.status_code}")
    print(f"Proxy Response Headers: {resp.headers}")
    print(f"Content length: {len(resp.content)}")
except Exception as e:
    print(f"Failed to connect to proxy: {e}")
