import requests

cnpj = '17832664000110'
url = f'https://brasilapi.com.br/api/cnpj/v1/{cnpj}'

response = requests.get(url)
if response.status_code == 200:
    data = response.json()
    print(f"Nome da Empresa: {data.get('razao_social')}")
    print(f"Telefone principal: {data.get('ddd_telefone_1')}")
    print(f"Telefone secundário: {data.get('ddd_telefone_2')}")
else:
    print(f"Erro na requisição. Status: {response.status_code}")
    print(response.text)
