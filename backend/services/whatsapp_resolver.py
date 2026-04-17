"""
WhatsApp Resolver Service - Resolve referências vagas de contatos para IDs reais do WhatsApp.
Cruza dados do Banco de Dados Interno, Pipedrive e Contatos do WhatsApp.
"""

import logging
import httpx
import unicodedata
import re
from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from services.context_service import ContextService
from services.whatsapp_integration import WhatsAppIntegration
from services.pipedrive.pipedrive_service import pipedrive_service

logger = logging.getLogger(__name__)

class WhatsAppResolverService:
    """Resolve referências de contatos (nome, empresa, apelido) para chat_ids ou números."""

    @staticmethod
    async def resolve_contact(
        session: AsyncSession,
        company_name: Optional[str] = None,
        person_name: Optional[str] = None,
        person_hint: Optional[str] = None,
        phone_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Pipeline de resolução multi-fonte:
        1. Se tem número direto -> Valida no WhatsApp
        2. Se tem empresa -> Busca employees no DB e Persons no Pipedrive
        3. Se tem nome -> Busca fuzzy nos contatos do WhatsApp
        4. Cruza e ranqueia o melhor match
        """
        def normalize(text: str) -> str:
            if not text: return ""
            # Remove acentos e converte para minúsculo
            text = "".join(
                c for c in unicodedata.normalize('NFD', text.lower())
                if unicodedata.category(c) != 'Mn'
            )
            # Remove pontuação para busca fuzzy mais robusta
            return re.sub(r'[^\w\s]', ' ', text.lower()).strip()

        results = []
        name_norm = normalize(person_name or "")
        hint_norm = normalize(person_hint or "")
        search_norm = name_norm or hint_norm or normalize(company_name or "")

        # 1. RESOLUÇÃO POR NÚMERO DIRETO
        if phone_number:
            status = await WhatsAppIntegration.get_contact_status(phone_number)
            if status and status.get("status") == "found":
                return {
                    "success": True,
                    "match_type": "direct_number",
                    "contact": status,
                    "chat_id": status.get("id")
                }

        # 2. BUSCA POR NOME NO WHATSAPP (FUZZY)
        whatsapp_contacts = []
        search_term = person_name or person_hint or company_name
        if search_term:
            whatsapp_contacts = await WhatsAppIntegration.search_contact_by_name(search_term, min_similarity=0.6)
            for contact in whatsapp_contacts:
                contact["source"] = "whatsapp_contacts"
                # Calcula similaridade baseada no nome e hint se disponíveis
                c_name_norm = normalize(contact.get("name") or "")
                sim = 70
                if name_norm and name_norm in c_name_norm: sim += 15
                if hint_norm and hint_norm in c_name_norm: sim += 10
                contact["similarity"] = min(sim, 95)
                results.append(contact)

        # 3. BUSCA POR EMPRESA (DB + PIPEDRIVE)
        if company_name:
            org = await ContextService.fetch_organization_by_name(session, company_name)
            if org:
                # 3a. Employees do Banco Interno
                employees_data = await ContextService.fetch_employees_by_department(session, org.id)
                by_dept = employees_data.get("by_department", {})
                for dept, emps in by_dept.items():
                    for emp in emps:
                        emp_whatsapp = await WhatsAppIntegration.search_contact_by_name(emp["name"], min_similarity=0.8)
                        for c in emp_whatsapp:
                            c["source"] = f"db_employee_{org.name}"
                            c["original_emp"] = emp
                            # Boost se o nome bater exatamente com o que a IA extraiu
                            c_name_norm = normalize(c.get("name") or "")
                            sim = 75
                            if name_norm and name_norm in c_name_norm: sim += 15
                            c["similarity"] = sim
                            results.append(c)

                # 3b. Persons do Pipedrive
                if org.pipedrive_id:
                    pd_details = await pipedrive_service.get_organization_details(org.pipedrive_id)
                    persons = pd_details.get("persons", [])
                    for p in persons:
                        phones = p.get("phone", [])
                        for phone_obj in phones:
                            phone_val = phone_obj.get("value")
                            if phone_val:
                                status = await WhatsAppIntegration.get_contact_status(phone_val)
                                if status and status.get("status") == "found":
                                    status["source"] = "pipedrive_person"
                                    status["name"] = p.get("name")
                                    status["similarity"] = 90
                                    pic_data = p.get("picture_id")
                                    if isinstance(pic_data, dict) and pic_data.get("pictures"):
                                        status["profilePicture"] = pic_data.get("pictures", {}).get("128") or pic_data.get("pictures", {}).get("512")
                                    results.append(status)
                        
                        if not phones:
                            p_whatsapp = await WhatsAppIntegration.search_contact_by_name(p["name"], min_similarity=0.8)
                            for c in p_whatsapp:
                                c["source"] = "pipedrive_person_name_match"
                                c["similarity"] = 80
                                results.append(c)

        # 4. BUSCA POR CHATS ATIVOS (FILTRAGEM MANUAL PARA SER ROBUSTO COM ACENTOS)
        if search_norm:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"http://localhost:8001/api/whatsapp/chats")
                    if resp.status_code == 200:
                        data = resp.json()
                        active_chats = data.get("chats", []) if isinstance(data, dict) else data
                        for chat in active_chats:
                            chat_name = chat.get("name") or ""
                            chat_norm = normalize(chat_name)
                            
                            # Match parcial ou total
                            if search_norm in chat_norm or chat_norm in search_norm:
                                chat["source"] = "active_chat"
                                
                                # Scoring Inteligente
                                score = 80
                                # Se o nome extraído pela IA bate exatamente
                                if name_norm and name_norm == chat_norm:
                                    score = 100
                                # Se o match contém tanto o nome quanto a dica (Ex: João + Pessoal)
                                elif name_norm and hint_norm and name_norm in chat_norm and hint_norm in chat_norm:
                                    score = 98
                                # Se bate apenas o nome principal (Match parcial forte)
                                elif name_norm and name_norm in chat_norm:
                                    score = 85
                                # Se bate apenas a dica
                                elif hint_norm and hint_norm in chat_norm:
                                    score = 75
                                    
                                chat["similarity"] = score
                                results.append(chat)
            except Exception as e:
                logger.error(f"Erro ao buscar chats ativos: {e}")

        # 5. FILTRAGEM E RANKING
        if not results:
            return {"success": False, "message": "Nenhum contato correspondente encontrado."}

        # Deduplicação por ID
        unique_matches = {}
        for r in results:
            cid = r.get("id") or r.get("number")
            if not cid: continue
            
            # Se já existe, pega a maior similaridade e dá um pequeno bônus por estar em múltiplas fontes
            if cid in unique_matches:
                unique_matches[cid]["confidence"] = max(unique_matches[cid]["confidence"], r.get("similarity", 70)) + 2
                if r.get("source") not in unique_matches[cid]["sources"]:
                    unique_matches[cid]["sources"].append(r.get("source"))
            else:
                r["confidence"] = r.get("similarity", 70)
                r["sources"] = [r.get("source")]
                unique_matches[cid] = r

        # Ordena por confiança
        sorted_matches = sorted(unique_matches.values(), key=lambda x: x["confidence"], reverse=True)
        
        best_match = sorted_matches[0]
        
        return {
            "success": True,
            "match_type": "resolved",
            "best_match": best_match,
            "chat_id": best_match.get("id"),
            "all_matches": sorted_matches[:5]
        }
