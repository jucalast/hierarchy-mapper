"""
Serviço de resolução de dados de empresa via CNPJ.
Implementa uma busca em cascata resiliente em 3 APIs públicas:
1. BrasilAPI
2. Minha Receita
3. ReceitaWS
"""
import httpx
from typing import Optional, Dict, Any


async def fetch_company_data_by_cnpj(cnpj_clean: str) -> Optional[Dict[str, Any]]:
    """
    Busca dados de empresa por CNPJ usando cascata resiliente.
    
    Args:
        cnpj_clean: CNPJ limpo (apenas dígitos, 14 caracteres)
    
    Returns:
        Dict com dados da empresa ou None se todas as APIs falharem.
    """
    data = None
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Camada 1: BRASILAPI
        try:
            resp = await client.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}")
            if resp.status_code == 200:
                data = resp.json()
        except:
            pass
        
        # Camada 2: MINHA RECEITA
        if not data:
            try:
                print(f"[Backend] BrasilAPI Limitada (429) - Tentando Fallback 1: Minha Receita...")
                resp = await client.get(f"https://minhareceita.org/{cnpj_clean}")
                if resp.status_code == 200:
                    data = resp.json()
            except:
                pass
            
        # Camada 3: RECEITAWS
        if not data:
            try:
                print(f"[Backend] Minha Receita Limitada - Tentando Fallback 2: ReceitaWS...")
                resp = await client.get(f"https://receitaws.com.br/v1/cnpj/{cnpj_clean}")
                if resp.status_code == 200:
                    raw = resp.json()
                    data = {
                        "razao_social": raw.get("nome"),
                        "nome_fantasia": raw.get("fantasia"),
                        "municipio": raw.get("municipio"),
                        "uf": raw.get("uf"),
                        "qsa": [{"nome_socio": s.get("nome"), "qualificacao_socio": s.get("qual")} for s in raw.get("qsa", [])]
                    }
            except:
                pass

    return data


def build_full_address(data: Dict[str, Any]) -> str:
    """Compõe endereço completo a partir dos dados da API de CNPJ."""
    if not data:
        return ""
    
    addr_parts = []
    if data.get("logradouro"):
        addr_parts.append(f"{data.get('logradouro')}, {data.get('numero') or 'S/N'}")
    if data.get("complemento"):
        addr_parts.append(str(data.get("complemento")))
    if data.get("bairro"):
        addr_parts.append(str(data.get("bairro")))
    if data.get("municipio"):
        addr_parts.append(f"{data.get('municipio')}-{data.get('uf')}")
    if data.get("cep"):
        addr_parts.append(f"CEP: {data.get('cep')}")
    
    return " | ".join(addr_parts)
