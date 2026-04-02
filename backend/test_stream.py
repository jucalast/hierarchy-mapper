import time
import requests
import json

def test_hierarchy_stream():
    url = "http://localhost:8000/api/v1/hierarchy/stream?cnpj=07526557000100&domain=ambev.com.br"
    print(f"Buscando stream em: {url}")
    
    start_time = time.time()
    
    try:
        response = requests.get(url, stream=True, timeout=600)
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: '):
                    data = json.loads(decoded_line[6:])
                    print(f"[{time.time() - start_time:.2f}s] Chunk recebido: {data.get('type')} - {len(data.get('nodes', []))} nós")
    except Exception as e:
        print(f"Erro na stream: {e}")

if __name__ == "__main__":
    test_hierarchy_stream()
