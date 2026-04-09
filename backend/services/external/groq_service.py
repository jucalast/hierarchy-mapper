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
            "department": emp.get("department", "Outros"),
            "level": emp.get("level", 5),
            "bio": (emp.get("education", "") or "")[:350] # Reduzi um pouco mais para segurança
        })

    prompt = f"""
    Você é um especialista em Estruturas Organizacionais B2B de grandes empresas multinacionais.
    Sua tarefa é conectar as pontas de um organograma (manager_id) e validar a senioridade (level).

    DIRETRIZES DE SENIORIDADE (level):
    6: CEO/VP/Sócio. 5: Diretores. 4: Gerentes/Heads. 3: Coordenadores/Supervisores (ou Especialistas c/ Gestão). 2: Analistas Sr/Pl/Espec. 1: Operacional/Assistente/Junior.
    
    REGRAS DE OURO PARA RELACIONAMENTOS (manager_id):
    1. DEPARTAMENTO (SILOS): Funcionários de um departamento (ex: TI) devem reportar para um Gerente/Diretor do MESMO departamento ou para "Executive Management".
       - NUNCA faça um 'IT Lead' reportar para um 'Purchasing Coordinator' só porque o Coordenador apareceu primeiro na lista.
    2. HIERARQUIA VERTICAL: Um funcionário Nível N deve reportar para alguém de Nível N+1 ou superior.
       - NUNCA faça um Nível 4 reportar para outro Nível 4.
    3. DISPERSÃO: Evite o erro de "Super-Gerente". Se você tem 20 pessoas e 3 Gerentes de Compras, distribua os Analistas entre esses 3 Gerentes de acordo com a senioridade ou proximidade de cargo, não coloque todos sob uma única pessoa.
    4. FALLBACK: Se um funcionário não tem um líder claro no seu próprio departamento, ele reporta para "Executive Management" ou, em última instância, para "root_company".
    5. RESPEITO ÀS ROLES: Se o cargo é explicitamente "Manager" ou "Gerente", ele deve ser Level 4. Se for "Director", Level 5. Não rebaixe cargos explicitamente citados.

    INSTRUÇÕES - INFERÊNCIA DE SENIORIDADE: 
    - Use a "bio" para confirmar se a pessoa exerce liderança ("managing", "leading", "coordenando", "gestor de equipe"). Se sim, promova para Level 3 ou 4.
    
    RETORNO OBRIGATÓRIO:
    - Retorne APENAS o JSON. Não invente novos IDs. Use exatamente os IDs enviados.
    - Todo funcionário deve ter um 'manager_id' (String).

    FUNCIONÁRIOS PARA ANALISAR:
    {json.dumps(employee_data, ensure_ascii=False)}

    FORMATO DE RESPOSTA (JSON ESTREITO):
    {{
      "hierarchy": [
        {{ "id": "...", "level": 4, "manager_id": "..." }},
        ...
      ]
    }}
    """

    gemini_key = os.getenv("GEMINI_API_KEY")
    content = None

    try:
        import asyncio
        async with httpx.AsyncClient(timeout=60.0) as client:
            
            # 1. TENTA GEMINI (Primário)
            if gemini_key:
                try:
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                    gemini_payload = {
                        "system_instruction": {"parts": [{"text": "Você é um assistente de RH que gera organogramas e responde apenas em formato JSON estrito."}]},
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}
                    }
                    print(f"[Gemini AI] 🧠 Refinando Hierarquia com gemini-2.0-flash...")
                    resp = await client.post(gemini_url, json=gemini_payload)
                    
                    if resp.status_code == 200:
                        content = resp.json()['candidates'][0]['content']['parts'][0]['text']
                    elif resp.status_code == 429:
                        err_msg = resp.json().get("error", {}).get("message", "Quota Exceeded")
                        print(f"[Gemini AI] Rate limit atingido ({err_msg}). Indo para Groq Fallback...")
                    else:
                        print(f"[Gemini AI] Erro {resp.status_code}: {resp.text[:200]}. Indo para Groq Fallback...")
                except Exception as e:
                    print(f"[Gemini AI] Exceção: {e}. Indo para Groq Fallback...")

            # 2. TENTA GROQ (Fallback) se Gemini falhar
            if not content:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                target_model = "llama-3.1-8b-instant"
                payload = {
                    "model": target_model,
                    "messages": [
                        {"role": "system", "content": "Você é um assistente de RH que gera organogramas e responde apenas em formato JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
                print(f"[Groq AI] 🧠 Refinando Hierarquia com {target_model}...")
                for attempt in range(2):
                    response = await client.post(url, headers=headers, json=payload)
                    
                    if response.status_code == 429:
                        print(f"[Groq AI] Rate limit atingido. Aguardando 15s para re-tentativa (Tentativa {attempt+1}/2)...")
                        await asyncio.sleep(15)
                        continue

                    if response.status_code != 200:
                        print(f"[Groq AI] Erro {response.status_code}: {response.text}")
                        return []

                    result = response.json()
                    content = result['choices'][0]['message']['content']
                    break
                else:
                    return []
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

async def expand_product_to_b2b_terms(product_focus: str) -> List[str]:
    """
    Usa IA para traduzir um produto genérico em termos técnicos de compras B2B.
    Ex: "Caixas" -> ["Packaging", "Embalagens", "Indirects", "Suprimentos"]
    """
    if not product_focus or len(product_focus) < 2:
        return []

    prompt = f"""
    Traduza o foco de busca "{product_focus}" em 4 termos técnicos em inglês e português que um comprador (Procurement) usaria no LinkedIn para se descrever ou descrever sua categoria.
    
    Exemplo: "Papelão" -> ["Packaging", "Embalagens", "Indirects", "Supply Chain"]
    Exemplo: "Segurança" -> ["Loss Prevention", "Prevenção de Perdas", "Facilities", "Indiretos"]
    Exemplo: "Sistemas" -> ["IT Procurement", "SaaS", "Indirects", "Hardware"]

    RETORNE APENAS UM ARRAY JSON SIMPLE DE STRINGS: ["Termo1", "Termo2", "Termo3", "Termo4"]
    """

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "Você é um especialista em Compras e Procurement B2B. Responda apenas com um array JSON de strings."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data['choices'][0]['message']['content']
                # Tenta extrair a lista do JSON (a IA pode mandar {"terms": [...]})
                parsed = json.loads(content)
                if isinstance(parsed, list): return parsed
                if isinstance(parsed, dict):
                    for k in parsed:
                        if isinstance(parsed[k], list): return parsed[k]
    except Exception as e:
        print(f"[Groq B2B] Erro na tradução: {e}")
    
    return [product_focus] # fallback
