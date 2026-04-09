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

        # 4. CAMADA 3: Brand Discovery Engine (Fallback e Enriquecimento de Alternativas)
        # Se force_refresh for True, SEMPRE rodamos para popular o carrossel com alternativas!
        if not found_domain or force_refresh:
            from .brand_discovery import discover_company_brand
            search_target = result_data["main_option"]["official_name"] if result_data["main_option"] and result_data["main_option"].get("official_name") else company_name
            print(f"[Intelligence] 🧠 Acionando BrandEngine para alternativas de '{search_target}'...")
            
            brand_res = await discover_company_brand(cnpj=cnpj or "", raw_name=search_target)
            
            # Só atualiza found_domain se ele ainda estiver vazio
            if brand_res and brand_res.get("detected_domain") and not found_domain:
                found_domain = brand_res.get("detected_domain")
                print(f"[Intelligence] 🔍 Domínio encontrado via BrandEngine: {found_domain}")
            
            # Adiciona as alternativas ao resultado para o carrossel
            if brand_res and brand_res.get("alternatives"):
                result_data["other_options"] = brand_res["alternatives"]
                if not found_domain:
                    found_domain = brand_res["alternatives"][0].get("domain")

        # 5. CAMADA 4: BUSCA DE DOMÍNIO VIA OSINT (Fallback final simplificado)
        if not found_domain:
            search_target = result_data["main_option"]["official_name"] if result_data["main_option"] and result_data["main_option"].get("official_name") else company_name
            # Limpa o "ruído" jurídico para a busca ser mais humana
            search_target = re.sub(r'\(.*?\)|LTDA|S\.A\.|EIRELI|ME|EPP|MEI|INDUSTRIA|COMERCIO|SERVICOS|BRASIL|ARMAZENAGEM|PECAS', '', search_target, flags=re.IGNORECASE).strip()
            
            # Buscas focadas tentando ignorar diretórios de CNPJ que dão falsos positivos
            queries = [
                f'site oficial "{search_target}"',
                f'"{search_target}" homepage -site:cnpj.biz -site:econodata.com.br -site:casadosdados.com.br'
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
                    blacklist = ["linkedin", "duckduckgo", "google", "facebook", "instagram", "twitter", "jusbrasil", "bing", "microsoft", "apple", "google", "youtube", "amazon"]
                    if not any(x in domain for x in blacklist) and "." in domain:
                        found_domain = domain
                        break

        # Atualiza o resultado principal com o domínio encontrado
        if result_data["main_option"]:
            result_data["main_option"]["domain"] = found_domain
        elif found_domain or results:
            result_data["main_option"] = {
                "cnpj": None,
                "domain": found_domain,
                "address": results[0].get("body")[:100] if results else None
            }
            result_data["success"] = True

        # Persistência
        if result_data["main_option"] and result_data["main_option"].get("cnpj") and result_data["main_option"].get("domain"):
            await self._save_org_to_db(company_name, result_data["main_option"])

        print(f"[Intelligence] 🏁 Finalizado para {company_name}: {result_data['main_option']}")
        return result_data

# Singleton
intelligence_service = IntelligenceService()
