import httpx
import json
import os
import re
import unicodedata
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class RoleEngine:
    def __init__(self):
        self.api_key = GROQ_API_KEY
        self.model = "llama-3.1-8b-instant"
        self.cache = {}

    def _is_junk_slogan(self, text: str) -> bool:
        """Detecta frases de efeito que não são cargos reais."""
        junk_patterns = [
            r"apaixonado por", r"proud to be", r"building the future", r"focado em resultados",
            r"transforming the", r"shaping the", r"building a", r"pioneering",
            r"creative solutions", r"innovation for", r"driving excellence"
        ]
        text_norm = text.lower()
        if any(re.search(p, text_norm) for p in junk_patterns):
            return True
        if re.search(r"\b(venha|conheça|descubra|veja|assista|leia|participe|junte-se)\b", text_norm):
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
            "comprador", "buyer", "procurement", "supply", "logistica", "manager", "gerente", 
            "diretor", "analista", "almoxarifado", "almoxarife", "compras", "pcp", "sourcing",
            "suprimentos", "demand planner", "estoquista", "operador logistico", "coordenador"
        ]
        
        for kw in kws:
            if kw in t:
                # Tenta extrair a frase ao redor da keyword
                match = re.search(fr"([^|,-]*{kw}[^|,-]*)", t)
                if match:
                    return match.group(1).strip().title()
                return t.split("|")[0].split("-")[0].strip().title()
                
        return "Profissional B2B" # Fallback mais elegante que "Não Identificado"

    async def distill_role(self, name: str, company: str, texts: List[str], product_focus: Optional[str] = None) -> dict:
        """Usa a Groq AI para extrair e validar o cargo de forma estruturada."""
        if not texts: texts = ["No context available"]
        
        cache_key = f"{name}_{company}_{product_focus}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        clean_sources = [re.sub(r'<[^>]*>', ' ', t).strip() for t in texts if t]
        combined_text = " | ".join(clean_sources)
        combined_text = re.sub(r'\s+', ' ', combined_text)[:4000]
        
        if self.api_key:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    prompt = (
                        f"Analyze the LinkedIn evidence for {name} at {company}.\n"
                        f"CONTEXT SOURCES:\n"
                        f"1. {clean_sources[0] if clean_sources else 'N/A'}\n"
                        f"2. {clean_sources[1] if len(clean_sources) > 1 else 'N/A'}\n\n"
                        f"CRITICAL RULES (PARSER MODE):\n"
                        f"1. WHITELIST (Approve only if evidence matches): Purchasing, Compras, Sourcing, Supply Chain, Logistics, Warehouse, PCP, PPCP, Comex, Procurement, Suprimentos, Almoxarifado.\n"
                        f"2. MANDATORY REJECTION (is_valid: False): Product Manager, Engenheiro (unless PCP), Produção, Qualidade, Quality, Sales, Vendas, Comercial, Marketing, HR, RH, Finance, IT, Operador, Moldes, Injeção, Técnico.\n"
                        f"3. EVIDENCE TRAP: You MUST return a field 'evidence' with a literal quote. If the quote does NOT contain at least one word from the WHITELIST, you MUST set is_valid: False.\n"
                        f"4. ZERO ASSUMPTION: If the text only shows 'Experience at {company}', return is_valid: False. Do not guess.\n\n"
                        f"RETURN ONLY JSON:\n"
                        f"{{ \"clean_name\": \"...\", \"role\": \"...\", \"department\": \"...\", \"is_valid\": bool, \"evidence\": \"literal quote\", \"reason\": \"...\", \"matching_score\": 0-100 }}\n"
                    )
                    
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
            "seniority": 1, 
            "is_valid": True,
            "reason": "Fallback (IA indisponível)"
        }
        self.cache[cache_key] = res
        return res

role_engine = RoleEngine()
