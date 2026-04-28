"""
Cold Lead Service — detecta empresas frias e prepara contexto para o agente.

Uma empresa é considerada "fria" quando:
  - Tem 0 mensagens WhatsApp E 0 threads email com qualquer contato
  - Mas pode já ter funcionários mapeados no banco (is_discovery=1 ou source='linkedin')

O serviço:
  1. Recebe o raw_context já montado pelo agente
  2. Detecta se é lead frio
  3. Se frio + tem employees mapeados → injeta como cold contacts no context
  4. Se frio + sem employees → retorna suggest_mapping=True

Não modifica nenhum dado existente. Apenas enriquece o contexto.
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from models.employee import Employee


COLD_LEAD_DEPT_PRIORITY = [
    "compras", "suprimentos", "supply chain", "procurement",
    "materiais", "logística", "logistica", "operações", "operacoes",
    "industrial", "produção", "producao",
]


def is_cold_lead(raw_context: dict) -> bool:
    """
    Retorna True se a empresa não tem histórico de comunicação real.
    Considera whatsapp E email. Se ambos zerados → lead frio.
    """
    wa_msgs = 0
    email_threads = 0

    # Conta mensagens de WhatsApp
    wa_result = raw_context.get("whatsapp_result", {})
    if isinstance(wa_result, dict):
        resultado = wa_result.get("resultado", {})
        msgs = resultado.get("messages", [])
        wa_msgs = len(msgs) if isinstance(msgs, list) else 0
        # também checa messages_by_contact
        by_contact = resultado.get("messages_by_contact", [])
        if isinstance(by_contact, list):
            for bc in by_contact:
                wa_msgs += len(bc.get("messages", []))

    # Conta threads de email
    email_result = raw_context.get("email_result", {})
    if isinstance(email_result, dict):
        threads = email_result.get("threads", []) or email_result.get("messages", [])
        email_threads = len(threads) if isinstance(threads, list) else 0

    return wa_msgs == 0 and email_threads == 0


async def get_mapped_employees_for_cold_outreach(
    org_id: int,
    session: AsyncSession,
    max_contacts: int = 5,
) -> list:
    """
    Busca funcionários já mapeados no banco para uma org,
    priorizando departamentos de compras/suprimentos.
    Retorna lista de dicts prontos para injeção no contact_map.
    """
    # Busca todos os funcionários com email ou linkedin
    stmt = select(Employee).where(
        and_(
            Employee.company_id == org_id,
            Employee.seniority.in_([2, 3, 4, 5]),  # exclui júnior (1) e board (6)
        )
    ).order_by(Employee.seniority.desc(), Employee.matching_score.desc())

    result = await session.execute(stmt)
    employees = result.scalars().all()

    if not employees:
        return []

    # Prioriza por departamento de compras
    def dept_priority(emp: Employee) -> int:
        dept = (emp.department or "").lower()
        role = (emp.role or "").lower()
        for i, kw in enumerate(COLD_LEAD_DEPT_PRIORITY):
            if kw in dept or kw in role:
                return i
        return len(COLD_LEAD_DEPT_PRIORITY)

    sorted_emps = sorted(employees, key=lambda e: (dept_priority(e), -(e.seniority or 0)))

    contacts = []
    for emp in sorted_emps[:max_contacts]:
        contacts.append({
            "name": emp.name,
            "role": emp.role,
            "department": emp.department,
            "seniority": emp.seniority,
            "email": emp.email,
            "phone": emp.phone,
            "linkedin_url": emp.linkedin_url,
            "source": emp.source or "linkedin",
            "is_cold_contact": True,          # flag para o agente tratar como cold outreach
            "email_available": bool(emp.email),
            # WA nunca está "disponível" para cold leads — não há histórico de conversa.
            # Ter telefone não significa que há conta WA ou que João já conversou com eles.
            "whatsapp_available": False,
            "channels": (["Email"] if emp.email else []) + (["Telefone"] if emp.phone else []),
            "preferred_channel": "Email" if emp.email else "Nenhum",
            "wa_msg_count": 0,
            "email_msg_count": 0,
        })

    return contacts
