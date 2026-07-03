"""
Resolução de entidades (org_id) a partir de múltiplas fontes de entrada.
Extraído de data_fetcher.py para manter a responsabilidade única.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.observability.logging_config import get_logger

log = get_logger(__name__)


async def resolve_organization(
    payload_org_id: Optional[Any],
    selected_companies: list,
    extracted_name: Optional[str],
    message: str,
    session: AsyncSession,
    log_queue: Optional[asyncio.Queue] = None,
) -> Optional[int]:
    """
    Resolve o org_id local a partir das fontes disponíveis, em ordem de prioridade:
        1. selectedCompanies enviado pela UI (clique no card)
        2. Nome extraído pelo classificador de intenção (IA)
        3. Regex fallback sobre o texto da mensagem

    Args:
        payload_org_id:     org_id vindo diretamente do payload da request (pode ser None)
        selected_companies: lista de empresas selecionadas na UI (objetos com .id e .name)
        extracted_name:     nome de empresa extraído pelo intent_classifier
        message:            texto bruto da mensagem do usuário
        session:            sessão assíncrona do banco de dados
        log_queue:          fila opcional para emitir eventos de log para o frontend

    Returns:
        org_id (int) resolvido, ou None se não encontrado.
    """
    from modules.context.service.service import ContextService

    def _log(msg: str, type: str = "thought") -> None:
        log.debug("data_fetcher.resolve_org", msg=msg)
        if log_queue:
            try:
                log_queue.put_nowait({"type": type, "content": msg})
            except Exception:
                pass

    org_id = payload_org_id

    if selected_companies and len(selected_companies) > 0:
        org_id = selected_companies[0].id
        _log(f"Usando empresa da UI: {selected_companies[0].name}")

    elif not org_id and extracted_name:
        _log(f"Buscando empresa inferida pela IA: {extracted_name}")
        org_data = await ContextService.fetch_organization_by_name(session, extracted_name)
        if org_data:
            org_id = org_data.id
        else:
            try:
                from modules.crm.service.pipedrive_service import pipedrive_service
                _log(f"Empresa '{extracted_name}' não encontrada localmente. Buscando no Pipedrive...")
                await pipedrive_service.search_organization(extracted_name)
            except Exception as e:
                _log(f"Erro ao buscar empresa no Pipedrive: {e}", type="log")

    if not org_id:
        org_name_regex = await ContextService.extract_organization_name(message)
        if org_name_regex:
            org_data_regex = await ContextService.fetch_organization_by_name(session, org_name_regex)
            if org_data_regex:
                org_id = org_data_regex.id

    return org_id
