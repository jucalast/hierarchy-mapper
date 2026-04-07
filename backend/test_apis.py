import requests
import json

def test_api(url):
    try:
        print(f"Testing {url}...")
        resp = requests.get(url, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(json.dumps(resp.json(), indent=2))
        else:
            print(resp.text)
    except Exception as e:
        print(f"Error: {e}")

# Test Speedio
test_api("https://api-publica.speedio.com.br/buscarcnpj?cnpj=02948769000161")

# Test CNPJ.ws
test_api("https://publica.cnpj.ws/cnpj/02948769000161")
