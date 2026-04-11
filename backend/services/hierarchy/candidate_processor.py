import re
import html
import asyncio
import time
from typing import Dict, List, Optional
from services.hierarchy.role_engine import role_engine
from services.hierarchy.org_search import org_search
from services.intelligence.preview_service import get_url_preview
from services.hierarchy.filters import apply_strict_filters, get_department_tag, get_seniority_level
from services.external.email_service import apply_pattern
from services.hierarchy.logging_utils import log_candidate_rejection, log_candidate_analysis

class CandidateProcessor:
    def __init__(self, brand: str, domain: str, area: str, location: str, product: str):
        self.brand = brand
        self.domain = domain
        self.area = area
        self.location = location
        self.product = product

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
            
            search_query = html.unescape(f'{flexible_name} "{self.brand}" linkedin')
            from services.hierarchy.search_engine import get_duck_results
            # Pegamos mais resultados (10) para garantir que achamos o snippet certo das atividades
            extra_results = await get_duck_results(search_query, max_results=10)
            
            snippets = []
            for r in extra_results:
                snippets.append(f"TÍTULO: {html.unescape(r.get('title'))}\nCORPO: {html.unescape(r.get('body', ''))}")
            
            # 2. Contexto de Repescagem
            repescagem_context = [
                f"--- DADOS DE REPESCAGEM (PESQUISA DIRETA) ---",
                *snippets,
                f"Sugerido via URL: {href}"
            ]
            
            # 3. Segunda Opinião da IA
            from services.hierarchy.role_engine import role_engine
            res = await role_engine.distill_role(name, self.brand, repescagem_context, area_focus=self.area)
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

    async def process_candidate(self, search_result: Dict) -> Optional[Dict]:
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

        # 1. 🔍 THE ORG (Verdade Absoluta)
        theorg_info, theorg_role, theorg_url = await org_search.get_theorg_role(self.brand, name)
        theorg_found = "HIERARCHY" in theorg_info

        # 2. 📄 METADADOS (Preview LinkedIn)
        enriched = await get_url_preview(href, company_hint=self.brand, fast_mode=True)
        meta_role = (enriched.get('role', '') or '').lower()
        
        # 3. 🛡️ FILTRO DE ÂNCORA (Marca)
        brand_slug = role_engine.slugify_lenient(self.brand)
        words = [role_engine.slugify_lenient(w) for w in self.brand.replace('&', ' ').split() if len(w) > 1]
        context_slug = role_engine.slugify_lenient(title + body + meta_role)
        
        brand_match = brand_slug in context_slug or any(w in context_slug for w in words)
        if not theorg_found and not brand_match:
            log_candidate_rejection(name, href, "Âncora de marca não encontrada no contexto")
            return None

        # 4. 🧠 REPESCAGEM / DEEP ANALYSIS
        # Para modularidade, o B2BScanner pode decidir quando rodar a repescagem no lote.
        # Mas aqui faremos a lógica de decisão individual para este processador.
        mechanical_title = role_engine.extract_mechanical_title(title, body, self.brand)
        
        # 🧹 LIMPEZA DE METADADOS E TÍTULO
        import html
        meta_role_clean = html.unescape(meta_role)
        bio_clean = html.unescape(enriched.get('description', 'N/A'))
        
        # Poda do Título (Remove ruído de outras pessoas no mesmo título do Google)
        clean_title = title.split(" - LinkedIn")[0].split(" | LinkedIn")[0]
        if "..." in clean_title: clean_title = clean_title.split("...")[0]
        # Se o título tiver o nome de outra pessoa conhecida (separada por pipe/hífen), corta
        if " - " in clean_title and name not in clean_title.split(" - ")[-1]:
            clean_title = clean_title.split(" - ")[0]

        # 🧠 CONTEXTO RICO PARA IA
        context = [
            f"Candidate Name: {name}",
            f"Google Page Title: {clean_title}",
            f"Search Snippet: {body}",
            f"LinkedIn Status: {enriched.get('name')} | {meta_role_clean}",
            f"LinkedIn Personal Bio: {bio_clean}",
            f"Verified Official Role: {theorg_role}"
        ]
        
        ai_data = await role_engine.distill_role(name, self.brand, context, product_focus=self.product, area_focus=self.area)
        confidence = ai_data.get("matching_score", 0)

        # 🔄 AUTO-REPESCAGEM: Se houver qualquer dúvida (abaixo de 90%), investiga a fundo.
        if ai_data.get("is_valid") and confidence < 90:
             print(f"      [Maestro] 🔄 Dúvida detectada ({confidence}%). Iniciando REPESCAGEM para {name}...")
             repescagem_res = await self.deep_research({"name": name, "linkedin": href, "title": title, "body": body})
             if repescagem_res.get("is_valid"):
                 ai_data = repescagem_res
                 confidence = ai_data.get("matching_score", 95)
                 ai_data["evidence"] = f"APROVADO VIA REPESCAGEM: {ai_data.get('evidence')}"

        # 🛡️ TRAVA FINAL: Só rejeita se a confiança for realmente nula ou se a IA for categórica.
        if ai_data.get("is_valid") and confidence < 60:
            ai_data["is_valid"] = False
            ai_data["evidence"] = f"VETO: Confiança insuficiente ({confidence}%)."

        # Fidelity Guard
        final_role = role_engine.apply_fidelity_guard(ai_data.get("role", "Professional"), mechanical_title)
        if theorg_found and theorg_role != "Não Encontrado":
            final_role = theorg_role

        # Log Unificado
        log_candidate_analysis(
            name, href, 
            {"title": title, "body": body, "meta": meta_role_clean, "bio_lkn": bio_clean}, 
            ai_data, 
            {"role": theorg_role, "url": theorg_url}, 
            {"is_valid": ai_data.get("is_valid"), "role": final_role, "department": ai_data.get("department", "N/D"), "matching_score": confidence}
        )

        if not ai_data.get("is_valid") and not theorg_found:
            return None

        # 🎨 MONTAGEM DO NÓ
        first_name = name.split()[0].lower() if name.split() else "colaborador"
        last_parts = name.split()[1:]
        last_name = last_parts[-1].lower() if last_parts else first_name
        generated_email = apply_pattern(first_name, last_name, self.domain, "first.last")
        
        # 🏢 LOGO DA EMPRESA (Usando domínio para ser infalível no unavatar)
        company_logo = f"https://unavatar.io/{self.domain}" if self.domain else None
        
        return {
            "id": f"node_{href.split('/in/')[-1].replace('/', '_')}",
            "name": name,
            "role": final_role,
            "company": self.brand,
            "linkedin": href,
            "url": href,
            "department": get_department_tag(final_role),
            "level": get_seniority_level(final_role),
            "email": generated_email,
            "avatar": enriched.get("image"),
            "company_logo": company_logo,
            "location": self.location or "Brasil"
        }
