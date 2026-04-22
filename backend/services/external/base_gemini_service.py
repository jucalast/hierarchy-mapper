import json
import httpx
import asyncio
import time
from typing import Dict, Union
from core.config import settings

# ============================================================
# CIRCUIT BREAKER: Estado global de rate-limit do Gemini
# Quando qualquer modelo retorna 429, TODOS os modelos Gemini
# são pulados por um período de cooldown, indo direto ao Groq.
# ============================================================
_gemini_circuit_open = False          # True = Gemini bloqueado
_gemini_circuit_open_until = 0.0      # Timestamp até quando está bloqueado
_gemini_consecutive_failures = 0      # Conta falhas consecutivas para escalar cooldown
_GEMINI_BASE_COOLDOWN = 60            # Cooldown inicial: 60 segundos
_GEMINI_MAX_COOLDOWN = 300            # Cooldown máximo: 5 minutos

def _is_gemini_available() -> bool:
    """Verifica se o circuit breaker do Gemini permite tentativas."""
    global _gemini_circuit_open, _gemini_circuit_open_until
    if not _gemini_circuit_open:
        return True
    if time.time() >= _gemini_circuit_open_until:
        # Cooldown expirou, podemos tentar novamente
        _gemini_circuit_open = False
        print(f"[Circuit Breaker] Cooldown do Gemini expirou. Reabilitando tentativas...")
        return True
    remaining = int(_gemini_circuit_open_until - time.time())
    print(f"[Circuit Breaker] Gemini bloqueado por rate limit. Pulando direto para Groq. ({remaining}s restantes)")
    return False

def _trip_gemini_circuit():
    """Ativa o circuit breaker do Gemini quando recebemos 429."""
    global _gemini_circuit_open, _gemini_circuit_open_until, _gemini_consecutive_failures
    _gemini_consecutive_failures += 1
    # Cooldown escalonado: 60s, 120s, 180s, 240s, 300s (max)
    cooldown = min(_GEMINI_BASE_COOLDOWN * _gemini_consecutive_failures, _GEMINI_MAX_COOLDOWN)
    _gemini_circuit_open = True
    _gemini_circuit_open_until = time.time() + cooldown
    print(f"[Circuit Breaker] Gemini rate-limited! Circuit breaker ATIVADO por {cooldown}s (falha consecutiva #{_gemini_consecutive_failures})")

def _reset_gemini_circuit():
    """Reseta o circuit breaker quando Gemini responde com sucesso."""
    global _gemini_circuit_open, _gemini_consecutive_failures
    if _gemini_consecutive_failures > 0:
        print(f"[Circuit Breaker] Gemini respondeu com sucesso! Resetando contador de falhas.")
    _gemini_circuit_open = False
    _gemini_consecutive_failures = 0


async def ask_gemini(prompt: str, json_mode: bool = False, max_retries: int = 2, history: list = None) -> Union[str, Dict]:
    gemini_key = settings.GEMINI_API_KEY
    groq_key = settings.GROQ_API_KEY
    
    if not gemini_key and not groq_key:
        print("[AI Service] Nenhuma API key configurada (GEMINI_API_KEY / GROQ_API_KEY)!")
        return {} if json_mode else ""
    
    # --- FORMATAÇÃO DO HISTÓRICO PARA GEMINI ---
    gemini_contents = []
    if history:
        for msg in history:
            # Garante que tratamos tanto dict quanto objeto Pydantic
            msg_role = msg.role if hasattr(msg, "role") else msg.get("role")
            msg_content = msg.content if hasattr(msg, "content") else msg.get("content", "")
            
            role = "model" if msg_role == "assistant" else "user"
            if msg_content:
                gemini_contents.append({"role": role, "parts": [{"text": msg_content}]})
    
    # Adiciona a mensagem atual
    gemini_contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "contents": gemini_contents,
        "generationConfig": {
            "responseMimeType": "application/json" if json_mode else "text/plain",
            "temperature": 0.1
        }
    }
    
    models_to_try = [
        ("gemini-flash-latest", f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={gemini_key}"),
        ("gemini-2.5-flash", f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"),
        ("gemini-3-flash-preview", f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={gemini_key}")
    ]
    
    groq_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant"
    ]

    async with httpx.AsyncClient(timeout=45.0) as client:
        # ============================================
        # Loop 1: Gemini (somente se circuit breaker permite)
        # ============================================
        if gemini_key and _is_gemini_available():
            gemini_failed_all = True
            for model_name, url in models_to_try:
                try:
                    resp = await client.post(url, json=payload)
                    
                    if resp.status_code == 200:
                        _reset_gemini_circuit()
                        gemini_failed_all = False
                        data = resp.json()
                        text_content = data['candidates'][0]['content']['parts'][0]['text']
                        if json_mode:
                            try:
                                return json.loads(text_content)
                            except json.JSONDecodeError:
                                return {"response": text_content}
                        return text_content
                        
                    elif resp.status_code == 429:
                        print(f"[Gemini API] Rate Limit (429) em {model_name}. Tentando próximo...")
                        await asyncio.sleep(1) # Pequeno fôlego
                        continue
                        
                    elif resp.status_code in [503, 404]:
                        print(f"[Gemini API Aviso] Erro {resp.status_code} em {model_name}. Tentando próximo...")
                        continue
                        
                    else:
                        print(f"[Gemini API Erro] {model_name} retornou {resp.status_code}: {resp.text[:200]}")
                        continue
                        
                except Exception as e:
                    print(f"[Gemini Falha de Conexão] {model_name}: {str(e)}")
                    continue
            
            # Se chegamos aqui e nenhum Gemini funcionou
            if gemini_failed_all:
                _trip_gemini_circuit()
        
        # ============================================
        # Loop 2: Groq Fallback
        # ============================================
        if groq_key:
            print(f"[Groq Fallback] Acionando Groq como fallback...")
            groq_url = "https://api.groq.com/openai/v1/chat/completions"
            
            # --- FORMATAÇÃO DO HISTÓRICO PARA GROQ ---
            groq_messages = []
            if history:
                for msg in history:
                    # Garante que tratamos tanto dict quanto objeto Pydantic
                    msg_role = msg.role if hasattr(msg, "role") else msg.get("role")
                    msg_content = msg.content if hasattr(msg, "content") else msg.get("content", "")
                    
                    # Groq usa 'assistant', não 'model'
                    groq_messages.append({"role": msg_role, "content": msg_content})
            
            # Adiciona a mensagem atual
            groq_messages.append({"role": "user", "content": prompt})

            for groq_model in groq_models:
                groq_payload = {
                    "model": groq_model,
                    "messages": groq_messages,
                    "temperature": 0.1
                }
                if json_mode:
                    groq_payload["response_format"] = {"type": "json_object"}
                    # Insere o sistema no início
                    groq_payload["messages"].insert(0, {"role": "system", "content": "Você é uma IA analítica. Por favor, forneça a saída estritamente em um JSON válido."})

                try:
                    groq_resp = await client.post(
                        groq_url, 
                        json=groq_payload, 
                        headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                    )
                    
                    if groq_resp.status_code == 200:
                        groq_data = groq_resp.json()
                        text_content = groq_data["choices"][0]["message"]["content"]
                        if json_mode:
                            try:
                                return json.loads(text_content)
                            except json.JSONDecodeError:
                                return {"response": text_content}
                        return text_content
                        
                    elif groq_resp.status_code == 429:
                        wait_time = 5
                        print(f"[Groq API Aviso] Rate limit 429 em {groq_model}. Aguardando {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        continue
                        
                    else:
                        print(f"[Groq Fallback] {groq_model} retornou {groq_resp.status_code}: {groq_resp.text[:200]}")
                        continue
                        
                except Exception as ge:
                    print(f"[Groq Falha de Conexão] {groq_model}: {ge}")
                    continue
                        
    print("[Erro Final AI] Absolutamente todas as opções falharam e esgotaram.")
    return {} if json_mode else "Desculpe, ocorreu um erro de cota ou indisponibilidade ao consultar a Inteligência Artificial."
