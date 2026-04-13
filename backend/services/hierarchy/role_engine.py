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
        
        # ⚠️ TABELA DE VETO CATEGÓRICO (Para evitar alucinações de 'Sales' em 'Purchasing')
        self.FORBIDDEN_KEYWORDS = {
            "compras": ["sales", "vendas", "comercial", "production", "produção", "operation", "operador", "rh", "hr", "marketing", "atendimento", "customer"],
            "logistica": ["rh", "hr", "marketing", "vendas", "sales", "financeiro", "accounting"]
        }

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

    def apply_fidelity_guard(self, ai_role: str, mechanical_role: str, brand: str = "") -> str:
        """Impede que a IA ignore um cargo real em favor de rótulos genéricos OU nomes de empresa."""
        if not ai_role:
            return mechanical_role or "Professional"
            
        ai_role_low = str(ai_role).lower().strip()
        generic_labels = ["professional", "employee", "pioneer", "profile", "member", "não identificado", "unidentified", "b2b profile"]
        
        # 🛡️ FIX #2: Detecta quando a IA retorna um nome de empresa como cargo
        # Ex: "Bayer", "Philip Morris", "Böttcher Brasil" não são cargos
        known_company_suffixes = ["ltda", "s.a.", "gmbh", "inc", "corp", "group", "international", "brasil", "brazil"]
        if brand:
            brand_slug = self.slugify_lenient(brand)
            role_slug = self.slugify_lenient(ai_role)
            # Se o "cargo" for >= 60% similar ao nome da marca, é alucinação
            import difflib
            similarity = difflib.SequenceMatcher(None, role_slug, brand_slug).ratio()
            if similarity > 0.5:
                print(f"      [Fidelity Guard] 🛡️ BLOQUEIO: '{ai_role}' é nome de empresa (sim={similarity:.0%}), restaurando '{mechanical_role}'")
                return mechanical_role if mechanical_role != "Não Identificado" else "Professional"
        
        # 🛡️ FIX EXTRA: Se o cargo for uma única palavra que compõe o nome da marca, bloqueie
        brand_words = [self.slugify_lenient(w) for w in brand.split() if len(w) > 3]
        if ai_role_low in brand_words and len(ai_role_low.split()) == 1:
            print(f"      [Fidelity Guard] 🛡️ BLOQUEIO: '{ai_role}' é parte do nome da marca, não um cargo.")
            return mechanical_role if mechanical_role != "Não Identificado" else "Professional"

        # Detecta sufixos corporativos no "cargo" (ex: "Bayer", "Philip Morris International")
        if any(sfx in ai_role_low for sfx in known_company_suffixes) or (len(ai_role_low.split()) <= 2 and ai_role_low[0].isupper() and not any(c in ai_role_low for c in ["gerente", "manager", "buyer", "comprador", "analista", "diretor", "coordenador", "supervisor", "head"])):
            # Verifica se parece um nome próprio/empresa (sem termos funcionais)
            functional_terms = ["gerente", "manager", "buyer", "comprador", "compradora", "analista", "analyst",
                               "diretor", "director", "coordenador", "coordinator", "supervisor", "head", "lead",
                               "specialist", "especialista", "assistente", "assistant", "engenheiro", "engineer",
                               "consultor", "consultant", "planejador", "planner", "officer", "procurement",
                               "sourcing", "supply", "logistic", "compras", "purchasing"]
            if not any(ft in ai_role_low for ft in functional_terms):
                return mechanical_role if mechanical_role != "Não Identificado" else "Professional"

        if mechanical_role == "Não Identificado":
            return ai_role
        
        # Se a IA deu algo genérico ou muito curto e o mecânico é bom
        if any(g == ai_role_low for g in generic_labels) or (len(ai_role_low) < 4 and len(mechanical_role) > 5):
            return mechanical_role
            
        return ai_role

    async def distill_role(self, name: str, company: str, context: List[str], product_focus: str = None, area_focus: str = "compras", target_location: str = "Brasil") -> Dict:
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

        # --- ETAPA 0: O SNIPER (EXTRAÇÃO E MAPEAMENTO) ---
        # 🛡️ FIX #3: Extrai cargo mecânico como fallback ANTES da IA
        mechanical_fallback_role = self.extract_mechanical_title(
            " | ".join(context), " ".join(context), company
        )
        
        prompt_cleaner = f"""
Você é um Sniper de Metadados B2B. Sua missão é extrair o NOME REAL e o CARGO REAL de uma pessoa no meio do ruído de snippets de busca.

TEXTO BRUTO: {" ".join(context)}
NOME SUSPEITO (Pode estar errado): {name}
EMPRESA DO ALVO: {company}

TAREFA:
1. Identifique o NOME REAL PRÓPRIO da pessoa. Frequentemente o nome que recebemos é apenas um cargo (ex: "Comprador na ABB").
   - Procure por padrões como "Veja o perfil de [NOME] no LinkedIn" ou "[NOME] postou isso" ou "[NOME] - LinkedIn".
   - Se o nome suspeito '{name}' for claramente um cargo, IGNORE-O e extraia o nome real do texto.
2. Identifique todos os cargos/funções associados à essa pessoa.
3. O cargo DEVE ser uma função profissional (ex: Gerente, Comprador, Supervisor, Head of Production).
4. **REGRA DE OURO (VETO):** NUNCA use o nome da empresa '{company}' ou variações dela como sendo o cargo. 
5. **NOMES DE EMPRESAS NÃO SÃO CARGOS.** "Bayer", "Philip Morris", "Böttcher Brasil" são EMPRESAS. Se só encontrar empresa, use "Não Identificado".

Responda APENAS JSON:
{{
  "all_mappings": [ {{ "name": "string", "role": "string" }} ],
  "target_profile": {{
     "proper_name": "Nome Real da Pessoa (Ex: João Silva)",
     "detected_role": "Cargo Funcional Isolado (Ex: Comprador Senior)",
     "clean_bio": "Breve bio sem ruidos"
  }}
}}
"""
        # 🛡️ FIX #3: Sniper resiliente com fallback granular
        try:
            clean_data = await self.groq.ask(prompt_cleaner, json_mode=True)
            if not clean_data or 'target_profile' not in clean_data:
                raise ValueError("Sniper retornou resposta vazia ou sem target_profile")
        except Exception as sniper_err:
            print(f"      [Sniper] ⚠️ Falha na higienização ({sniper_err}). Usando fallback mecânico.")
            clean_data = {
                "target_profile": {
                    "name": name,
                    "detected_role": mechanical_fallback_role,
                    "clean_bio": " ".join(context)[:500]
                },
                "all_mappings": [{"name": name, "role": mechanical_fallback_role}]
            }
        
        # Substituímos o contexto original pelo contexto higienizado para as próximas etapas
        # 🛡️ Incluímos dados brutos originais como referência de backup para o Detetive
        sanitized_context = [
            f"Nome: {clean_data['target_profile'].get('proper_name', name)}",
            f"Empresa Alvo: {company}",
            f"Bio Higienizada: {clean_data['target_profile'].get('clean_bio', '')}",
            f"Cargo Detectado: {clean_data['target_profile'].get('detected_role', '')}",
            f"Outras pessoas mapeadas no mesmo snippet: {json.dumps(clean_data.get('all_mappings', []))}",
            f"[DADOS BRUTOS ORIGINAIS (BACKUP)]: {' | '.join(context)[:800]}"
        ]

        # Log de debug interno
        print(f"      [Sniper] 🎯 Alvo: {name} | Cargo Detectado: {clean_data['target_profile'].get('detected_role')}")

        # --- ETAPA 1: O DETETIVE (EXTRAÇÃO DE EVIDÊNCIAS) ---
        prompt_detective = f"""
Você é um Detetive Forense. Sua missão é confirmar se os dados higienizados sustentam que '{name}' trabalha na '{company}'.

DADOS HIGIENIZADOS:
{" ".join(sanitized_context)}

⚠️ ALERTA DE ALUCINAÇÃO:
- Se o sobrenome de '{name}' for igual a '{company}', NÃO assuma que ele trabalha lá apenas pelo nome.
- Procure por menções EXPLÍCITAS de vínculo profissional atual.
- Se os dados mencionarem outra empresa (Ex: Bosch, Volkswagen), o vínculo com '{company}' é DUVIDOSO.

Responda APENAS JSON:
{{
  "bio_raw": "Citação direta do cargo ou empresa",
  "snippets": ["Frases que confirmam o vínculo"],
  "employer_found": bool (A empresa {company} foi confirmada?),
  "is_institutional": bool (O texto original parece de uma página institucional?)
}}
"""
        facts = await self.groq.ask(prompt_detective, json_mode=True)
        
        # --- ETAPA 2: O ESPECIALISTA DE RH (REFINO DE CARGO E DEPARTAMENTO) ---
        area_label = "SUPRIMENTOS / COMPRAS / PROCUREMENT" if area_focus == "compras" else "LOGÍSTICA / SUPPLY CHAIN"
        forbidden_list = self.FORBIDDEN_KEYWORDS.get(area_focus, [])
        forbidden = ", ".join(forbidden_list)
        
        # 🛡️ FIX #1: Injeta resultado do Detetive no Especialista (Cascata de Dados)
        detective_employer_status = "CONFIRMADO" if facts.get('employer_found') else "NÃO CONFIRMADO / TRABALHA EM OUTRA EMPRESA"
        detective_is_institutional = "SIM (Perfil de página corporativa)" if facts.get('is_institutional') else "NÃO"
        
        prompt_specialist = f"""
Você é um Especialista de RH Sênior em Recrutamento Técnico de {area_label}.
Analise o perfil técnico de '{name}' para a empresa '{company}'.

DADOS DO CANDIDATO (CONTEXTO ISOLADO):
{" ".join(sanitized_context)}

⚠️ RESULTADO DO DETETIVE (ETAPA ANTERIOR — RESPEITE!):
- Vínculo com {company}: {detective_employer_status}
- Perfil Institucional: {detective_is_institutional}
- Snippets do Detetive: {json.dumps(facts.get('snippets', []))}

INSTRUÇÕES TÉCNICAS:
1. EXTRAIA O CARGO: Use o 'Cargo Detectado' do Sniper como base, mas refine se a 'Bio Higienizada' trouxer mais detalhes.
2. **REGRA CRÍTICA:** Se o Detetive disse que o vínculo com {company} é "NÃO CONFIRMADO", você DEVE definir is_relevant como false. Não adianta o cargo ser bom se a pessoa NÃO trabalha na empresa alvo.
3. AVALIE RELEVÂNCIA: Determine se este cargo pertence ou tem interface direta com {area_label}.
4. **LOGÍSTICA vs COMPRAS:** No foco COMPRAS, aceite perfis de Logística/Supply Chain se eles tiverem interface com fornecedores ou materiais.
5. **VETO ABSOLUTO:** Rejeite Vendas, Marketing, Financeiro, RH, Jurídico e Produção Direta.
6. Se o cargo contiver "{forbidden}", is_relevant DEVE SER 'false'.
7. **NOMES DE EMPRESAS NÃO SÃO CARGOS.** Se o 'Cargo Detectado' for um nome de empresa (Ex: "Bayer", "Philip Morris"), trate como "Não Identificado".

Responda APENAS JSON:
{{ 
  "role_name": "Cargo Real Extraído", 
  "dept": "Departamento Sugerido", 
  "is_relevant": bool,
  "reasoning": "Breve explicação da decisão técnica"
}}
"""
        role_info = await self.groq.ask(prompt_specialist, json_mode=True)

        # --- ETAPA 3: O JUIZ (VEREDITO FINAL) ---
        # Verificação mecânica prévia para o Juiz não alucinar
        mechanical_veto = False
        role_lower = str(role_info.get('role_name', '')).lower()
        if any(f in role_lower for f in forbidden_list):
            mechanical_veto = True

        prompt_judge = f"""
Você é o Juiz Final da Qualificação B2B. Sua missão é barrar qualquer falso positivo.
CANDIDATO: '{name}' na '{company}'

DADOS RECEBIDOS:
- Especialista diz: {role_info.get('role_name')} | Dept: {role_info.get('dept')} | Relevante: {role_info.get('is_relevant')}
- Detetive encontrou: {json.dumps(facts)}
- Etapa 0 (Original): {json.dumps(clean_data['target_profile'])}
- Veto Mecânico Detectado: {mechanical_veto}

CONSTITUIÇÃO (REGRAS CRÍTICAS - SIGA À RISCA):
1. **TRAVA DE SOBRENOME:** Se o candidato tem o mesmo sobrenome da empresa mas o Detetive/Sniper indica TRABALHO EM OUTRA EMPRESA (Ex: Bosch), você **DEVE REJEITAR** (is_valid=false). 
2. **FILTRO DE RELEVÂNCIA (MANDATÓRIO):** Se o Especialista marcou "is_relevant: false", você **DEVE REJEITAR** (is_valid=false). Não importa se o cargo parece bom, se não for relevante para o foco, barque.
3. **VETO DE MARCA:** Se o "Cargo Final" for igual ao nome da empresa "{company}", você **DEVE REJEITAR** ou corrigir para um cargo funcional. NUNCA aprove um nó onde o cargo é apenas o nome da empresa.
4. **VETO DE DEPARTAMENTO:** Se o departamento for Vendas ou RH e o foco for Compras, **REJEITE**.
5. **FORA DA LOCALIZAÇÃO:** Se o candidato estiver claramente fora de {target_location}, **REJEITE**.

Responda APENAS JSON:
{{
  "is_valid": bool,
  "proper_name": "Nome Real Corrigido pela IA",
  "role": "Cargo Funcional Padronizado (Ex: Diretor de Suprimentos)",
  "matching_score": 0-100,
  "department": "Departamento Final",
  "evidence": "Explicação curta do veredito"
}}
"""
        try:
            verdict = await self.groq.ask(prompt_judge, json_mode=True)
            verdict["facts"] = facts
            verdict["proper_name"] = verdict.get("proper_name") or clean_data['target_profile'].get('proper_name', name)
            verdict["clean_data"] = clean_data # Inserimos os dados da Etapa 0
            verdict["specialist"] = role_info # Dados do estágio 3 (RH)
            return verdict
        except Exception as e:
            print(f"      [RoleEngine] Error in Chain: {e}")
            return {"is_valid": True, "role": "Colaborador", "matching_score": 50, "department": area_focus.capitalize()}

    async def distill_roles_batch(self, candidates: List[Dict], company: str, product_focus: str = None, area_focus: str = "compras", target_location: str = "Brasil") -> Dict[int, Dict]:
        """Processa múltiplos candidatos em uma única chamada de IA para economizar cota."""
        if not self.groq:
            return {c['idx']: {"is_valid": True, "role": "Professional", "matching_score": 50} for c in candidates}

        batch_str = ""
        for c in candidates:
            batch_str += f"ID {c['idx']} | NAME: {c['name']} | CONTEXT: {' | '.join(c['context'])}\n"

        prompt = f"""
Analise este lote de candidatos para a empresa '{company}'.
Foco: {area_focus.upper()} ({product_focus or 'Geral'})
Localização Alvo: {target_location}

REGRAS ESTREITAS: 
- Queremos apenas pessoas de {area_focus.upper()}.
- Vendas (Sales/Key Account), RH, Marketing e Atendimento NÃO são {area_focus.upper()}. Marque is_valid=false para estes casos.
- LOCALIZAÇÃO: Se o perfil indicar claramente que a pessoa está fora de {target_location}, marque is_valid=false.

LOTE:
{batch_str}

Para cada ID, decida se é do departamento de {area_focus.upper()} e qual o cargo.
Responda APENAS um JSON com os IDs como chaves:
{{ "0": {{"is_valid": bool, "role": "string", "matching_score": int}}, ... }}
"""
        try:
            response = await self.groq.ask(prompt, json_mode=True)
            return response
        except Exception as e:
            print(f"      [RoleEngine] Batch Error: {e}")
            return {c['idx']: {"is_valid": True, "role": "Professional"} for c in candidates}

role_engine = RoleEngine()
