"""
Verifica duplicatas no Pipedrive antes de sugerir um lead.

Regras:
- Empresa com deal ativo e atividade recente (< 6 meses) → "active" → não sugere
- Empresa com deal perdido ("lost") → "lost_deal" → elegível (nova tentativa)
- Empresa existe mas sem atividade há > 6 meses → "stale" → elegível (reaquecimento)
- Empresa não existe no Pipedrive → "new" → elegível
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from core.logging_config import get_logger

log = get_logger(__name__)

STALE_MONTHS = 6


async def check_pipedrive_duplicate(
    company_name: str,
    domain: Optional[str] = None,
    cnpj: Optional[str] = None,
) -> dict:
    """
    Retorna:
        {
            "status": "new" | "active" | "lost_deal" | "stale",
            "org_id": int | None,
            "last_activity": datetime | None,
            "deal_info": dict | None,
        }
    """
    from services.pipedrive.pipedrive_service import pipedrive_service

    result: dict = {
        "status": "new",
        "org_id": None,
        "last_activity": None,
        "deal_info": None,
    }

    # Estratégia de busca progressiva
    search_terms = []
    
    # 1. Nome completo
    search_terms.append(company_name)
    
    # 2. Nome limpo (sem Ltda, S.A, etc)
    clean_name = _clean_name(company_name)
    if clean_name != company_name:
        search_terms.append(clean_name)
        
    # 3. Domínio (identificador muito forte)
    if domain:
        search_terms.append(domain)
        
    # 4. Primeira palavra (Ex: "Cipec" de "Cipec Industrial")
    first_word = company_name.split()[0].strip()
    if len(first_word) >= 3 and first_word.lower() not in ["empresa", "grupo", "cia", "soluções"]:
        if first_word not in search_terms:
            search_terms.append(first_word)

    orgs = []
    for term in search_terms:
        try:
            orgs = await pipedrive_service.search_organization(term)
            if orgs:
                # Se buscamos por uma palavra curta, validamos se o resultado faz sentido
                # para evitar que "Cipec" bata com "Cipreste", por exemplo.
                top_org = orgs[0]
                found_name = top_org.get("name", "").lower()
                target_name = company_name.lower()
                
                # Critério: O nome no Pipedrive deve estar contido no nome do prospect ou vice-versa
                if term == company_name or term == domain:
                    # Busca exata ou por domínio é confiável
                    log.info("prospect.dedup.found", term=term, org_id=top_org.get("id"))
                    break
                elif found_name in target_name or target_name in found_name:
                    log.info("prospect.dedup.found_partial", term=term, found=found_name, org_id=top_org.get("id"))
                    break
                else:
                    # Falso positivo provável (ex: "Cipec" vs "Cipreste")
                    orgs = []
                    continue
        except Exception as e:
            log.warning("prospect.dedup.search_failed", term=term, error=str(e))

    if not orgs:
        return result

    org = orgs[0]
    org_id = org.get("id")
    result["org_id"] = org_id

    deals = await _get_org_deals(org_id)

    if not deals:
        # Empresa existe no Pipedrive mas nunca teve deal — consideramos stale
        result["status"] = "stale"
        return result

    active_deals = [d for d in deals if d.get("status") == "open"]
    lost_deals = [d for d in deals if d.get("status") == "lost"]

    if active_deals:
        last_act = await _get_last_activity_date(org_id)
        result["last_activity"] = last_act

        months_inactive = _months_since(last_act)
        if last_act and months_inactive >= STALE_MONTHS:
            result["status"] = "stale"
        else:
            result["status"] = "active"

        result["deal_info"] = _summarize_deal(active_deals[0], months_inactive)

    elif lost_deals:
        result["status"] = "lost_deal"
        result["deal_info"] = _summarize_deal(lost_deals[-1], None)

    return result


def _clean_name(name: str) -> str:
    # Remove sufixos jurídicos comuns e lixo de SEO
    suffixes = [
        r"\s+Ltda\.?.*", r"\s+S\.?A\.?.*", r"\s+Eireli.*", r"\s+MEI?.*", 
        r"\s+EPP.*", r"\s+Serviços.*", r"\s+Indústria.*", r"\s+Comércio.*",
        r"\s+\-.*", r"\s+\|.*"
    ]
    clean = name
    for pattern in suffixes:
        clean = re.sub(pattern, "", clean, flags=re.IGNORECASE)
    return clean.strip()


async def _get_org_deals(org_id: int) -> list:
    from services.pipedrive.pipedrive_service import pipedrive_service
    try:
        resp = await pipedrive_service._request(
            "GET", f"organizations/{org_id}/deals", params={"limit": 20, "status": "all_not_deleted"}
        )
        if resp and resp.status_code == 200:
            return resp.json().get("data") or []
    except Exception as e:
        log.warning("prospect.dedup.deals_failed", org_id=org_id, error=str(e))
    return []


async def _get_last_activity_date(org_id: int) -> Optional[datetime]:
    from services.pipedrive.pipedrive_service import pipedrive_service
    try:
        resp = await pipedrive_service._request(
            "GET", f"organizations/{org_id}/activities",
            params={"limit": 1, "done": 1},
        )
        if resp and resp.status_code == 200:
            data = resp.json().get("data") or []
            if data:
                raw = data[0].get("due_date") or data[0].get("add_time", "")
                if raw:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception as e:
        log.warning("prospect.dedup.activities_failed", org_id=org_id, error=str(e))
    return None


def _months_since(dt: Optional[datetime]) -> float:
    if not dt:
        return 0.0
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days / 30


def _summarize_deal(deal: dict, months_inactive: Optional[float]) -> dict:
    return {
        "title": deal.get("title"),
        "status": deal.get("status"),
        "stage_id": deal.get("stage_id"),
        "value": deal.get("value"),
        "days_inactive": int((months_inactive or 0) * 30),
    }
