import httpx
import json
import os
import re
import unicodedata
import asyncio
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class RoleEngine:
    def __init__(self):
        self.api_key = GROQ_API_KEY
        self.model = "llama-3.1-8b-instant"
        self.cache = {}
        self.gemini_disabled = False # Trava de cota diária
        self.last_gemini_check = 0 # Unix time do último teste de saúde
        self.gemini_ok = True # Cache do status de saúde

    async def proactive_health_check(self) -> bool:
        """Verifica proativamente se o Gemini está online e com cota."""
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key or self.gemini_disabled:
            return False
            
        import time
        now = time.time()
        # Se checou nos últimos 10 minutos e estava OK, assume que continua OK
        if now - self.last_gemini_check < 600 and self.gemini_ok:
            return True
            
        self.last_gemini_check = now
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                smoke_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                smoke_payload = {"contents": [{"parts": [{"text": "hi"}]}], "generationConfig": {"maxOutputTokens": 1}}
                smoke_resp = await client.post(smoke_url, json=smoke_payload)
                if smoke_resp.status_code == 429:
                    print("      [RoleEngine] 🚨 Gemini sem cota (Checagem Proativa). Usando Groq direto.")
                    self.gemini_disabled = True
                    return False
                elif smoke_resp.status_code != 200:
                    self.gemini_ok = False
                    return False
                else:
                    self.gemini_ok = True
                    self.gemini_disabled = False
                    return True
        except Exception:
            self.gemini_ok = False
            return False

    def _is_junk_slogan(self, text: str) -> bool:
        """Detecta frases de efeito e boilerplate de SEO que não são cargos reais."""
        junk_patterns = [
            r"apaixonado por", r"proud to be", r"building the future", r"focado em resultados",
            r"transforming the", r"shaping the", r"building a", r"pioneering",
            r"creative solutions", r"innovation for", r"driving excellence",
            r"veja o perfil", r"está no linkedin", r"visualizar perfil", r"entre para ver",
            r"trajetória no setor", r"com o coração cheio", r"grande jornada",
            r"desenvolvi uma sólida", r"experiência como", r"profissional com \d+",
            r"brasil \. \d+", r"conexões no linkedin", r"formação acadêmica",
            r"atuei um pouco", r"meu nome é"
        ]
        text_norm = text.lower()
        if any(re.search(p, text_norm) for p in junk_patterns):
            return True
        if re.search(r"\b(venha|conheça|descubra|veja|assista|leia|participe|junte-se|ver|conferir)\b", text_norm):
            return True
        return False

    def _clean_raw_name(self, name: str) -> str:
        n = str(name).split(" - ")[0].split(" | ")[0].split(" : ")[0].split(" · ")[0]
        n = re.sub(r'([a-z])([A-Z])', r'\1 \2', n)
        parts = n.split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[1]}".title()
        return n.title()

    def _clean_raw_title(self, name: str, company: str, title_bruto: str) -> str:
        t = str(title_bruto).lower()
        t = t.replace(name.lower(), "").strip()
        t = t.replace(company.lower(), "").strip()
        t = t.replace("| linkedin", "").strip()
        
        # 🛡️ DICIONÁRIO DE CARGOS B2B (REFORÇADO)
        kws = [
            "comprador", "compradora", "buyer", "procurement", "supply", "logistica", "logística", 
            "manager", "gerente", "diretor", "analista", "analyst", "sourcing", "purchas",
            "suprimentos", "demand planner", "category manager", "coordenador", "head", "lead",
            "strategic buyer", "technical buyer", "cpo", "csco", "coo", "operations", "operacoes",
            "expedição", "estoque", "almoxarifado", "frota", "transporte", "distribution", "pcp"
        ]
        
        for kw in kws:
            if kw in t:
                # Tenta extrair a frase ao redor da keyword
                match = re.search(fr"([^|,-]*{kw}[^|,-]*)", t)
                if match:
                    return match.group(1).strip().title()
                return t.split("|")[0].split("-")[0].strip().title()
                
        return "Não Identificado" # Forçamos a falha para disparar a repescagem profunda

    async def distill_role(self, name: str, company: str, texts: List[str], product_focus: Optional[str] = None, target_company: Optional[str] = None, area_focus: Optional[str] = "compras") -> dict:
        """Usa a Groq AI para extrair e validar o cargo de forma estruturada."""
        if not texts: texts = ["No context available"]
        
        target = target_company or company
        cache_key = f"{name}_{target}_{product_focus}_{area_focus}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        clean_sources = [re.sub(r'<[^>]*>', ' ', t).strip() for t in texts if t]
        
        if self.api_key or os.getenv("GEMINI_API_KEY"):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    distilled_raw = None
                    gemini_key = os.getenv("GEMINI_API_KEY")
                    
                    prompt = (
                        f"INVESTIGATION TARGET: {name} at {target}.\n"
                        f"AREA OF FOCUS: {area_focus.upper()}\n"
                        f"CONTEXT SOURCES:\n"
                        f"1. {clean_sources[0] if clean_sources else 'N/A'}\n"
                        f"2. {clean_sources[1] if len(clean_sources) > 1 else 'N/A'}\n\n"
                        f"STRICT VALIDATION RULES:\n"
                        f"- Rule NO_BOILERPLATE: NEVER return titles starting with 'Brasil...', 'Veja...', 'Experience...', 'Profissional com...'.\n"
                        f"- Rule CLEAN_TITLE: Extract ONLY the functional job title (e.g. 'Senior Buyer'). If the context combines multiple people, isolate the title of {name} only.\n"
                        f"- Rule ENTITY_ANCHORING: Candidate MUST work at {target}.\n"
                        f"- Rule GENERIC_TITLES: Reject if role is 'Professional', 'Employee', or just the name of the company '{target}'.\n"
                        f"- Area Focus ({area_focus}): This is the MANDATORY department.\n"
                        f"- Product Focus ({product_focus}): PRIORITY but NOT exclusion.\n"
                        f"- Validation: Reject if from Finance, IT, HR, Sales, or Accounting.\n"
                        f"5. CONFIDENCE SCAN: Calculate 'matching_score' (0-100). If weak, score < 40 and is_valid: False.\n"
                        f"6. SENIORITY (1-6): 6=C-Level, 5=Director, 4=Manager/Head, 3=Coord/Sup, 2=Senior/Analyst/Buyer, 1=Assistant/Intern.\n\n"
                        f"RETURN ONLY JSON:\n"
                        f"{{ \"clean_name\": \"...\", \"role\": \"...\", \"department\": \"...\", \"is_valid\": bool, \"evidence\": \"short quote\", \"reason\": \"...\", \"seniority\": int, \"matching_score\": int }}\n"
                    )

                    # 1. TENTA GEMINI (Primário) - Respeita a trava de cota
                    if gemini_key and not self.gemini_disabled:
                        for attempt in range(2):
                            try:
                                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                                gemini_payload = {
                                    "system_instruction": {"parts": [{"text": "Você é um especialista em recrutamento técnico para Supply Chain. Seja extremamente rigoroso e responda apenas com JSON válido."}]},
                                    "contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0}
                                }
                                resp = await client.post(gemini_url, json=gemini_payload)
                                
                                if resp.status_code == 200:
                                    distilled_raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
                                    break
                                elif resp.status_code == 503 and attempt == 0:
                                    print(f"      [RoleEngine] ⏳ Gemini instável (503). Retentando em 2s...")
                                    await asyncio.sleep(2)
                                    continue
                                elif resp.status_code == 429:
                                    err_msg = resp.json().get("error", {}).get("message", "Quota Exceeded")
                                    print(f"      [RoleEngine] 🚨 Gemini sem cota ({err_msg}). Acionando Groq...")
                                    self.gemini_disabled = True
                                    break
                                else:
                                    print(f"      [RoleEngine] Gemini falhou ({resp.status_code}: {resp.text[:200]}). Acionando Groq...")
                                    break
                            except Exception as e:
                                print(f"      [RoleEngine] Exceção Gemini: {e}")
                                break

                    # 2. TENTA GROQ (Fallback) se Gemini falhar
                    if not distilled_raw and self.api_key:
                        print(f"      [RoleEngine] ⚡ Acionando Groq para análise individual de: {name}...")
                        resp = await client.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            headers={"Authorization": f"Bearer {self.api_key}"},
                            json={
                                "model": self.model,
                                "messages": [
                                    {"role": "system", "content": "Você é um especialista em recrutamento técnico para Supply Chain. Seja extremamente rigoroso e responda apenas com JSON."},
                                    {"role": "user", "content": prompt}
                                ],
                                "response_format": {"type": "json_object"},
                                "temperature": 0.0
                            }
                        )
                        if resp.status_code == 200:
                            distilled_raw = resp.json()['choices'][0]['message']['content']

                    if distilled_raw:
                        # Extrai JSON caso o modelo tenha cuspido markdown markdown block
                        if "```json" in distilled_raw:
                            distilled_raw = distilled_raw.split("```json")[-1].split("```")[0].strip()
                        
                        distilled = json.loads(distilled_raw)
                        
                        if distilled and isinstance(distilled, dict):
                            if "clean_name" not in distilled or len(distilled["clean_name"]) < 3:
                                distilled["clean_name"] = self._clean_raw_name(name)
                            
                            self.cache[cache_key] = distilled
                            return distilled

            except Exception as e:
                print(f"      [RoleEngine] Erro IA: {e}")

        # Fallback
        clean_name = self._clean_raw_name(name)
        role = self._clean_raw_title(name, company, texts[0] if texts else "")
        res = {
            "clean_name": clean_name,
            "role": role, 
            "department": "Operations", 
            "seniority": 2, 
            "is_valid": True,
            "reason": "Fallback (IA indisponível)"
        }
        self.cache[cache_key] = res
        return res

    async def distill_roles_batch(self, candidates: List[dict], company: str, product_focus: Optional[str] = None, area_focus: Optional[str] = "compras") -> dict:
        """Processa dezenas de perfis em 1 request. candidatos = [{'idx': 0, 'name': '...', 'context': [...]}]"""
        if not candidates: return {}
        
        prompt = f"INVESTIGATION MISSION: Validate {len(candidates)} profiles for company '{company}' (Focus: {area_focus.upper()}).\n\n"
        for c in candidates:
            clean_sources = [re.sub(r'<[^>]*>', ' ', t).strip() for t in c.get("context", []) if t]
            prompt += f"--- TARGET {c['idx']} ---\nName: {c['name']}\nContext Snippet: {' | '.join(clean_sources)[:700]}\n\n"
            
        prompt += (
            f"STRICT VALIDATION RULES (APPLIED TO ALL):\n"
            f"1. ENTITY ANCHOR: Candidates MUST currently work at '{company}'.\n"
            f"2. FORBIDDEN TITLES: NEVER approve or return generic roles like 'Professional', 'Employee', 'Experienced', 'B2B Professional', or just '{company}'.\n"
            f"3. CLEAN TITLES: Extract ONLY the job title (e.g. 'Senior Buyer'). If Google snippet shows multiple people, focus ONLY on the target person's name as provided. NEVER return 'Brasil...', 'Veja o perfil...', or fragments of other people's titles.\n"
            f"4. NO BOILERPLATE: NEVER return text like 'Experienced in...', '8 years of...', 'Law 8666...', or 'Great journey'.\n"
            f"5. AREA FOCUS ({area_focus.upper()}): Mandatory department.\n"
            f"6. HARD REJECTION: Reject from Finance, IT, HR, Legal, Facilities, or Production.\n"
            f"7. CONFIDENCE SCAN: matching_score (0-100).\n"
            f"8. SENIORITY (1-6).\n\n"
            f"RETURN ONLY THIS EXACT JSON FORMAT:\n"
            f"{{ \"results\": [ {{ \"id\": 0, \"clean_name\": \"...\", \"role\": \"...\", \"department\": \"...\", \"is_valid\": bool, \"evidence\": \"literal quote\", \"reason\": \"...\", \"seniority\": int, \"matching_score\": int }} ] }}"
        )

        distilled_raw = None
        gemini_key = os.getenv("GEMINI_API_KEY")

        if self.api_key or gemini_key:
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    # Log correto dependendo do status do Gemini
                    if not self.gemini_disabled and self.gemini_ok:
                        print(f"      [RoleEngine Batch] 📦 Processando {len(candidates)} perfis em lote no Gemini...")
                    else:
                        print(f"      [RoleEngine] ⚡ Redirecionando {len(candidates)} perfis direto para o Groq (Gemini Offline).")

                    # 1. TENTA GEMINI (Se passar no Health Check)
                    # O Smoke Test já foi feito proativamente ou será feito aqui se necessário
                    if gemini_key and not self.gemini_disabled and self.gemini_ok:
                        for attempt in range(2):
                            try:
                                gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                                gemini_payload = {
                                    "system_instruction": {"parts": [{"text": "Você é um especialista B2B rigoroso. Responda apenas com JSON."}]},
                                    "contents": [{"parts": [{"text": prompt}]}],
                                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0}
                                }
                                resp = await client.post(gemini_url, json=gemini_payload)
                                if resp.status_code == 200:
                                    distilled_raw = resp.json()['candidates'][0]['content']['parts'][0]['text']
                                    break
                                elif resp.status_code == 503 and attempt == 0:
                                    print(f"      [RoleEngine Batch] ⏳ Gemini instável (503). Retentando em 2s...")
                                    await asyncio.sleep(2)
                                    continue
                                elif resp.status_code == 429:
                                    err_msg = resp.json().get("error", {}).get("message", "Quota Exceeded")
                                    print(f"      [RoleEngine Batch] 🚨 COTA DIÁRIA EXCEDIDA NO GEMINI ({err_msg}). Desativando Gemini para esta sessão.")
                                    self.gemini_disabled = True # TRAVA ATIVADA
                                    break
                                else:
                                    print(f"      [RoleEngine Batch] Gemini falhou ({resp.status_code}: {resp.text[:200]}). Acionando Groq...")
                                    break
                            except Exception as e:
                                print(f"      [RoleEngine Batch] Exceção Gemini: {e}")
                                break

                    # 2. TENTA GROQ (INDIVIDUALMENTE OU EM LOTES DE 2)
                    if not distilled_raw and self.api_key:
                        print(f"      [RoleEngine Fallback] 🕵️ Desmembrando lote ({len(candidates)} perfis) para processamento individual no Groq...")
                        final_map = {}
                        
                        for c in candidates:
                            print(f"      [Groq Individual] 🕵️ Analisando perfil: {c['name']}...")
                            try:
                                # Prompt simplificado para 1 única pessoa (mais preciso no Groq)
                                clean_context = [re.sub(r'<[^>]*>', ' ', t).strip() for t in c.get("context", []) if t]
                                single_prompt = (
                                    f"Analyze this LinkedIn profile for the company {company}:\n"
                                    f"Name: {c['name']}\n"
                                    f"METADATA & SNIPPETS:\n{' | '.join(clean_context)[:2000]}\n\n"
                                    f"CRITICAL RULES (STRICT MODE):\n"
                                    f"1. MANDATORY BLACKLIST (REJECT): Sales, Vendas, Marketing, HR, RH, Finance, Accounting, IT, Software, Engineering (unless PCP), Production, Quality, Legal.\n"
                                    f"2. WHITELIST (APPROVE): Only if the role is clearly Purchasing, Compras, Sourcing, Supply Chain, Logistics, PCP, Comex, Procurement, Buyer.\n"
                                    f"3. UNCERTAIN/GENERIC ROLES: If you see 'Employee', 'Professional' or just 'Experience' without a department, set is_valid: False AND set reason to 'Insufficient role information for B2B validation'. This will trigger a deep research phase.\n"
                                    f"4. CLEAN TITLE RULE: Return ONLY the functional role title (e.g., 'Category Manager'). NEVER include 'At Knorr', 'Knorr-Bremse', or similar branding phrases in the role field.\n"
                                    f"5. TASK: If it is BLACKLIST, set is_valid: False and specify the department as the reason (e.g. 'Department: Sales').\n"
                                    f"RETURN ONLY JSON: {{ \"is_valid\": bool, \"clean_name\": \"...\", \"role\": \"...\", \"seniority\": int(1-6), \"evidence\": \"...\", \"department\": \"Operations\", \"reason\": \"...\" }}\n"
                                )
                                
                                resp = await client.post(
                                    "https://api.groq.com/openai/v1/chat/completions",
                                    headers={"Authorization": f"Bearer {self.api_key}"},
                                    json={
                                        "model": "llama-3.1-8b-instant",
                                        "messages": [{"role": "user", "content": single_prompt}],
                                        "response_format": {"type": "json_object"},
                                        "temperature": 0.0
                                    }
                                )
                                
                                if resp.status_code == 200:
                                    res_data = resp.json()['choices'][0]['message']['content']
                                    res_json = json.loads(res_data)
                                    # Usa o ID real do loop (c['idx']) para evitar confusão da IA
                                    final_map[c['idx']] = res_json
                            except Exception as e:
                                print(f"      [RoleEngine Fallback] Erro no perfil {c['idx']} via Groq: {e}")
                        
                        if final_map:
                            return final_map

                    if distilled_raw:
                        # Processamento do lote vindo do Gemini
                        if "```json" in distilled_raw:
                            distilled_raw = distilled_raw.split("```json")[-1].split("```")[0].strip()
                        elif "```" in distilled_raw:
                            distilled_raw = distilled_raw.split("```")[1].strip()
                        
                        distilled_json = json.loads(distilled_raw)
                        final_map = {}
                        for item in distilled_json.get("results", []):
                            if "id" in item:
                                final_map[item["id"]] = item
                        return final_map

            except Exception as e:
                print(f"      [RoleEngine Batch] Erro IA: {e}")

        return {}

role_engine = RoleEngine()
