import re
import httpx
from typing import Dict, Optional, Any, List
from services.hierarchy.search_engine import get_duck_results as search_duckduckgo
import os
import json
import asyncio
from sqlalchemy import select
from core.database import async_session
from models import Organization
from .brand_discovery import get_corporate_data, extract_domain_from_email, discover_domain_via_clearbit

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
                stmt = select(Organization).where(Organization.name == name)
                result = await session.execute(stmt)
                org = result.scalars().first()
                
                if not org:
                    org = Organization(name=name)
                    session.add(org)
                
                if data:
                    org.cnpj = self._format_cnpj(data.get("cnpj")) or org.cnpj
                    org.domain = data.get("domain") or org.domain
                    org.address = data.get("address") or org.address
                
                await session.commit()
                print(f"[Database] 🐘 Empresa '{name}' Sincronizada.")
        except Exception as e:
            print(f"[Database] Error saving org: {e}")

    async def enrich_company(self, company_name: str, hint_address: Optional[str] = None, force_refresh: bool = False, cnpj: Optional[str] = None) -> Dict[str, Any]:
        """
        Versão Aprimorada: Foca em Domínio e Endereço. 
        Extrai domínio do e-mail oficial (BrasilAPI) e refina buscas OSINT.
        """
        # 1. TENTA BUSCAR NO BANCO PRIMEIRO (Cache de Alta Performance)
        if not force_refresh:
            try:
                async with async_session() as session:
                    # Se temos CNPJ, buscamos por ele (mais preciso). Senão, pelo nome.
                    if cnpj:
                        fmt_cnpj = self._format_cnpj(cnpj)
                        stmt = select(Organization).where(Organization.cnpj == fmt_cnpj)
                    else:
                        stmt = select(Organization).where(Organization.name == company_name)
                    
                    res = await session.execute(stmt)
                    cached = res.scalars().first()
                    
                    # Se temos o dado completo (CNPJ + Domínio), retornamos imediatamente
                    if cached and cached.cnpj and cached.domain:
                        print(f"[Intelligence] 📦 Cache Hit: {cached.cnpj} -> {cached.domain}")
                        return {
                            "main_option": {
                                "cnpj": cached.cnpj,
                                "domain": cached.domain,
                                "address": cached.address,
                                "official_name": cached.name
                            },
                            "success": True,
                            "is_match": True,
                            "cached": True
                        }
            except Exception as e:
                print(f"[Intelligence] Cache Check skipped: {e}")

        result_data = {
            "main_option": None,
            "other_options": [],
            "success": False,
            "is_match": False,
            "needs_cnpj": True if not cnpj else False 
        }

        found_domain = None
        official_email = None

        # 2. SE TEM CNPJ, BUSCA DADOS OFICIAIS (ALTA PRECISÃO)
        if cnpj:
            print(f"[Intelligence] 🎯 Buscando dados oficiais para CNPJ: {cnpj}")
            official = await get_corporate_data(cnpj)
            if official.get("success"):
                official_email = official.get("email")
                result_data["main_option"] = {
                    "cnpj": cnpj,
                    "address": official.get("address"),
                    "domain": None,
                    "official_name": official.get("name")
                }
                result_data["needs_cnpj"] = False
                result_data["is_match"] = True
                result_data["success"] = True

                # Tenta extrair domínio do e-mail oficial
                print(f"[Intelligence] Official Email retornado: {official_email}")
                found_domain = await extract_domain_from_email(official_email)
                if found_domain:
                    print(f"[Intelligence] 📧 Domínio extraído do e-mail: {found_domain}")

        # 3. CAMADA 2: Clearbit (API Global de Domínios)
        if not found_domain:
            search_name = result_data["main_option"]["official_name"] if result_data["main_option"] and result_data["main_option"].get("official_name") else company_name
            print(f"[Intelligence] 🚀 Tentando Clearbit para '{search_name}'...")
            found_domain = await discover_domain_via_clearbit(search_name)
            if found_domain:
                print(f"[Intelligence] 🌐 Domínio encontrado via Clearbit: {found_domain}")

        # 4. CAMADA 3: BUSCA DE DOMÍNIO VIA OSINT (Foco Técnico - Sem LinkedIn)
        # Priorizamos encontrar o site oficial antes de buscar redes sociais.
        if not found_domain:
            search_target = result_data["main_option"]["official_name"] if result_data["main_option"] and result_data["main_option"].get("official_name") else company_name
            # Limpa o "ruído" jurídico e conectores para a busca ser mais humana e técnica
            # Remove (QUALQUER COISA), LTDA, S.A, etc, e também conectores como E, DE, DA...
            search_target_clean = re.sub(r'\(.*?\)|LTDA|S\.A\.|EIRELI|ME|EPP|MEI|INDUSTRIA|COMERCIO|SERVICOS|BRASIL|ARMAZENAGEM|PECAS', '', search_target, flags=re.IGNORECASE)
            search_target_clean = re.sub(r'\s+(E|DE|DA|DO|DAS|DOS)\s+', ' ', f" {search_target_clean} ", flags=re.IGNORECASE).strip()
            search_target_clean = re.sub(r'\s+', ' ', search_target_clean).strip()
            
            print(f"[Intelligence] 🔍 Buscando site oficial OSINT para: {search_target_clean}")
            queries = [
                f'site oficial "{search_target_clean}"',
                f'"{search_target_clean}" homepage -site:cnpj.biz -site:econodata.com.br -site:casadosdados.com.br'
            ]
            results = []
            for q in queries:
                batch = await search_duckduckgo(q, max_results=3)
                if batch: results.extend(batch)

            for r in results:
                href = r.get("href", "").lower()
                match = re.search(r'https?://(?:www\.)?([^/]+)', href)
                if match:
                    domain = match.group(1).split(":")[0].lower()
                    blacklist = ["linkedin", "duckduckgo", "google", "facebook", "instagram", "twitter", "jusbrasil", "bing", "microsoft", "apple", "youtube", "amazon", "cnpj.biz", "econodata", "leads2b"]
                    if not any(x in domain for x in blacklist) and "." in domain:
                        found_domain = domain
                        print(f"[Intelligence] ✅ Site oficial encontrado via OSINT: {found_domain}")
                        break

        # 5. CAMADA 4: Brand Discovery Engine (Apenas se ainda faltar o domínio ou para alternativas)
        # Se chegamos aqui sem domínio, usamos o motor de marcas que inclui LinkedIn como plano C.
        if not found_domain:
            from .brand_discovery import discover_company_brand
            search_target = result_data["main_option"]["official_name"] if result_data["main_option"] and result_data["main_option"].get("official_name") else company_name
            print(f"[Intelligence] 🧠 Acionando BrandEngine como último recurso para '{search_target}'...")
            
            brand_res = await discover_company_brand(cnpj=cnpj or "", raw_name=search_target)
            
            if brand_res and brand_res.get("detected_domain") and not found_domain:
                found_domain = brand_res.get("detected_domain")
            
            if brand_res and brand_res.get("alternatives"):
                result_data["other_options"] = brand_res["alternatives"]
                if not found_domain:
                    found_domain = brand_res["alternatives"][0].get("domain")

        # Atualiza o resultado principal com o domínio encontrado
        if result_data["main_option"]:
            result_data["main_option"]["domain"] = found_domain
        elif found_domain:
            result_data["main_option"] = {
                "cnpj": cnpj,
                "domain": found_domain,
                "address": official.get("address") if 'official' in locals() else None,
                "official_name": official.get("name") if 'official' in locals() else company_name
            }
            result_data["success"] = True

        # 5. PERSISTÊNCIA CONDICIONAL (Auto-save apenas para empresas NOVAS)
        if result_data["main_option"] and result_data["main_option"].get("cnpj") and result_data["main_option"].get("domain"):
            try:
                async with async_session() as session:
                    # Verifica se já temos essa empresa ligada ao Pipedrive
                    fmt_cnpj = self._format_cnpj(result_data["main_option"]["cnpj"])
                    stmt = select(Organization).where(Organization.cnpj == fmt_cnpj)
                    res = await session.execute(stmt)
                    existing = res.scalars().first()
                    
                    if not existing or not existing.pipedrive_id:
                        print(f"[Intelligence] 🚀 Empresa Nova Detectada. Iniciando Auto-Save para {company_name}...")
                        
                        # 1. Cria no Pipedrive se não existir ID
                        from services.pipedrive.pipedrive_service import pipedrive_service
                        new_pid = await pipedrive_service.create_organization({
                            "name": result_data["main_option"]["official_name"] or company_name,
                            "address": result_data["main_option"]["address"],
                            "domain": result_data["main_option"]["domain"]
                        })
                        
                        # 2. Salva no Banco Local com o novo ID
                        save_data = result_data["main_option"].copy()
                        if new_pid: save_data["pipedrive_id"] = new_pid
                        
                        await self._save_org_to_db(company_name, save_data)
                        print(f"[Intelligence] ✅ Empresa nova '{company_name}' salva e sincronizada.")
                    else:
                        print(f"[Intelligence] 🛡️ Empresa já vinculada ao Pipedrive ({existing.pipedrive_id}). Auto-save ignorado para confirmação manual.")
            except Exception as e:
                print(f"[Intelligence] Erro no fluxo de auto-save condicional: {e}")

        # 🏁 Finalizado: Retorna os dados
        print(f"[Intelligence] 🏁 Enriquecimento concluído para {company_name}")
        return result_data

# Singleton
intelligence_service = IntelligenceService()
