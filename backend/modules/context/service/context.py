"""
Serviço de contexto para RAG - Busca internamente dados do banco e passa como contexto para IA.

Otimizações:
- Usa `selectinload(Organization.employees)` para evitar N+1 queries.
- Funções auxiliares aceitam objeto Organization já carregado.
"""
import re
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.people.employee import Employee
from models.organization import Organization

class ContextService:
    """Serviço para extrair contexto de dados internos do banco."""
    
    @staticmethod
    async def extract_organization_name(message: str) -> Optional[str]:
        """
        Extrai nome de organização mencionada na mensagem.
        Ex: "O que você vê da Knorr?" -> "Knorr"
        """
        # Remove caracteres especiais e normaliza
        words = re.findall(r'\b[A-Za-z]{2,}\b', message)
        
        # Procura por palavras que podem ser nomes de empresa
        org_indicators = ['da ', 'de ', 'da empresa ', 'da companhia ']
        
        for indicator in org_indicators:
            if indicator in message.lower():
                idx = message.lower().index(indicator) + len(indicator)
                remaining = message[idx:].split()[0]
                if remaining and len(remaining) > 2:
                    return remaining.strip('.,;:!?')
        
        # Se não encontrar padrão, tenta pegar última palavra grande (potencial nome de empresa)
        for word in reversed(words):
            if len(word) > 3 and word[0].isupper():
                return word
        
        return None
    
    @staticmethod
    async def classify_question_intent(message: str) -> str:
        """
        Classifica o tipo de pergunta para determinar que dados buscar.
        
        Returns:
            - "overview": Visão geral da organização
            - "employees": Sobre funcionários específicos
            - "decision_makers": Sobre tomadores de decisão
            - "contacts": Sobre contatos específicos
            - "supply_chain": Sobre cadeia de suprimento
            - "general": Pergunta geral
        """
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['funcionário', 'employee', 'contato', 'contact', 'pessoas', 'people']):
            if any(word in message_lower for word in ['chance', 'likely', 'probabilidade', 'mais']):
                return "decision_makers"
            return "employees"
        
        if any(word in message_lower for word in ['compra', 'comprador', 'buyer', 'decision', 'decisão', 'poder', 'influência']):
            return "decision_makers"
        
        if any(word in message_lower for word in ['contato', 'email', 'telefone', 'phone', 'contact', 'reach']):
            return "contacts"
        
        if any(word in message_lower for word in ['fornecedor', 'supplier', 'cadeia', 'chain', 'parceiro', 'partner']):
            return "supply_chain"
        
        if any(word in message_lower for word in ['que você vê', 'o que tem', 'pode me dizer', 'qual é', 'what do you']):
            return "overview"
        
        return "general"
    
    @staticmethod
    async def fetch_organization_by_name(session: AsyncSession, org_name: str) -> Optional[Organization]:
        """Busca organização pelo nome (case-insensitive)."""
        stmt = select(Organization).where(
            func.lower(Organization.name).like(f"%{org_name.lower()}%")
        )
        result = await session.execute(stmt)
        return result.scalars().first()
    
    @staticmethod
    async def fetch_organization_overview(session: AsyncSession, org_id: int) -> Dict:
        """Busca visão geral da organização (Tenta por ID local e ID Pipedrive)."""
        org_stmt = (
            select(Organization)
            .options(selectinload(Organization.employees))
            .where((Organization.id == org_id) | (Organization.pipedrive_id == org_id))
        )
        org_result = await session.execute(org_stmt)
        org = org_result.scalars().first()

        if not org:
            return {}

        employees = [e for e in org.employees if e.role != "Reprovado" and e.department != "Reprovado"]

        # Busca estatísticas
        total_mapped = len(employees)
        departments = list({e.department for e in employees if e.department})
        
        # Prepara dados dos funcionários com fotos para o frontend
        employees_data = []
        try:
            for emp in employees:
                employees_data.append({
                    "id": emp.id,
                    "name": emp.name,
                    "profile_pic": emp.profile_pic,
                    "role": emp.role,
                    "department": emp.department
                })
        except Exception as e:
            print(f"[ContextService] Erro ao processar funcionários: {e}")
            # Continua sem os dados de funcionários se houver erro
        
        return {
            "organization": {
                "id": org.id,
                "name": org.name,
                "cnpj": org.cnpj,
                "domain": org.domain,
                "address": org.address,
                "pipedrive_id": org.pipedrive_id,
                "category": org.category,
                "product_focus": org.product_focus,
                "linkedin_url": org.linkedin_url,
                "description": org.description,
                "logo": org.logo_url,
                "employees_count": total_mapped,
                "employees": employees_data
            },
            "statistics": {
                "total_employees_mapped": total_mapped,
                "departments": departments,
                "last_enrichment": org.last_enrichment.isoformat() if org.last_enrichment else None
            }
        }
    
    @staticmethod
    async def fetch_decision_makers(session: AsyncSession, org_id: int) -> Dict:
        """Busca potenciais tomadores de decisão (C-level, gerentes, quadro societário)."""
        # Filtra direto no SQL: só funcionários com depto/role relevantes (reduz set)
        # Tenta resolver ID Local ou Pipedrive
        emp_stmt = select(Employee).where(
            Employee.company_id.in_(
                select(Organization.id).where(
                    (Organization.id == org_id) | (Organization.pipedrive_id == org_id)
                )
            ),
            Employee.role != "Reprovado",
            Employee.department != "Reprovado"
        )
        emp_result = await session.execute(emp_stmt)
        employees = emp_result.scalars().all()
        
        # Classifica por potencial de decisão
        decision_levels = []
        
        for emp in employees:
            role_lower = (emp.role or "").lower()
            dept_lower = (emp.department or "").lower()
            
            # Score de influência
            score = 0
            
            # C-level
            if any(x in role_lower for x in ['ceo', 'cfo', 'cto', 'coo', 'diretor', 'president', 'founder']):
                score = 100
            # Quadro Societário
            elif any(x in dept_lower for x in ['quadro societário', 'sócio', 'sharehol']):
                score = 90
            # Gerência
            elif any(x in role_lower for x in ['gerente', 'manager', 'head', 'líder', 'chief']):
                score = 75
            # Compras/Procurement
            elif any(x in dept_lower for x in ['compra', 'procurement', 'sourcing']):
                score = 70
            
            if score > 0:
                decision_levels.append({
                    "name": emp.name,
                    "role": emp.role,
                    "department": emp.department,
                    "linkedin": emp.linkedin_url,
                    "email": emp.email,
                    "phone": emp.phone,
                    "whatsapp_number": emp.whatsapp_number,
                    "influence_score": score
                })
        
        # Ordena por score
        decision_levels.sort(key=lambda x: x["influence_score"], reverse=True)
        
        return {
            "decision_makers": decision_levels[:10],  # Top 10
            "total": len(decision_levels)
        }
    
    @staticmethod
    async def fetch_employees_by_department(session: AsyncSession, org_id: int, department: str = None) -> Dict:
        """Busca funcionários por departamento."""
        query = select(Employee).where(
            Employee.company_id.in_(
                select(Organization.id).where(
                    (Organization.id == org_id) | (Organization.pipedrive_id == org_id)
                )
            ),
            Employee.role != "Reprovado",
            Employee.department != "Reprovado"
        )
        
        if department:
            query = query.where(func.lower(Employee.department).like(f"%{department.lower()}%"))
        
        result = await session.execute(query)
        employees = result.scalars().all()
        
        # Agrupa por departamento
        by_dept = {}
        for emp in employees:
            dept = emp.department or "Não definido"
            if dept not in by_dept:
                by_dept[dept] = []
            by_dept[dept].append({
                "name": emp.name,
                "role": emp.role,
                "email": emp.email,
                "linkedin": emp.linkedin_url,
                "phone": emp.phone,
                "whatsapp_number": emp.whatsapp_number,
                "seniority": emp.seniority
            })
        
        return {
            "by_department": by_dept,
            "total_employees": len(employees)
        }
    
    @staticmethod
    async def build_context_for_ai(
        session: AsyncSession,
        org_id: int,
        intent: str = "overview"
    ) -> Dict:
        """
        Monta contexto estruturado baseado no intent da pergunta.
        """
        context = {}
        
        if intent == "overview":
            context = await ContextService.fetch_organization_overview(session, org_id)
        
        elif intent == "decision_makers":
            overview = await ContextService.fetch_organization_overview(session, org_id)
            decision_makers = await ContextService.fetch_decision_makers(session, org_id)
            context = {**overview, "decision_makers": decision_makers}
        
        elif intent == "employees":
            employees = await ContextService.fetch_employees_by_department(session, org_id)
            overview = await ContextService.fetch_organization_overview(session, org_id)
            context = {**overview, "employees": employees}
        
        elif intent == "contacts":
            contacts = await ContextService.fetch_contacts_with_whatsapp(session, org_id)
            overview = await ContextService.fetch_organization_overview(session, org_id)
            context = {**overview, "contacts": contacts}
        
        elif intent == "supply_chain":
            # TODO: Implementar busca de relacionamentos/parceiros
            overview = await ContextService.fetch_organization_overview(session, org_id)
            context = {**overview, "supply_chain": "Dados de cadeia de suprimento"}
        
        else:  # general
            context = await ContextService.fetch_organization_overview(session, org_id)
        
        return context
    
    @staticmethod
    async def fetch_contacts_with_whatsapp(
        session: AsyncSession,
        org_id: int,
        limit: int = 10
    ) -> Dict:
        """
        Busca contatos de uma organização e enriquece com dados do WhatsApp.
        
        Cada contato retorna:
        {
            "name": "João Silva",
            "role": "Gerente de Vendas",
            "department": "Commercial",
            "email": "joao@empresa.com",
            "phone": "5511987654321",
            "whatsapp_active": true,
            "whatsapp_status": "found",
            "whatsapp_data": {...}  # if found
        }
        """
        from modules.communication.service.whatsapp.integration import WhatsAppIntegration
        import asyncio
        
        try:
            # Buscar empregados da organização (Tenta por ID local e ID Pipedrive)
            stmt = select(Employee).where(
                Employee.company_id.in_(
                    select(Organization.id).where(
                        (Organization.id == org_id) | (Organization.pipedrive_id == org_id)
                    )
                ),
                Employee.role != "Reprovado",
                Employee.department != "Reprovado"
            ).limit(limit)
            result = await session.execute(stmt)
            employees = result.scalars().all()
            
            if not employees:
                return {"status": "no_contacts", "count": 0, "contacts": []}
            
            # Remover duplicatas e preparar para enriquecimento
            contact_list = []
            for emp in employees:
                contact_data = {
                    "name": emp.name,
                    "role": emp.role or "Não especificado",
                    "department": emp.department or "Não especificado",
                    "email": emp.email or "",
                    "linkedin": emp.linkedin_url or "",
                    "phone": emp.phone or emp.linkedin_url or "",  # Fallback pro linkedin caso o banco antigo tenha lá
                    "whatsapp_number": emp.whatsapp_number or "",
                    "seniority": emp.seniority or "Não especificado"
                }
                contact_list.append(contact_data)
            
            # Enriquecer com dados do WhatsApp (paralelo)
            enriched_contacts = await WhatsAppIntegration.enrich_employees_batch(contact_list)
            
            # Filtrar para apenas contatos encontrados no WhatsApp (priority)
            found_contacts = [c for c in enriched_contacts if c.get("whatsapp_active")]
            other_contacts = [c for c in enriched_contacts if not c.get("whatsapp_active")]
            
            # Ordenar: ativos primeiro, depois outros
            sorted_contacts = found_contacts + other_contacts
            
            return {
                "status": "success",
                "count": len(sorted_contacts),
                "found_on_whatsapp": len(found_contacts),
                "contacts": sorted_contacts[:limit]
            }
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erro ao buscar contatos com WhatsApp: {str(e)}")
            return {
                "status": "error",
                "count": 0,
                "contacts": [],
                "error": str(e)
            }
