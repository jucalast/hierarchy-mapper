import json
import httpx
import os
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class GroqService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or GROQ_API_KEY
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    async def ask(self, prompt: str, json_mode: bool = False) -> Dict:
        """Envia um prompt para a IA (Gemini como primário, Groq como fallback)."""
        gemini_key = os.getenv("GEMINI_API_KEY")
        
        # 1. TENTA GEMINI (Desejado pelo usuário e superior em lógica)
        if gemini_key:
            try:
                # Usando gemini-2.0-flash para máximo desempenho em lógica
                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                gemini_payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json" if json_mode else "text/plain",
                        "temperature": 0.1
                    }
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(gemini_url, json=gemini_payload)
                    if resp.status_code == 200:
                        content = resp.json()['candidates'][0]['content']['parts'][0]['text']
                        return json.loads(content)
            except Exception as e:
                print(f"[AI Service] Gemini Fallback: {e}")

        # 2. TENTA GROQ (Fallback)
        if not self.api_key:
            return {}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama-3.3-70b-versatile", # Upgrade moral para o fallback
            "messages": [
                {"role": "system", "content": "Você é um assistente B2B preciso. Responda apenas em JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self.base_url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    content = data['choices'][0]['message']['content']
                    return json.loads(content)
                else:
                    print(f"[Groq AI] Erro {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[Groq AI] Exception: {e}")
            
        return {}

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
    Você é um especialista em Estruturas Organizacionais B2B. Sua tarefa é refinar um organograma definindo a senioridade (level) e quem responde a quem (manager_id).

    REGRAS DE senioridade (level):
    6: Sócio / CEO / VP / Board / Fundador.
    5: Diretores / Superintendentes.
    4: Gerentes / Heads / Lead / Gestores / Chefes.
    3: Coordenadores / Supervisores / Especialistas Sêniores / Líderes.
    1: Assistentes / Auxiliares / Estagiários / Operacional.
    2: Analistas / Compradores / Engenheiros / Default (Tudo que não se encaixa acima).

    🛡️ PROTEÇÃO DE SÓCIOS (LEVEL 6):
    - Se um funcionário já possui Level 6 ou pertence ao departamento "Quadro de Sócios (QSA)", ele é IMUTÁVEL. 
    - NUNCA rebaixe o nível de um sócio. 
    - NUNCA subordine um Sócio a outra pessoa que não seja a "root_company".

    REGRAS DE CONEXÃO (manager_id):
    1. PRIORIDADE VERTICAL: Um funcionário deve reportar para alguém de nível SUPERIOR (ex: Nível 2 reporta para 3, 4, 5 ou 6).
    2. PRIORIDADE DEPARTAMENTAL: Busque primeiro um líder no MESMO departamento. 
    3. TRANSVERSALIDADE: Se não houver líder no mesmo departamento, ele deve reportar para a "Diretoria Executiva", "Quadro de Sócios (QSA)" ou "Executive Management".
    4. FALLBACK FINAL: Se não houver nenhum líder humano disponível acima dele, conecte a "root_company".
    5. DISTRIBUIÇÃO: Não sobrecarregue um único gerente se houver outros do mesmo nível e departamento. Distribua os subordinados.

    INSTRUÇÕES - ANÁLISE DE BIO:
    - Use a "bio" para validar se o cargo condiz com a realidade. Se a bio diz "gestor de 20 pessoas" mas o cargo é "Analista", promova para o nível de Gerencial (4).
    
    RETORNO OBRIGATÓRIO:
    - Retorne APENAS o JSON. Use exatamente os IDs enviados.
    - Todo funcionário deve ter um 'manager_id'.

    FUNCIONÁRIOS PARA ANALISAR:
    {json.dumps(employee_data, ensure_ascii=False)}

    FORMATO DE RESPOSTA (JSON):
    {{
      "hierarchy": [
        {{ "id": "...", "level": 4, "manager_id": "...", "role_refinado": "..." }},
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
