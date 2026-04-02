import re
import httpx
from typing import Dict, Optional, Any, List
from services.search_engine import get_duck_results as search_duckduckgo
import os
from sqlalchemy import select
from services.database import async_session, Organization

class IntelligenceService:
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")

    def _format_cnpj(self, cnpj_str: str) -> str:
        """Formata CNPJ bruto em 00.000.000/0001-00."""
        if not cnpj_str: return None
        clean = re.sub(r'\D', '', str(cnpj_str))
        if len(clean) != 14: return cnpj_str
        return f"{clean[:2]}.{clean[2:5]}.{clean[5:8]}/{clean[8:12]}-{clean[12:]}"

    async def _save_org_to_db(self, name: str, data: dict):
        """Salva ou atualiza a empresa no Banco de Dados SQL."""
        try:
            async with async_session() as session:
                # 🛡️ Busca se já existe para evitar duplicidade
                stmt = select(Organization).where(Organization.name == name)
                result = await session.execute(stmt)
                org = result.scalars().first()
                
                if not org:
                    org = Organization(name=name)
                    session.add(org)
                
                # Atualiza metadados OSINT
                if data:
                    org.cnpj = self._format_cnpj(data.get("cnpj")) or org.cnpj
                    org.domain = data.get("domain") or org.domain
                    org.address = data.get("address") or org.address
                
                await session.commit()
                print(f"[Database] 🐘 Empresa '{name}' Sincronizada no Neon DB.")
        except Exception as e:
            print(f"[Database] Error saving org: {e}")

    async def enrich_company(self, company_name: str, hint_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Busca dados OSINT + IA e persiste no Neon DB.
        """
        # 1. TENTA BUSCAR NO BANCO PRIMEIRO (CACHE DE INTELIGÊNCIA)
        try:
            async with async_session() as session:
                stmt = select(Organization).where(Organization.name == company_name)
                res = await session.execute(stmt)
                cached = res.scalars().first()
                if cached and cached.cnpj and cached.domain:
                    print(f"[Intelligence] 🧠 Carregando Memória SQL para: {company_name}")
                    return {
                        "main_option": {"cnpj": cached.cnpj, "domain": cached.domain, "address": cached.address},
                        "other_options": [],
                        "is_match": True,
                        "success": True
                    }
        except Exception as e:
            print(f"[Database] Cache error: {e}")

        print(f"[Intelligence] 🕵️‍♂️ Investigando: {company_name} | Pista: {hint_address or 'Nenhuma'}")
        
        # 🔍 MULTI-SNIPER SEARCH STRATEGY
        clean_hint = hint_address if (hint_address and str(hint_address).lower() != "none") else ""
        
        # 🎯 Buscas em múltiplas frentes para garantir volume de dados
        queries = [
            f"{company_name} {clean_hint} cnpj brasil sede matriz",
            f"{company_name} linkedin company official website domain",
            f"qual o cnpj e domínio de email da empresa {company_name} no brasil"
        ]
        
        results = []
        for q in queries:
            batch = await search_duckduckgo(q)
            if batch:
                results.extend(batch)
            
        # Remove duplicatas de URLs nos resultados
        seen_hrefs = set()
        unique_results = []
        for r in results:
            if r['href'] not in seen_hrefs:
                seen_hrefs.add(r['href'])
                unique_results.append(r)
        results = unique_results

        combined_text = "\n".join([f"Title: {r['title']} | Body: {r['body']}" for r in results[:15]])
        
        result_data = {
            "main_option": None,
            "other_options": [],
            "success": False,
            "is_match": False
        }

        if self.groq_api_key and combined_text:
            try:
                # PROMPT DE SELEÇÃO EXTRAPOLADA
                prompt = (
                    f"Task: Extract corporate intelligence for '{company_name}'.\n"
                    f"Address Hint: '{hint_address or 'Not provided'}'\n\n"
                    f"Rules:\n"
                    f"1. Identify the 'main_option': the official headquarters ('Matriz') or the one matching the address hint.\n"
                    f"2. Extract the 'cnpj' (14 digits), 'address', and official corporate 'domain' (e.g., knorr-bremse.com.br - NO www/http).\n"
                    f"3. DEDUCE DOMAIN: If not explicitly written, look at the titles/links in the SNIPPETS to find the official corporate URL.\n"
                    f"4. List other branches or related companies in 'other_options'.\n"
                    f"5. If 'main_option' is the clear corporate headquarters for Brazil, set 'is_match': true.\n\n"
                    f"CRITICAL: If any data is MISSING or UNKNOWN, return null for that field. NEVER use filler text.\n\n"
                    f"Return JSON: {{'main_option': {{'cnpj', 'domain', 'address'}}, 'other_options': [...], 'is_match': boolean}}\n\n"
                    f"DATA SNIPPETS:\n{combined_text}"
                )
                
                async with httpx.AsyncClient(timeout=15.0) as client:
                    target_model = "llama-3.1-8b-instant" # 🏎️ Rápida e com limites generosos
                    print(f"[Intelligence] 🧠 Consultando {target_model} para {company_name}...")
                    
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.groq_api_key}"},
                        json={
                            "model": target_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0,
                            "response_format": {"type": "json_object"}
                        }
                    )
                    
                    if resp.status_code == 200:
                        import json
                        raw_content = resp.json()['choices'][0]['message']['content']
                        print(f"[Intelligence] 🤖 Resposta IA para {company_name}: {raw_content}") 
                        
                        ai_data = json.loads(raw_content)
                        
                        main = ai_data.get("main_option")
                        result_data["main_option"] = main
                        result_data["other_options"] = ai_data.get("other_options", [])
                        result_data["is_match"] = ai_data.get("is_match", False)
                        result_data["success"] = True
                        
                        # PERSISTÊNCIA NO SQL
                        if main:
                            await self._save_org_to_db(company_name, main)
                    else:
                        print(f"[Intelligence] 🚨 IA Falhou (Erro {resp.status_code}): {resp.text}")
            except Exception as e:
                print(f"[Intelligence] IA Error: {e}")
                
        # 🛡️ HEURISTIC FALLBACK: Se a IA falhou, tenta extrair o domínio dos links
        if not result_data.get("main_option") or not result_data["main_option"].get("domain"):
            print(f"[Intelligence] 🚑 Ativando Heurística de Emergência para {company_name}...")
            for r in results[:5]:
                href = r.get("href", "")
                # Extrai domínio simples (ex: knorr-bremse.com)
                match = re.search(r'https?://(?:www\.)?([^/]+)', href)
                if match:
                    found_domain = match.group(1).split(":")[0].lower()
                    # Filtra ruído (linkedin, duckduckgo, etc)
                    if not any(x in found_domain for x in ["linkedin", "duckduckgo", "youtube", "facebook", "instagram", "mercadolivre"]):
                        if not result_data["main_option"]: 
                            result_data["main_option"] = {"cnpj": None, "domain": found_domain, "address": None}
                        else: 
                            result_data["main_option"]["domain"] = found_domain
                        
                        result_data["success"] = True
                        print(f"[Intelligence] ✨ Domínio Restaurado por Heurística: {found_domain}")
                        break

        print(f"[Intelligence] 🏁 Resultado Final {company_name}: {result_data}")
        return result_data

# Singleton
intelligence_service = IntelligenceService()
