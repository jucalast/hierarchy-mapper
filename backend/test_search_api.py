import httpx
import json

def test_stream_hierarchy():
    cnpj = "07.526.557/0001-00"
    domain = "ambev.com.br"
    url = f"http://127.0.0.1:8000/api/v1/hierarchy/stream?cnpj={cnpj}&domain={domain}"
    
    print(f"Testing streaming hierarchy for CNPJ: {cnpj}")
    
    with httpx.stream("GET", url, timeout=60.0) as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                msg_type = data.get("type")
                if msg_type == "initial":
                    print(f"Initial company data: {data.get('company_name')}")
                    print(f"Nodes found: {len(data.get('nodes'))}")
                elif msg_type == "batch":
                    print(f"Received batch of {len(data.get('nodes'))} nodes")
                    for node in data.get("nodes")[:2]:
                        print(f"  - {node.get('name')} ({node.get('role')})")
                elif msg_type == "done":
                    print("Stream finished.")
                    break
                elif msg_type == "error":
                    print(f"Error: {data.get('message')}")
                    break

if __name__ == "__main__":
    test_stream_hierarchy()
