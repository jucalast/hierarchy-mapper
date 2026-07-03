"""
Enriquecimento OSINT de leads para o pipeline de IA.
Extraído de data_fetcher.py para manter a responsabilidade única.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.observability.logging_config import get_logger

log = get_logger(__name__)


async def execute_osint_enrichment(
    intent_info: dict,
    org_id: Optional[int],
    session: AsyncSession,
    log_queue: Optional[asyncio.Queue] = None,
) -> Optional[Dict[str, Any]]:
    """
    Executa enriquecimento OSINT para um lead específico identificado no intent.

    Resolve nome de pessoa e empresa a partir de intent_info, chama o OSINT service
    e persiste os dados enriquecidos (email, WhatsApp, telefone) no Employee local.

    Args:
        intent_info:  dict do classificador com extracted_person_name e extracted_company_name
        org_id:       ID local da organização (usado para buscar domínio/CNPJ)
        session:      sessão assíncrona do banco
        log_queue:    fila opcional para eventos de log no frontend

    Returns:
        {"osint_result": ..., "status": "success"} em caso de sucesso,
        {"error": "..."} em caso de falha ou dados insuficientes.
    """
    from modules.context.service.service import ContextService
    from core.external.osint_service import osint_service
    from models.people.employee import Employee

    target_person = intent_info.get("extracted_person_name")
    target_company = intent_info.get("extracted_company_name")

    if not target_company and org_id:
        org_overview = await ContextService.fetch_organization_overview(session, org_id)
        target_company = org_overview.get("organization", {}).get("name")

    if not (target_person and target_company):
        return {"error": "Não consegui identificar o nome da pessoa ou da empresa para pesquisar."}

    target_domain = None
    target_cnpj = None
    if org_id:
        org_overview = await ContextService.fetch_organization_overview(session, org_id)
        org_obj = org_overview.get("organization", {})
        target_domain = org_obj.get("domain")
        target_cnpj = org_obj.get("cnpj")

    def _log(msg: str, type: str = "thought") -> None:
        log.debug("data_fetcher.osint", msg=msg)
        if log_queue:
            try:
                log_queue.put_nowait({"type": type, "content": msg})
            except Exception:
                pass

    _log(f"Executando Enriquecimento OSINT para {target_person} na {target_company}...")
    osint_data = await osint_service.enrich_lead(
        target_person, target_company, domain=target_domain, cnpj=target_cnpj
    )

    if not osint_data or "error" in osint_data:
        return {"error": osint_data.get("error", "Falha na pesquisa externa.") if osint_data else "Falha na pesquisa externa."}

    _log(f"Enriquecimento concluído: {osint_data.get('whatsapp', {}).get('numero')}")

    # Persiste no banco local para consultas futuras
    try:
        emp_q = select(Employee).where(
            Employee.company_id == org_id,
            func.lower(Employee.name).like(f"%{target_person.lower()}%"),
        )
        emp_res = await session.execute(emp_q)
        emp = emp_res.scalars().first()
        if emp:
            if osint_data.get("emailProvavel"):
                emp.email = osint_data.get("emailProvavel")
            wp = osint_data.get("whatsapp", {}).get("numero")
            if wp:
                emp.whatsapp_number = wp
            pabx = osint_data.get("pabx")
            if pabx:
                emp.phone = pabx
            session.add(emp)
            await session.commit()
            log.info("data_fetcher.osint.persisted", employee=emp.name)
    except Exception as e:
        log.warning("data_fetcher.osint.persist_failed", error=str(e))

    return {"osint_result": osint_data, "status": "success"}
