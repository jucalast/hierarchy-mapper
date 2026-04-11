import re
import html
import random
import os
import json
import asyncio
from typing import List, Dict, Optional
from services.external.groq_service import GroqService

# Reusing the Groq API key from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class RoleEngine:
    def __init__(self):
        self.groq = GroqService() if GROQ_API_KEY else None

    async def proactive_health_check(self):
        """Verifica se a cota do Gemini/Groq está OK."""
        print("      [RoleEngine] 🛡️ Verificando integridade dos motores de decisão...")
        # Lógica simples de verificação pode ser adicionada aqui

    def slugify_lenient(self, text: str) -> str:
        """Normalização para matching de nomes de empresas."""
        return re.sub(r'[^a-z0-9]', '', text.lower())

    def extract_mechanical_title(self, title: str, body: str, brand: str) -> str:
        """
        Extração pura baseada em padrões de texto (Fidelidade Máxima).
        Tenta isolar o cargo sem depender de IA.
        """
        # Limpa sufixos do LinkedIn
        t = re.sub(r' \| LinkedIn$', '', title, flags=re.I)
        t = re.sub(r' - LinkedIn$', '', t, flags=re.I)
        
        brand_slug = self.slugify_lenient(brand)
        
        # 1. Tenta por separadores no Título Google
        separators = [r' - ', r' \| ', r' : ']
        for sep in separators:
            p = re.split(sep, t)
            if len(p) > 1:
                potential = p[1].split(' | ')[0].strip()
                if len(potential) > 3: 
                    # Se o que achamos for o nome da empresa, ignoramos como cargo
                    if self.slugify_lenient(potential) not in [brand_slug]:
                        return potential.title()

        # 2. Tenta por padrões no Snippet (Bio)
        bio_lower = body.lower()
        patterns = [
            r"(?:atualmente |hoje |sou |atuo como )([^.!,·]*?)(?: na | da | em | na empresa|!|\.|\,)",
            r"([^.!,·]*?)\s+(?:comprador|compradora|gerente|analista|assistente|diretor|coordenador|supervisor|estagiário)"
        ]
        for pat in patterns:
            m = re.search(pat, bio_lower)
            if m:
                role_candidate = m.group(0).strip(" .!,")
                if len(role_candidate) > 4 and len(role_candidate) < 50:
                    # Verifica se o candidato não é a própria marca
                    if self.slugify_lenient(role_candidate) != brand_slug:
                        return role_candidate.title()
                        
        return "Não Identificado"

    def apply_fidelity_guard(self, ai_role: str, mechanical_role: str) -> str:
        """Impede que a IA ignore um cargo real em favor de rótulos genéricos."""
        if mechanical_role == "Não Identificado":
            return ai_role
            
        ai_role_low = ai_role.lower().strip()
        generic_labels = ["professional", "employee", "pioneer", "profile", "member", "não identificado", "unidentified", "b2b profile"]
        
        # Se a IA deu algo genérico ou muito curto e o mecânico é bom
        if any(g == ai_role_low for g in generic_labels) or (len(ai_role_low) < 4 and len(mechanical_role) > 5):
            print(f"      [Fidelity Guard] 🛡️ Restaurando cargo real '{mechanical_role}' (ia quis '{ai_role}')")
            return mechanical_role
            
        return ai_role

    async def distill_role(self, name: str, company: str, context: List[str], product_focus: str = None, area_focus: str = "compras") -> Dict:
        """Motor de Decisão em Cadeia (Especializado): Detetive -> Especialista -> Juiz."""
        if not self.groq:
            return {"is_valid": True, "role": "Professional", "matching_score": 50, "department": area_focus.upper()}

        # 🛡️ TRAVA DE SEGURANÇA: Veto Mecânico de Perfis Institucionais (Fuzzy)
        def clean_cmp(s): return re.sub(r'[^a-z0-9]', '', s.lower())
        name_pure = clean_cmp(name)
        brand_pure = clean_cmp(company)
        company_suffixes = ["technologies", "technology", "ltda", "systems", "solutions", "servicos", "services", "industria", "comercio"]
        if any(sfx in name.lower() for sfx in company_suffixes):
            import difflib
            if difflib.SequenceMatcher(None, name_pure, brand_pure).ratio() > 0.7:
                 return {"is_valid": False, "role": "Perfil Institucional", "matching_score": 0, "department": "N/D", "evidence": "VETO FUZZY: Perfil de empresa."}

        # --- ETAPA 1: O DETETIVE (EXTRAÇÃO DE EVIDÊNCIAS) ---
        prompt_detective = f"""
Você é um Detetive Forense. Extraia apenas fatos do contexto abaixo sobre '{name}' na '{company}'.
CONTEXTO: {" ".join(context)}

Responda APENAS JSON:
{{
  "bio_raw": "Citação direta do cargo na bio",
  "snippets": ["Lista de frases curtas que mencionam cargo ou departamento"],
  "employer_found": "Empresa mencionada como atual",
  "is_institutional": bool (este texto é de uma página de empresa/robô?)
}}
"""
        facts = await self.groq.ask(prompt_detective, json_mode=True)
        
        # --- ETAPA 2: O ESPECIALISTA DE RH (REFINO DE CARGO E DEPARTAMENTO) ---
        area_label = "SUPRIMENTOS / COMPRAS" if area_focus == "compras" else "LOGÍSTICA / SUPPLY CHAIN"
        
        prompt_specialist = f"""
Baseado nos fatos sobre '{name}', qual o CARGO PROFISSIONAL EXATO dele na '{company}'?
FOCO ESTRATÉGICO: {area_label} (Específico: {product_focus or 'Geral'})

REGRAS:
- Seja técnico (Ex: Comprador, Coordenador Logístico, Diretor de Supply Chain).
- NUNCA use o nome da empresa '{company}' como o cargo.
- Se o cargo for passado, use 'Ex-colaborador'.
- RELEVÂNCIA: O cargo pertence ou atende à área de {area_label}? (Sim/Não).

Responda APENAS JSON:
{{ "role_name": "Cargo Extraído", "dept": "Departamento", "is_relevant": bool }}
"""
        role_info = await self.groq.ask(prompt_specialist, json_mode=True)

        # --- ETAPA 3: O JUIZ (VEREDITO FINAL) ---
        prompt_judge = f"""
Decida o veredito final para '{name}' na empresa '{company}'.
DADOS:
- RH diz: {role_info.get('role_name')} ({role_info.get('dept')}) | Relevante: {role_info.get('is_relevant')}
- Detetive encontrou: {json.dumps(facts)}

REGRAS DE OURO:
1. EMPRESA: is_valid=false se não trabalhar na '{company}'.
2. DEPARTAMENTO: is_valid=false se 'is_relevant' for false. Queremos apenas pessoas de {area_label}.
3. INSTITUIÇÃO: is_valid=false se 'is_institutional' for true.
4. matching_score: 0-100 baseado na clareza do cargo e vínculo.

Responda APENAS JSON:
{{
  "is_valid": bool,
  "role": "Cargo Final",
  "matching_score": 0-100,
  "department": "Departamento Final",
  "evidence": "Foco {area_focus.upper()}: [Motivo da aprovação ou rejeição técnica]"
}}
"""
        try:
            verdict = await self.groq.ask(prompt_judge, json_mode=True)
            return verdict
        except Exception as e:
            print(f"      [RoleEngine] Error in Chain: {e}")
            return {"is_valid": True, "role": "Colaborador", "matching_score": 50, "department": area_focus.capitalize()}

    async def distill_roles_batch(self, candidates: List[Dict], company: str, product_focus: str = None, area_focus: str = "compras") -> Dict[int, Dict]:
        """Processa múltiplos candidatos em uma única chamada de IA para economizar cota."""
        if not self.groq:
            return {c['idx']: {"is_valid": True, "role": "Professional", "matching_score": 50} for c in candidates}

        batch_str = ""
        for c in candidates:
            batch_str += f"ID {c['idx']} | NAME: {c['name']} | CONTEXT: {' | '.join(c['context'])}\n"

        prompt = f"""
Analise este lote de candidatos para a empresa '{company}'.
Foco: {area_focus.upper()} ({product_focus or 'Geral'})

LOTE:
{batch_str}

Para cada ID, decida se é do departamento de {area_focus.upper()} e qual o cargo.
Responda APENAS um JSON com os IDs como chaves:
{{ "0": {{"is_valid": bool, "role": "string", "matching_score": int}}, ... }}
"""
        try:
            from services.external.groq_service import GroqService
            groq = GroqService()
            response = await groq.ask(prompt, json_mode=True)
            return response
        except Exception as e:
            print(f"      [RoleEngine] Batch Error: {e}")
            return {c['idx']: {"is_valid": True, "role": "Professional"} for c in candidates}

role_engine = RoleEngine()
