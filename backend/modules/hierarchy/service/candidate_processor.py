"""
modules.hierarchy.service.candidate_processor
=============================================
Validacao e enriquecimento de candidatos encontrados no LinkedIn.

Para cada candidato bruto: verifica cargo via RoleEngine, extrai email
por padroes de nome+dominio, e faz deep_research() quando dados sao
insuficientes para uma decisao confiavel.

Classe: CandidateProcessor(brand, domain, area, location, product)
"""
import re
import html
import asyncio
import time
from typing import Dict, List, Optional
from .role_engine import role_engine
from .org_search import org_search
from modules.intelligence.service.preview_service import get_url_preview
from .filters import apply_strict_filters, get_department_tag, get_seniority_level, is_same_person, check_location_is_brazilian
from core.external.email_service import apply_pattern
from .logging_utils import log_candidate_rejection, log_candidate_analysis, register_raw_data

class CandidateProcessor:
    def __init__(self, brand: str, domain: str, area: str, location: str, product: str, razao_social: Optional[str] = None, partners: Optional[List[str]] = None):
        self.brand = brand
        self.domain = domain
        self.area = area
        self.location = location
        self.product = product
        self.razao_social = razao_social
        self.partners = partners or []

    def is_qsa_partner(self, candidate_name: str) -> bool:
        if not self.partners or not candidate_name:
            return False
        for partner_name in self.partners:
            if is_same_person(partner_name, candidate_name):
                return True
        return False

    async def deep_research(self, candidate_data: Dict) -> Dict:
        """Realiza uma busca cirúrgica para validar um candidato duvidoso (Repescagem)."""
        import html
        name = candidate_data.get("name")
        href = candidate_data.get("linkedin")
        
        try:
            # 1. Busca dedicada de Sniper (Mais inteligente: Se o nome for longo, usa ele todo sem aspas)
            name_parts = name.split()
            if len(name_parts) > 3:
                flexible_name = name # Usa o nome completo para nomes compostos longos
            else:
                flexible_name = f"{name_parts[0]} {name_parts[-1]}" if len(name_parts) > 1 else name
            
            clean_brand = self.brand.replace("Gmb H", "").replace("GmbH", "").replace("Ltda", "").replace("S.A.", "").strip()
            search_location = self.location if self.location else "Brasil"
            
            # Formato buscador de experiência (Nome + Marca + Local + linkedin + cargo/experiência)
            # Focamos em capturar a aba de 'Experiência' do LinkedIn no snippet do Google/Duck
            search_query = html.unescape(f'{flexible_name} {clean_brand} {search_location} linkedin cargo experiência')
            print(f"      [Maestro] 🔎 Consultando fundo: {search_query}")
            
            from .search_engine import get_duck_results
            # Aumentamos para 15 resultados para garantir que pegamos o snippet de experiência se houver
            extra_results = await get_duck_results(search_query, max_results=15)
            
            snippets = []
            suggested_linkedin = href # Fallback
            for idx, r in enumerate(extra_results):
                r_href = r.get('href', '')
                # Se o órfão não tinha LinkedIn, pegamos o primeiro link de perfil que aparecer
                if ("linkedin.com/in/" in r_href) and (not suggested_linkedin or "/in/" not in suggested_linkedin):
                    suggested_linkedin = r_href.split("?")[0]
                snippets.append(f"TÍTULO: {html.unescape(r.get('title'))}\nCORPO: {html.unescape(r.get('body', ''))}")
            
            # 2. Contexto de Repescagem
            repescagem_context = [
                f"--- DADOS DE REPESCAGEM (PESQUISA DIRETA) ---",
                *snippets,
                f"Sugerido via URL: {suggested_linkedin}"
            ]
            
            # 3. Segunda Opinião da IA
            from .role_engine import role_engine
            res = await role_engine.distill_role(name, self.brand, repescagem_context, area_focus=self.area, target_location=self.location, razao_social=self.razao_social)
            res["verified_linkedin"] = suggested_linkedin
            return res
            
        except Exception as e:
            print(f"      [Repescagem] ❌ Falha na investigação: {e}")
            return {"is_valid": False, "matching_score": 0, "evidence": f"Erro na repescagem: {e}"}

    def clean_name_from_title(self, title: str) -> str:
        """Extrai o nome limpo do título do buscador."""
        t_clean = title.replace(" | LinkedIn", "").replace("| LinkedIn", "").strip()
        parts = re.split(r'[\|\-\–\—•]', t_clean)
        name_guess = parts[0].strip()
        
        if len(self.brand) > 5:
            name_final = re.split(fr"\s*{re.escape(self.brand)}", name_guess, flags=re.I)[0].strip()
        else:
            name_final = name_guess
            
        return name_final.split('...')[0].strip()

    async def upgrade_orphan(self, orphan_data: Dict) -> Optional[Dict]:
        """
        Pega um nome descoberto 'de carona' e roda uma investigação completa (Repescagem).
        Isso transforma um órfão ruidoso em um candidato de alta fidelidade.
        """
        name = orphan_data.get("name")
        print(f"      [Orphan Upgrade] 💎 Iniciando investigação para: {name}")
        
        is_qsa = self.is_qsa_partner(name)

        # 1. Roda a Repescagem (IA + Busca Direta)
        ai_data = await self.deep_research({"name": name, "linkedin": "None"})
        
        # 🎭 FALLBACK PARA ÓRFÃOS: 'Análise Humana'
        is_invalid = not ai_data.get("is_valid") or ai_data.get("matching_score", 0) < 70
        generic_roles = ["não identificado", "professional", "colaborador", "employee", "pioneer", "cargo não identificado nos metadados"]
        current_role_lower = str(ai_data.get("role", "")).lower()

        if is_invalid and (current_role_lower in generic_roles or not ai_data.get("role")):
             # Para órfãos, exigimos um pouco mais de evidência para não encher de lixo
             if is_qsa:
                 ai_data["is_valid"] = True
                 ai_data["role"] = "Sócio / Administrador"
                 ai_data["department"] = "Quadro de Sócios (QSA)"
                 ai_data["matching_score"] = 100
                 print(f"      [Orphan Upgrade] 💎 Sócio Administrador QSA promovido automaticamente: {name}")
             elif ai_data.get("department") != "Não Identificado" and ai_data.get("matching_score", 0) > 0:
                 ai_data["is_valid"] = True
                 ai_data["role"] = "Análise Humana"
                 ai_data["department"] = "A validar (Órfão)"
                 print(f"      [Orphan Upgrade] 🎭 Promovido para ANÁLISE HUMANA: {name}")
             else:
                 print(f"      [Orphan Upgrade] 🚫 Rejeitado: {name} (Não relevante para {self.area})")
                 return None
            
        # 2. Enriquecimento de Metadados (Aproveitamos para pegar a imagem e bio real)
        verified_linkedin = ai_data.get("verified_linkedin")
        if verified_linkedin and "/in/" in verified_linkedin:
            enriched = await get_url_preview(verified_linkedin, company_hint=self.brand, fast_mode=True)
        else:
            enriched = {}

        # 3. Montagem do Nó Completo
        final_role = ai_data.get("role", orphan_data.get("role", "Colaborador"))
        if is_qsa and (final_role.lower() in generic_roles or not final_role or final_role == "Colaborador"):
            final_role = "Sócio / Administrador"
        
        confidence = ai_data.get("matching_score", 0)

        # 🛡️ Proteção extra: headline nunca deve ser "Análise Humana"
        raw_headline = enriched.get("role")
        if not raw_headline or "não identificado" in raw_headline.lower() or "análise humana" in raw_headline.lower():
            if final_role and "análise humana" not in final_role.lower():
                final_headline = final_role
            else:
                final_headline = "Colaborador"
        else:
            final_headline = raw_headline
        
        node_data = {
            "id": f"node_{verified_linkedin.split('/in/')[-1].replace('/', '_')}" if verified_linkedin else f"node_orphan_{name.replace(' ', '_')}",
            "name": name,
            "role": final_role,
            "company": self.brand,
            "linkedin": verified_linkedin or "URL não encontrada",
            "url": verified_linkedin or "URL não encontrada",
            "department": "Quadro de Sócios (QSA)" if is_qsa else await get_department_tag(final_role),
            "level": 6 if is_qsa else await get_seniority_level(final_role),
            "email": apply_pattern(name.split()[0].lower(), (name.split()[1:] or [name.split()[0]])[-1].lower(), self.domain, "first.last"),
            "avatar": enriched.get("image") or None,
            "company_logo": f"https://unavatar.io/{self.domain}" if self.domain else None,
            "location": enriched.get("location") or self.location or "Brasil",
            "observations": ai_data.get("evidence") or enriched.get("description"),
            "education": enriched.get("education"),
            "headline": final_headline,
            "matching_score": 100 if is_qsa else confidence,
            "evidence": ai_data.get("evidence")
        }
        
        # Registro de Dados Brutos para Órfãos
        register_raw_data(
            name, 
            verified_linkedin or "N/A", 
            {"title": "Orphan Upgrade", "body": "N/D", "meta": enriched.get("role"), "bio_lkn": enriched.get("description")}, 
            ai_data, 
            {"role": "Não Encontrado"}, 
            {"is_valid": ai_data.get("is_valid"), "role": final_role, "department": ai_data.get("department", "N/D"), "matching_score": confidence}
        )

        print(f"      [Orphan Upgrade] ✅ Sucesso: {name} promovido para {final_role}")
        return node_data

    async def process_candidate(self, search_result: Dict, is_partner_search: bool = False) -> Optional[Dict]:
        """
        Orquestra toda a análise de um único candidato.
        Retorna node_data se aprovado, None se reprovado.
        """
        href = search_result.get("href", "").split("?")[0].rstrip("/")
        title = search_result.get('title', '').strip()
        body = (search_result.get("body") or search_result.get("snippet") or "").strip()
        
        name = self.clean_name_from_title(title)
        if len(name) < 3 or name.lower() == self.brand.lower() or "linkedin" in name.lower():
            log_candidate_rejection(name or "Unknown", href, "Nome inválido ou coincidente com a marca")
            return None

        # 🛡️ FIX #4: Ativa o Filtro Mecânico Estrito antes da IA (Bypassado para buscas de sócios/fundadores ou QSA)
        is_qsa = self.is_qsa_partner(name)
        
        mechanical_title = role_engine.extract_mechanical_title(title, body, self.brand)
        if not mechanical_title or mechanical_title.strip() == "":
            mechanical_title = "Não Identificado"

        if not is_partner_search and not is_qsa:
            core_comp_arg = self.razao_social if self.razao_social else self.brand
            is_valid, reject_reason = await apply_strict_filters(name, title, body, core_comp_arg, self.brand, self.location, mechanical_title)
            if not is_valid:
                log_candidate_rejection(name, href, f"REJEIÇÃO MECÂNICA: {reject_reason}")
                return None

        # 1. 🔍 THE ORG (Verdade Absoluta)
        theorg_info, theorg_role, theorg_url = await org_search.get_theorg_role(self.brand, name)
        theorg_found = "HIERARCHY" in theorg_info

        # 2. 📄 METADADOS (Preview LinkedIn)
        enriched = await get_url_preview(href, company_hint=self.brand, fast_mode=True)
        meta_company = (enriched.get('company', '') or '').strip()
        
        # 🇧🇷 FILTRO DE LOCALIZAÇÃO (Rejeita não-brasileiros)
        candidate_loc = enriched.get('location', '')
        if candidate_loc:
            is_br, loc_reason = check_location_is_brazilian(candidate_loc)
            if is_br is False:
                log_candidate_rejection(name, href, f"REJEIÇÃO DE LOCALIZAÇÃO: {loc_reason}")
                return None
        
        # 🧪 INTELIGÊNCIA DE NOME: Se o nome extraído do título parece um cargo ou é genérico,
        # tentamos extrair o nome real dos metadados ou da URL.
        meta_name = enriched.get('name', '').strip()
        role_keywords = ['comprador', 'manager', 'diretor', 'director', 'gerente', 'analista', 'vp', 'ceo', 'coordenador', 'lead', 'pleno', 'sênior', 'jr']
        
        is_role_not_name = any(kw in name.lower() for kw in role_keywords) or (self.brand.lower() in name.lower())
        
        if (len(meta_name) > 3 and meta_name.lower() != self.brand.lower()) and (is_role_not_name or len(name) < 5):
            print(f"      [CandidateProcessor] 👤 Refinando nome: '{name}' -> '{meta_name}' (via Metadados)")
            name = meta_name
        elif is_role_not_name:
            # Fallback: Tenta extrair da URL Slug (ex: gislane-rodrigues-...)
            url_slug = href.split("/in/")[-1].split("/")[0].split("?")[0]
            slug_parts = [p.capitalize() for p in url_slug.split("-") if not p.isdigit() and len(p) > 2]
            if len(slug_parts) >= 2:
                inferred_name = " ".join(slug_parts[:3]) # Pega até 3 nomes
                print(f"      [CandidateProcessor] 👤 Refinando nome: '{name}' -> '{inferred_name}' (via URL Slug)")
                name = inferred_name

        meta_role = (enriched.get('role', '') or '').lower()
        meta_role_clean = html.unescape(meta_role)
        bio_clean = html.unescape(enriched.get('description', 'N/A'))
        brand_slug = role_engine.slugify_lenient(self.brand)
        words = [role_engine.slugify_lenient(w) for w in self.brand.replace('&', ' ').split() if len(w) > 1]
        
        # Se tiver Razão Social, inclui na âncora de marca
        if self.razao_social:
            razao_slug = role_engine.slugify_lenient(self.razao_social)
            razao_words = [role_engine.slugify_lenient(w) for w in self.razao_social.replace('&', ' ').split() if len(w) > 1]
        else:
            razao_slug = ""
            razao_words = []
            
        context_slug = role_engine.slugify_lenient(title + body + meta_role)
        
        brand_match = (
            brand_slug in context_slug 
            or any(w in context_slug for w in words)
            or (razao_slug and razao_slug in context_slug)
            or (razao_words and any(w in context_slug for w in razao_words))
        )
        
        if not theorg_found and not brand_match:
            # Mesmo rejeitado aqui, vamos logar os dados brutos que já coletamos
            log_candidate_analysis(
                name, href, 
                {"title": title, "body": body, "meta": meta_role_clean, "bio_lkn": bio_clean}, 
                {"is_valid": False, "evidence": "REJEIÇÃO MECÂNICA: Marca não encontrada no contexto (Título/Snippet/Meta)"}, 
                {"role": theorg_role, "url": theorg_url}, 
                {"is_valid": False, "role": "N/D", "department": "N/D", "matching_score": 0}
            )
            return None

        # 4. 🧠 REPESCAGEM / DEEP ANALYSIS
        # Para modularidade, o B2BScanner pode decidir quando rodar a repescagem no lote.
        # Mas aqui faremos a lógica de decisão individual para este processador.
        
        # ✂️ PODA MECÂNICA (Solução Definitiva contra ruído de múltiplos perfis)
        def isolate_context(text, target_name):
            if "..." in text:
                parts = text.split("...")
                # Tenta match pelo nome completo
                for p in parts:
                    if target_name.lower() in p.lower():
                        return p.strip()
                # Tenta match pelo primeiro nome (Último recurso para snippets cortados)
                first_name = target_name.split()[0].lower()
                if len(first_name) > 2:
                    for p in parts:
                        if first_name in p.lower():
                            return p.strip()
            return text

        clean_title = isolate_context(title.split(" - LinkedIn")[0].split(" | LinkedIn")[0], name)
        clean_body = isolate_context(body, name)
        
        if "..." in clean_title: clean_title = clean_title.split("...")[0]

        # 🧠 CONTEXTO RICO PARA IA
        context = [
            f"Candidate Name: {name}",
            f"Google Page Title: {clean_title}",
            f"Search Snippet: {clean_body}",
            f"LinkedIn Status: {enriched.get('name')} | {meta_role_clean}",
            f"LinkedIn CURRENT COMPANY (Declarada): {meta_company or 'Não detectada'}",
            f"LinkedIn Personal Bio: {bio_clean}",
            f"Verified Official Role: {theorg_role}"
        ]
        
        ai_data = await role_engine.distill_role(
            name, self.brand, context, 
            product_focus=self.product, 
            area_focus=self.area, 
            target_location=self.location,
            official_role=theorg_role if theorg_found else None,
            meta_company=meta_company,
            razao_social=self.razao_social
        )
        confidence = ai_data.get("matching_score", 0)

        # 🔄 AUTO-REPESCAGEM: Se houver qualquer dúvida (abaixo de 90%) OU cargo não identificado, investiga a fundo.
        # Agora ativamos repescagem MESMO se for inválido, mas o cargo for genérico (Pode ser um falso negativo por falta de dado)
        generic_roles = ["não identificado", "professional", "colaborador", "employee", "pioneer", "cargo não identificado nos metadados"]
        current_role_lower = str(ai_data.get("role", "")).lower()
        
        needs_repescagem = (
            (ai_data.get("is_valid") and confidence < 90) or 
            (current_role_lower in generic_roles)
        )
        
        if needs_repescagem:
             print(f"      [Maestro] 🔄 Dúvida ou Cargo Genérico detectado ('{ai_data.get('role')}'). Iniciando REPESCAGEM para {name}...")
             repescagem_res = await self.deep_research({"name": name, "linkedin": href, "title": title, "body": body})
             if repescagem_res.get("is_valid"):
                 ai_data = repescagem_res
                 confidence = ai_data.get("matching_score", 95)
                 ai_data["evidence"] = f"APROVADO VIA REPESCAGEM: {ai_data.get('evidence')}"
             else:
                 # 🛡️ FIX: Se a investigação profunda diz que NÃO é válido, atualizamos o status global.
                 ai_data["is_valid"] = False
                 ai_data["evidence"] = f"REJEITADO APÓS REPESCAGEM: O perfil foi investigado e o cargo é irrelevante/não confirmado. {ai_data.get('evidence', '')}"

        # 🎭 FALLBACK DE ÚLTIMA INSTÂNCIA: 'Análise Humana'
        # Se chegamos aqui e o cargo AINDA é genérico (mesmo após repescagem), enviamos para aprovação humana.
        # Não descartamos se houver evidência de vínculo.
        final_processed_role = str(ai_data.get("role", "")).lower()
        if final_processed_role in generic_roles or not ai_data.get("role"):
             # Só fazemos o fallback se houver algum indício de que a pessoa trabalha lá
             if mechanical_title == "Não Identificado" or ai_data.get("is_valid") or ai_data.get("department") != "Não Identificado" or confidence > 0 or is_qsa:
                  ai_data["is_valid"] = True
                  ai_data["role"] = "Análise Humana"
                  ai_data["department"] = "A validar"
                  ai_data["matching_score"] = 10 
                  ai_data["evidence"] = "ENVIADO PARA ANÁLISE HUMANA: Vínculo confirmado, mas cargo exato oculto/genérico."

        # 🛡️ TRAVA FINAL: Só rejeita se a confiança for realmente nula ou se a IA for categórica.
        if ai_data.get("is_valid") and confidence < 5:
            # Mantemos o "Análise Humana" se for o caso ou se for QSA
            if ai_data.get("role") != "Análise Humana" and not is_qsa:
                ai_data["is_valid"] = False
            ai_data["evidence"] = f"VETO: Confiança insuficiente ({confidence}%)."

        # Fidelity Guard
        final_role = role_engine.apply_fidelity_guard(ai_data.get("role", "Professional"), mechanical_title, brand=self.brand)
        if theorg_found and theorg_role != "Não Encontrado":
            final_role = theorg_role

        if is_qsa and (final_role.lower() in generic_roles or not final_role or final_role == "Professional"):
            final_role = "Sócio / Administrador"

        # 🔥 SOBERANIA DA IA: O nome final é o que a IA extraiu (proper_name), ignorando o chute inicial.
        name = ai_data.get("proper_name", name)

        # Log Unificado
        log_candidate_analysis(
            name, href, 
            {"title": title, "body": body, "meta": meta_role_clean, "bio_lkn": bio_clean, "mechanical_role": mechanical_title}, 
            ai_data, 
            {"role": theorg_role, "url": theorg_url}, 
            {"is_valid": ai_data.get("is_valid"), "role": final_role, "department": ai_data.get("department", "N/D"), "matching_score": confidence}
        )

        # 🎁 COLETA DE ÓRFÃOS (Aproveitamento total dos dados)
        potential_orphans = []
        for mapping in ai_data.get("clean_data", {}).get("all_mappings", []):
            m_name = mapping.get("name")
            if m_name and m_name.lower() != name.lower() and len(m_name) > 5:
                potential_orphans.append({
                    "name": m_name,
                    "role": mapping.get("role"),
                    "company": self.brand,
                    "source": "discovery_leak"
                })

        if not ai_data.get("is_valid") and not theorg_found:
            # Se for um sócio do QSA, NUNCA rejeita! Protege e força Análise Humana/Sócio
            if is_qsa:
                ai_data["is_valid"] = True
                final_role = final_role if (final_role and final_role != "Professional" and final_role.lower() not in generic_roles) else "Sócio / Administrador"
                ai_data["role"] = final_role
                ai_data["department"] = "Quadro de Sócios (QSA)"
                ai_data["matching_score"] = 100
                ai_data["evidence"] = "APROVADO AUTOMATICAMENTE: Sócio Administrador confirmado no QSA/CNPJ da empresa."
            else:
                return {"main": None, "orphans": potential_orphans}

        # 🎨 MONTAGEM DO NÓ PRINCIPAL
        # 🛡️ Proteção extra: headline nunca deve ser "Análise Humana"
        raw_headline = enriched.get("role")
        if not raw_headline or "não identificado" in raw_headline.lower() or "análise humana" in raw_headline.lower():
            if final_role and "análise humana" not in final_role.lower():
                final_headline = final_role
            else:
                final_headline = "Colaborador"
        else:
            final_headline = raw_headline

        node_data = {
            "id": f"node_{href.split('/in/')[-1].replace('/', '_')}",
            "name": name,
            "role": final_role,
            "company": self.brand,
            "linkedin": href,
            "url": href,
            "department": "Quadro de Sócios (QSA)" if is_qsa else await get_department_tag(final_role),
            "level": 6 if is_qsa else await get_seniority_level(final_role),
            "email": apply_pattern(name.split()[0].lower(), (name.split()[1:] or [name.split()[0]])[-1].lower(), self.domain, "first.last"),
            "avatar": enriched.get("image"),
            "company_logo": f"https://unavatar.io/{self.domain}" if self.domain else None,
            "location": enriched.get("location") or self.location or "Brasil",
            "observations": enriched.get("description"), # A Bio vinda do OSINT
            "education": enriched.get("education"),
            "headline": final_headline,
            "matching_score": 100 if is_qsa else confidence,
            "evidence": ai_data.get("evidence")
        }

        return {"main": node_data, "orphans": potential_orphans}
