"""
modules.communication.service.email_resolver
============================================
Resolve o melhor e-mail disponível para contato B2B com hierarquia de prioridade.

Hierarquia de resolução:
  1. E-mail verificado do decisor (alta confiança)
  2. compras@domínio → suprimentos@ → procurement@ → contato@ (certeiro genérico)
  3. Retorna None se domínio não puder ser determinado
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.observability.logging_config import get_logger

log = get_logger(__name__)

# Prefixos tentados em ordem de prioridade para e-mails de departamento
PROCUREMENT_PREFIXES = ["compras", "suprimentos", "procurement", "contato"]


@dataclass
class EmailResolution:
    email: str
    type: str           # "decisor" | "procurement"
    confidence: float   # 0.0 a 1.0
    domain: str = ""
    cc_emails: list[str] = field(default_factory=list)


async def resolve_procurement_email(
    org_name: str = "",
    org_id: Optional[int] = None,
    contact_email: str = "",
) -> Optional[EmailResolution]:
    """
    Resolve o melhor e-mail para contato com uma organização B2B.

    Se contact_email já estiver preenchido (decisor conhecido), retorna ele como
    principal e adiciona compras@domínio na lista de CC.

    Se não houver e-mail do decisor, extrai o domínio da organização e retorna
    compras@domínio como e-mail principal (com variantes como CC).

    Retorna None se o domínio não puder ser determinado.
    """
    from modules.agent.service.tools._utils import _extract_org_domain

    if contact_email and "@" in contact_email:
        domain = contact_email.split("@")[1].lower()
        cc = [f"compras@{domain}"]
        log.info(
            "email_resolver.decisor_known",
            email=contact_email,
            domain=domain,
            cc=cc,
        )
        return EmailResolution(
            email=contact_email,
            type="decisor",
            confidence=1.0,
            domain=domain,
            cc_emails=cc,
        )

    domain = await _extract_org_domain(org_name, org_id=org_id)
    if not domain:
        log.warning("email_resolver.no_domain", org=org_name, org_id=org_id)
        return None

    primary = f"{PROCUREMENT_PREFIXES[0]}@{domain}"
    cc = [f"{p}@{domain}" for p in PROCUREMENT_PREFIXES[1:]]

    log.info(
        "email_resolver.procurement_resolved",
        email=primary,
        cc=cc,
        org=org_name,
        domain=domain,
    )
    return EmailResolution(
        email=primary,
        type="procurement",
        confidence=0.7,
        domain=domain,
        cc_emails=cc,
    )
