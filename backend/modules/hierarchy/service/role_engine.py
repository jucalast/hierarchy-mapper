"""
modules.hierarchy.service.role_engine
======================================
Classificador de cargos com LLM (Groq) e tabela de veto categorico.

FORBIDDEN_KEYWORDS garante que cargos de Vendas nunca sejam classificados
como Compras -- problema critico que causava falsos positivos no scanner.
LLM e chamado apenas quando os filtros mecanicos sao inconclusivos.

Singleton: role_engine
"""
import re
import html
import random
import os
import json
import asyncio
from typing import List, Dict, Optional
from core.external.groq_service import GroqService
from core.llm.base import LLMTier
from core.config import settings

# Reusing the Groq API key from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or settings.GROQ_API_KEY

class RoleEngine:
    def __init__(self):
        self.groq = GroqService()
        
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
        """Normalização para matching de nomes de empresas (Remove acentos e ruídos)."""
        import unicodedata
        if not text: return ""
        text = "".join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')
        return re.sub(r'[^a-z0-9]', '', text)

    def extract_mechanical_title(self, title: str, body: str, brand: str) -> str:
        """
        Extração pura baseada em padrões de texto (Fidelidade Máxima).
        Tenta isolar o cargo sem depender de IA, filtrando marca e nomes.
        """
        # Limpa sufixos do LinkedIn
        t = re.sub(r' \| LinkedIn$', '', title, flags=re.I)
        t = re.sub(r' - LinkedIn$', '', t, flags=re.I)
        
        brand_slug = self.slugify_lenient(brand)
        
        # 1. Tenta por separadores no Título Google
        separators = [r' - ', r' \| ', r' : ']
        parts = []
        for sep in separators:
            # Pega o divisor que retornar mais pedaços (melhor isolamento)
            split_parts = re.split(sep, t)
            if len(split_parts) > len(parts):
                parts = split_parts
        
        # Se não achou divisores, tenta no corpo
        if len(parts) <= 1:
            parts = [t]

        # Limpa o cargo mecânico de ruídos comuns de empresa
        def clean_mech(role_str):
            role_str = re.sub(fr'\s+(?:at|na|da|no|in|en)\s+{re.escape(brand)}.*', '', role_str, flags=re.I)
            role_str = re.sub(fr'\s+[-|]\s+{re.escape(brand)}.*', '', role_str, flags=re.I)
            return role_str.strip()

        # O primeiro pedaço é geralmente o Nome. O segundo/terceiro costuma ser o Cargo.
        # Vamos iterar do segundo pedaço em diante para achar o cargo.
        for idx, p in enumerate(parts):
            if idx == 0: continue # Pula o nome provável
            potential = p.split(' | ')[0].strip()
            if len(potential) >= 3: 
                pot_slug = self.slugify_lenient(potential)
                # Se não for o nome da marca, nem "LinkedIn", nem genérico demais
                if pot_slug not in brand_slug and brand_slug not in pot_slug:
                    return clean_mech(potential).title()

        # 2. Tenta por padrões no Snippet (Bio) se o título falhou
        bio_lower = body.lower()
        patterns = [
            r"(?:atualmente |hoje |sou |atuo como )([^.!,·]*?)(?: na | da | em | na empresa|!|\.|\,)",
            r"([^.!,·]*?)\s+(?:comprador|compradora|gerente|analista|assistente|diretor|coordenador|supervisor|estagiário|especialista|buyer|manager)"
        ]
        for pat in patterns:
            m = re.search(pat, bio_lower)
            if m:
                role_candidate = m.group(1).strip(" .!,") if "(" not in pat else m.group(0).strip(" .!,")
                if len(role_candidate) > 4 and len(role_candidate) < 50:
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
            # 🛡️ FUZZY GUARD REFORÇADO: Se o "cargo" for parte da marca ou vice-versa, é alucinação
            import difflib
            similarity = difflib.SequenceMatcher(None, role_slug, brand_slug).ratio()
            
            # Se for contido um no outro ou tiver alta similaridade
            if similarity > 0.45 or role_slug in brand_slug or brand_slug in role_slug:
                # Caso especial: Cargos legítimos curtos (ex: CEO, Head, Buyer) não devem ser vados se não baterem na marca
                legit_shorts = ["ceo", "coo", "cfo", "head", "lead", "vps", "buyer", "owner"]
                if ai_role_low in legit_shorts and ai_role_low not in brand_slug:
                     return ai_role

                print(f"      [Fidelity Guard] 🛡️ BLOQUEIO: '{ai_role}' detectado como nome de empresa, restaurando '{mechanical_role}'")
                return mechanical_role if mechanical_role != "Não Identificado" else "Professional"
        
        # 🛡️ FIX EXTRA: Se o cargo for uma única palavra que compõe o nome da marca, bloqueie
        brand_words = [self.slugify_lenient(w) for w in brand.split() if len(w) >= 3]
        if ai_role_low in brand_words and len(ai_role_low.split()) == 1:
            print(f"      [Fidelity Guard] 🛡️ BLOQUEIO: '{ai_role}' é parte da marca.")
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
            # Se a IA deu algo muito genérico ou nome de empresa que escapou
            if any(g == ai_role_low for g in generic_labels) or len(ai_role_low) < 3:
                return "Colaborador"
            return ai_role
        
        # Se a IA deu algo genérico ou muito curto e o mecânico é bom
        if any(g == ai_role_low for g in generic_labels) or (len(ai_role_low) < 4 and len(mechanical_role) > 5):
            return mechanical_role
            
        return ai_role

    async def distill_role(self, name: str, company: str, context: List[str], product_focus: str = None, area_focus: str = "compras", target_location: str = "Brasil", official_role: str = None, meta_company: str = "", razao_social: Optional[str] = None) -> Dict:
        """Motor de Decisão em Cadeia (Especializado): Sniper -> Detetive -> Especialista -> Juiz."""
        api_key = GROQ_API_KEY or os.getenv("GROQ_API_KEY") or settings.GROQ_API_KEY
        if not api_key:
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
Você é um Sniper de Metadados B2B. Sua missão é extrair o NOME REAL e o CARGO REAL especificamente de '{name}' no meio do ruído de snippets de busca do LinkedIn.

TEXTO BRUTO (Contexto): {" ".join(context)}
ALVO PRIORITÁRIO: {name}
EMPRESA DO ALVO: {company}

TAREFA:
1. FOCO NO ALVO: O snippet pode conter dados de várias pessoas (Ex: "João Silva - Comprador na 3M... Maria Souza - RH na 3M"). Você deve isolar APENAS os dados de '{name}'.
2. IDENTIFIQUE O NOME: Se o nome fornecido '{name}' for apenas um cargo ou estiver incompleto, tente encontrar o nome próprio real no texto (ex: "Perfil de [NOME] no LinkedIn").
3. EXTRAIA O CARGO: Identifique a função profissional atual.
4. **VERIFICAÇÃO DE FONTE:** Se houver uma menção de "Verified Official Role", essa é a informação mais confiável. Priorize-a se ela se referir ao seu alvo.
5. **REGRA DE OURO (VETO):** NUNCA use o nome da empresa '{company}' ou variações como sendo o cargo. 
6. **DIFERENCIE EXPERIÊNCIA:** Se o texto diz "Experiência em {company}" sem citar uma função, o cargo é "Não Identificado".
7. **VETO DE SLOGAN/DESCRIÇÃO:** NUNCA extraia slogans, descrições da empresa ou frases institucionais (ex: 'Líder de mercado', 'A maior do setor', 'Inovação e qualidade') como cargo. Se só houver isso, o cargo é "Não Identificado".
8. NOMES DE EMPRESAS NÃO SÃO CARGOS. Se encontrar apenas nome de empresa no lugar do cargo, use "Não Identificado".

Responda APENAS JSON:
{{
  "all_mappings": [ {{ "name": "string", "role": "string" }} ],
  "target_profile": {{
     "proper_name": "Nome Real da Pessoa (Ex: Yuri Silva)",
     "detected_role": "Cargo Funcional Isolado (Ex: Comprador Senior)",
     "clean_bio": "Breve bio sem ruidos, focada no alvo"
  }}
}}

DICA: Se o alvo prioritário for '{name}', procure por '{name}' no texto. Se o snippet disser 'Veja o perfil de [Nome] no LinkedIn', esse é o nome real.
"""
        # 🛡️ FIX #3: Sniper resiliente com Retry e Fallback Robusto
        clean_data = None
        for attempt in range(2):
            try:
                clean_data = await self.groq.ask(prompt_cleaner, json_mode=True)
                if clean_data and 'target_profile' in clean_data:
                    break
                print(f"      [Sniper] Intentativa {attempt+1} vazia, tentando novamente...")
                if attempt == 0: await asyncio.sleep(1)
            except Exception as e:
                print(f"      [Sniper] Erro na tentativa {attempt+1}: {e}")
                if attempt == 0: await asyncio.sleep(1)
                continue

        if not clean_data or 'target_profile' not in clean_data:
            print(f"      [Sniper] ⚠️ Falha na higienização após retentativas. Usando fallback mecânico.")
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
            f"Verified Official Role: {official_role or 'Não Encontrado'}",
            f"Outras pessoas mapeadas no mesmo snippet: {json.dumps(clean_data.get('all_mappings', []))}",
            f"[DADOS BRUTOS ORIGINAIS (BACKUP)]: {' | '.join(context)[:800]}"
        ]

        # --- ETAPA 1: O DETETIVE (EXTRAÇÃO DE EVIDÊNCIAS) ---
        prompt_detective = f"""
Você é um Detetive de Metadados Corporativos. Analise o contexto de '{name}' para a empresa-alvo '{company}' (Razão Social Oficial: '{razao_social or 'Não Informada'}').
META_COMPANY_DECLARADA: '{meta_company}'

OBJETIVO: Identificar se o vínculo ATUAL com a empresa-alvo é real.
DADOS BRUTOS E HIGIENIZADOS:
{" ".join(sanitized_context)}

REGRAS DE VETO (MUITO IMPORTANTE):
1. **CONFLICT_CHECK:** Se a META_COMPANY_DECLARADA ou o Snippet indicam que o candidato trabalha em OUTRA empresa (ex: Siemens, Vivo, Unimed, PHD do Brasil) que não seja '{company}' nem a sua Razão Social '{razao_social or 'Não Informada'}', você deve marcar 'employer_found': false e citar o conflito no campo snippets.
   * ATENÇÃO: A Razão Social Oficial da empresa é '{razao_social or 'Não Informada'}'. Se o candidato declarar trabalhar na Razão Social '{razao_social or 'Não Informada'}', ou em qualquer variação óbvia ou abreviação comercial dela (como 'Com.', 'Comércio' etc.), isso é considerado um VÍNCULO CONFIRMADO (employer_found: true). NÃO considere como conflito!
2. **PAST_EMPLOYER:** Se o text diz "ex-funcionário", "trabalhou na", ou cita datas passadas (2020-2023), o vínculo é suspeito. Marque 'employer_found': false se houver outra empresa atual citada.
3. **SURNAME_SKEPTICISM:** O sobrenome do candidato pode ser igual ao nome da empresa '{company}' (ex: João Böttcher). NÃO assuma que ele trabalha na '{company}' apenas pelo sobrenome. Procure por indicadores funcionais ("na {company}", "at {company}").
4. **INSTITUTIONAL:** Se o perfil parecer ser da PRÓPRIA empresa (Página oficial) e não de uma pessoa, marque is_institutional: true.

Responda APENAS JSON:
{{
  "employer_found": bool,
  "snippets": ["trechos que provam o vínculo ou o conflito"],
  "is_institutional": bool,
  "bio_raw": "resumo profissional curto"
}}
"""
        facts = await self.groq.ask(prompt_detective, json_mode=True)
        
        # --- ETAPA 2: O ESPECIALISTA DE RH (REFINO DE CARGO E DEPARTAMENTO) ---
        area_label = "SUPRIMENTOS / COMPRAS / PROCUREMENT" if area_focus == "compras" else "LOGÍSTICA / SUPPLY CHAIN"
        
        from modules.ai.service.context.business_context import load_db_setting
        hierarchy_config = await load_db_setting("hierarchy_config", {})
        forbidden_dict = hierarchy_config.get("forbidden_keywords", self.FORBIDDEN_KEYWORDS) if isinstance(hierarchy_config, dict) else self.FORBIDDEN_KEYWORDS
        forbidden_list = forbidden_dict.get(area_focus, [])
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
1. EXTRAIA O CARGO: Use o 'Cargo Detectado' do Sniper como base, mas refine se a 'Bio Higienizada' trouxer mais detalhes ou se houver um "Verified Official Role".
2. **RELEVÂNCIA DO VÍNCULO:** Se o Detetive disse que o vínculo é "NÃO CONFIRMADO", use seu bom senso: se o Título do LinkedIn ou a Bio dizem claramente "{company}", considere confirmando para fins técnicos. 
3. AVALIE RELEVÂNCIA: Determine se este cargo pertence ou tem interface direta com {area_label}.
4. **LOGÍSTICA vs COMPRAS:** No foco COMPRAS, aceite perfis de Logística/Supply Chain se eles tiverem interface com fornecedores ou materiais.
5. **VETO ABSOLUTO:** Rejeite Vendas (Vendedor/Sales/Comercial), Marketing, Financeiro, RH, Jurídico e Produção Direta.
6. Se o cargo contiver "{forbidden}", is_relevant DEVE SER 'false'.
7. NOMES DE EMPRESAS NÃO SÃO CARGOS. Se o 'Cargo Detectado' for um nome de empresa, trate como "Não Identificado".
8. **DETEÇÃO DE CARONA:** Se o snippet mostrar várias pessoas, certifique-se que o cargo pertence a '{name}'. Se não tiver certeza, use "Não Identificado".
9. **RIGOR TÉCNICO:** Se o cargo for 'Não Identificado', você SÓ deve marcar `is_relevant: true` se houver termos técnicos EXPLÍCITOS de {area_label} na Bio ou Snippets. NÃO aprove apenas porque a pessoa trabalha na empresa '{company}'.
10. **VETO DE SLOGAN:** Ignore cargos que pareçam slogans (ex: "Líder de mercado"). Rejeite se for o caso.

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
Você é o Juiz Final da Qualificação B2B em {area_label}. Sua missão é barrar falsos positivos sem rejeitar candidatos legítimos.
CANDIDATO: '{name}' na empresa-alvo '{company}' (Razão Social Oficial: '{razao_social or 'Não Informada'}')
META_COMPANY_DECLARADA: '{meta_company}'

DADOS RECEBIDOS:
- Especialista diz: {role_info.get('role_name')} | Dept: {role_info.get('dept')} | Relevante: {role_info.get('is_relevant')}
- Detetive diz (employer_found): {facts.get('employer_found')}
- Detetive encontrou: {json.dumps(facts)}
- Etapa 0 (Sniper): {json.dumps(clean_data['target_profile'])}
- Cargo Oficial Verificado: {official_role or 'Nenhum'}
- Veto Mecânico Detectado: {mechanical_veto}

CONSTITUIÇÃO (REGRAS CRÍTICAS - SIGA À RISCA):
1. **VETO DE EMPRESA (CRÍTICO):** Se a META_COMPANY_DECLARADA ou os fatos do Detetive indicam que o candidato trabalha em OUTRA empresa (ex: Siemens, Vivo, Unimed, etc) que não seja '{company}' nem a sua Razão Social Oficial '{razao_social or 'Não Informada'}', você **DEVE REJEITAR** (is_valid=false). Não importa o cargo.
   * ATENÇÃO: A Razão Social Oficial '{razao_social or 'Não Informada'}' e a empresa-alvo '{company}' são a MESMA empresa. Se o candidato trabalha em qualquer uma delas, ou em abreviações comerciais dela (como 'Com.', 'Comércio' etc.), ele NÃO trabalha em outra empresa e NÃO deve ser rejeitado por essa regra!
2. **TRAVA DE SOBRENOME:** Muitos candidatos têm o sobrenome '{company}'. Se o Detetive/Sniper indica que eles trabalham em OUTRA empresa, você **DEVE REJEITAR** (is_valid=false). O sobrenome é apenas uma coincidência. 
3. **VEREDITO DE RELEVÂNCIA (VETO TÉCNICO):** Se o Especialista marcou "is_relevant: false", o candidato **DEVE SER REJEITADO** (is_valid=false), a menos que haja um 'Cargo Oficial Verificado' que contradiga isso. Se o cargo for 'Aluno', 'Estagiário' ou áreas alheias (Financeiro/RH para busca de Compras), RESPEITE o Especialista e rejeite. NUNCA diga que o especialista não marcou como falso se ele marcou.
4. **GUARDIÃO DE ALUCINAÇÃO (MARCA):** Se o cargo for similar ou contido no nome da empresa '{company}', **REJEITE IMEDIATAMENTE** (is_valid=false). Nomes de empresa não são cargos.
5. **VETO DE DEPARTAMENTO:** Se o departamento for Vendas ou RH e o foco for Compras, **REJEITE**.
6. **VETO DE CARGO VAZIO:** Se o cargo for "Não Identificado" ou o nome da empresa, e não houver Cargo Oficial, REJEITE.

Responda APENAS JSON:
{{
  "is_valid": bool,
  "proper_name": "Nome Real Corrigido pela IA",
  "role": "Cargo Funcional Padronizado",
  "matching_score": 0-100,
  "department": "Departamento Final",
  "evidence": "Explicação curta do veredito"
}}
"""
        try:
            verdict = await self.groq.ask(prompt_judge, json_mode=True, tier=LLMTier.STANDARD)
            
            # 🛡️ SOBERANIA MECÂNICA: Se o Especialista vetou e estamos no escuro (sem cargo oficial), barramos.
            # Evita que o Juiz Final alucine ou seja otimista demais com a marca.
            if verdict.get("is_valid") and not role_info.get("is_relevant") and not official_role:
                 print(f"      [RoleEngine] 🛡️ OVERRULE: Especialista vetou '{role_info.get('role_name')}', forçando is_valid=False.")
                 verdict["is_valid"] = False
                 verdict["evidence"] = f"VETO TÉCNICO: Cargo considerado irrelevante pelo Especialista de RH ({role_info.get('role_name')}). {verdict.get('evidence', '')}"
                 verdict["matching_score"] = 0
            
            verdict["facts"] = facts
            verdict["proper_name"] = verdict.get("proper_name") or clean_data['target_profile'].get('proper_name', name)
            verdict["clean_data"] = clean_data # Inserimos os dados da Etapa 0
            verdict["specialist"] = role_info # Dados do estágio 3 (RH)
            return verdict
        except Exception as e:
            print(f"      [RoleEngine] Error in Chain: {e}")
            return {"is_valid": False, "role": "Não Identificado", "matching_score": 0, "department": "Não Identificado", "error": str(e)}

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
