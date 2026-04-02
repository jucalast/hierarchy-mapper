import json
import httpx
import os
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

async def refine_hierarchy_ai(employees: List[Dict]) -> List[Dict]:
    """
    Usa a IA da Groq (Llama-3-70b/8b) para analisar os cargos e definir uma hierarquia real.
    """
    if not employees:
        return []

    # Prepara a lista simplificada para a IA (economiza tokens)
    employee_data = []
    for emp in employees:
        if emp.get("id") == "root_company": continue
        employee_data.append({
            "id": emp["id"],
            "name": emp["name"],
            "role": emp["role"],
            "level": emp.get("level", 5)
        })

    prompt = f"""
    Você é um especialista em Estruturas Organizacionais B2B.
    Analise os funcionários abaixo e determine os níveis (1-6) e quem reporta a quem (manager_id).

    DIRETRIZES (Tiers):
    6: CEO/Presidente. 5: Diretores. 4: Gerentes. 3: Coordenadores/Supervisores. 2: Analistas Sr/Espec. 1: Operacional/Jr.
    
    REGRAS DE REPORT:
    - Nível 6/5 reportam para "root_company".
    - Nível 4 reporta para 5 ou 6.
    - Nível 3 reporta para 4.
    - Nível 2/1 reportam para 3 ou 4.

    FUNCIONÁRIOS:
    {json.dumps(employee_data, ensure_ascii=False)}

    RETORNE UM OBJETO JSON com a chave "hierarchy" contendo um array:
    {{
      "hierarchy": [
        {{ "id": "...", "level": 4, "manager_id": "..." }},
        ...
      ]
    }}
    """

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "Você é um assistente de RH que gera organogramas e responde apenas em formato JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            
            if response.status_code != 200:
                print(f"[Groq AI] Erro {response.status_code}: {response.text}")
                return []

            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # Limpa possíveis markdown wrappers
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            refined_data = json.loads(content)
            
            # Extração flexível da chave de dados
            if isinstance(refined_data, dict):
                if "hierarchy" in refined_data: return refined_data["hierarchy"]
                if "employees" in refined_data: return refined_data["employees"]
                for key in refined_data:
                    if isinstance(refined_data[key], list): return refined_data[key]
            
            return refined_data if isinstance(refined_data, list) else []
            
    except Exception as e:
        print(f"[Groq AI] Erro na síntese: {str(e)}")
        return []

