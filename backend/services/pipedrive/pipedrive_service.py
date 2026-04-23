"""
services.pipedrive.pipedrive_service
====================================

Refatorado para:
  * usar o cliente HTTP singleton (`core.http_client`) — reaproveita conexões,
    HTTP/2, pool com limites sãos;
  * aplicar circuit breaker (`core.resilience`) e métricas Prometheus;
  * centralizar rate-limit/Retry-After em todos os métodos (via `_request`);
  * cache TTL do mapa de estágios (`core.cache`);
  * logging estruturado (structlog) com `correlation_id` do middleware;
  * preservar 100% das assinaturas públicas existentes
    (list_organizations, create_organization, get_organization_details,
    update_organization, update_person, delete_organization,
    create_activity, update_activity, delete_activity, create_person,
    sync_overdue_activities, smart_reschedule_activities, update_deal,
    get_person_details, get_all_stages, get_retry_after_seconds, get_client).

Obs.: Mantém o singleton `pipedrive_service` exportado no final do módulo.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

from core.cache import get_cache
from core.config import settings
from core.http_client import get_http_client
from core.logging_config import get_logger
from core.metrics import external_api_requests_total, update_circuit_metric
from core.resilience import CircuitOpenError, get_breaker

log = get_logger(__name__)


# =============================================================================
# Serviço
# =============================================================================

class PipedriveService:
    _stages_cache: Dict[int, str] = {}
    _retry_after_until: float = 0.0
    _semaphore: asyncio.Semaphore = asyncio.Semaphore(
        max(1, settings.pipedrive.concurrency_limit)
    )

    def __init__(self) -> None:
        self.api_token = settings.PIPEDRIVE_API_TOKEN
        self.user_id = settings.PIPEDRIVE_USER_ID
        self.base_url = "https://api.pipedrive.com/v1"
        self._breaker = get_breaker("pipedrive")
        self._stages_cache_store = get_cache(
            "pipedrive.stages",
            ttl_sec=settings.pipedrive.cache_stages_ttl_sec,
            max_entries=8,
        )

    # ---------------------------------------------------------------------
    # Compatibilidade
    # ---------------------------------------------------------------------

    async def get_client(self) -> httpx.AsyncClient:
        """Retorna o cliente HTTP compartilhado.

        Mantido por compat. Sempre devolve o singleton global.
        """
        return get_http_client()

    def get_retry_after_seconds(self) -> int:
        remaining = int(PipedriveService._retry_after_until - time.time())
        return max(0, remaining)

    def _update_retry_after(self, resp: httpx.Response) -> None:
        if resp.status_code != 429:
            return
        retry_after = resp.headers.get("retry-after")
        if retry_after:
            try:
                PipedriveService._retry_after_until = time.time() + int(retry_after) + 0.5
                log.warning(
                    "pipedrive.rate_limited",
                    retry_after=int(retry_after),
                )
            except Exception:
                pass

    # ---------------------------------------------------------------------
    # URLs
    # ---------------------------------------------------------------------

    def _url(self, endpoint: str, **extra_qs: Any) -> str:
        """Monta URL já com api_token e querystring extra."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        sep = "&" if "?" in url else "?"
        url += f"{sep}api_token={self.api_token}"
        for k, v in extra_qs.items():
            if v is None:
                continue
            url += f"&{k}={v}"
        return url

    # ---------------------------------------------------------------------
    # Core: requisição com rate-limit, breaker e métricas
    # ---------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json: Any = None,
        params: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> Optional[httpx.Response]:
        try:
            self._breaker.ensure_available()
        except CircuitOpenError:
            update_circuit_metric(self._breaker.name, True)
            log.warning("pipedrive.circuit_open")
            external_api_requests_total.labels(
                service="pipedrive", endpoint=endpoint, outcome="circuit_open"
            ).inc()
            return None

        url = self._url(endpoint)
        client = get_http_client()
        t_out = timeout or settings.pipedrive.request_timeout_sec

        async with PipedriveService._semaphore:
            wait = PipedriveService._retry_after_until - time.time()
            if wait > 0:
                log.info("pipedrive.cooldown_wait", seconds=int(wait))
                await asyncio.sleep(wait)

            try:
                resp = await client.request(
                    method, url, json=json, params=params, timeout=t_out
                )
            except Exception as e:
                log.warning(
                    "pipedrive.network_error",
                    endpoint=endpoint,
                    error=f"{type(e).__name__}: {e}",
                )
                self._breaker.record_failure(reason="network_error")
                update_circuit_metric(self._breaker.name, True)
                external_api_requests_total.labels(
                    service="pipedrive", endpoint=endpoint, outcome="error"
                ).inc()
                return None

            if resp.status_code == 429:
                self._update_retry_after(resp)
                wait = PipedriveService._retry_after_until - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                    try:
                        resp = await client.request(
                            method, url, json=json, params=params, timeout=t_out
                        )
                    except Exception as e:
                        log.warning(
                            "pipedrive.network_error_retry",
                            endpoint=endpoint,
                            error=f"{type(e).__name__}: {e}",
                        )
                        self._breaker.record_failure(reason="network_error_retry")
                        external_api_requests_total.labels(
                            service="pipedrive", endpoint=endpoint, outcome="error"
                        ).inc()
                        return None

            outcome = "success" if resp.status_code < 400 else (
                "rate_limited" if resp.status_code == 429 else "error"
            )
            external_api_requests_total.labels(
                service="pipedrive", endpoint=endpoint, outcome=outcome
            ).inc()

            if 200 <= resp.status_code < 500 and resp.status_code != 429:
                # sucesso ou erro de cliente — não abre breaker
                self._breaker.record_success()
                update_circuit_metric(self._breaker.name, False)
            elif resp.status_code >= 500:
                self._breaker.record_failure(reason=f"http_{resp.status_code}")
                update_circuit_metric(self._breaker.name, True)

            return resp

    async def make_request(self, method: str, endpoint: str, **kwargs) -> Optional[httpx.Response]:
        """Assinatura antiga — permanece para compat. Internamente usa `_request`."""
        return await self._request(
            method,
            endpoint,
            json=kwargs.get("json"),
            params=kwargs.get("params"),
            timeout=kwargs.get("timeout"),
        )

    # ---------------------------------------------------------------------
    # Stages (cache TTL)
    # ---------------------------------------------------------------------

    async def get_all_stages(self) -> Dict[int, str]:
        """Retorna mapeamento {stage_id: stage_name} (retrocompatível)."""
        full = await self.get_all_stages_full()
        return {sid: info["name"] for sid, info in full.items()}

    async def get_all_stages_full(self) -> Dict[int, dict]:
        """Retorna mapeamento {stage_id: {name, order_nr, pipeline_id}} com cache TTL."""
        cache_key = "all_full"
        cached = self._stages_cache_store.get(cache_key)
        if isinstance(cached, dict) and cached:
            return cached

        resp = await self._request("GET", "stages")
        if resp is not None and resp.status_code == 200:
            s_data = resp.json().get("data") or []
            mapping: Dict[int, dict] = {
                s["id"]: {
                    "name": s.get("name", ""),
                    "order_nr": s.get("order_nr", 0),
                    "pipeline_id": s.get("pipeline_id", 1),
                }
                for s in s_data
            }
            self._stages_cache_store.set(cache_key, mapping)
            # Mantém cache legado sincronizado
            PipedriveService._stages_cache = {sid: info["name"] for sid, info in mapping.items()}
            return mapping
        return {}

    # ---------------------------------------------------------------------
    # CRUD — Organizations
    # ---------------------------------------------------------------------

    async def search_organization(self, term: str) -> List[dict]:
        """Busca organização por nome no Pipedrive (via /itemSearch ou /organizations/search)."""
        resp = await self._request(
            "GET",
            "organizations/search",
            params={"term": term, "limit": 10},
        )
        if resp is not None and resp.status_code == 200:
            try:
                data = resp.json()
                if data.get("success"):
                    # O endpoint /search retorna os itens dentro de 'data' -> 'items'
                    items = data.get("data", {}).get("items") or []
                    return [i.get("item") for i in items if i.get("item")]
            except Exception as e:
                log.warning("pipedrive.org.search_failed", error=str(e))
        return []

    async def create_organization(self, data: dict) -> Optional[int]:
        payload = {
            "name": data.get("name"),
            "address": data.get("address"),
            "website": data.get("domain"),
        }
        resp = await self._request("POST", "organizations", json=payload)
        if resp is None:
            return None
        try:
            res_data = resp.json()
            if res_data.get("success"):
                org_id = res_data["data"]["id"]
                log.info("pipedrive.org.created", org_id=org_id, name=data.get("name"))
                return org_id
        except Exception as e:
            log.warning("pipedrive.org.create_failed", error=str(e))
        return None

    async def get_person_details(self, person_id: int) -> Optional[dict]:
        resp = await self._request("GET", f"persons/{person_id}")
        if resp is not None and resp.status_code == 200:
            return resp.json().get("data")
        return None

    async def update_activity(self, activity_id: int, data: dict) -> bool:
        """Atualiza atividade existente (via `_request`)."""
        resp = await self._request("PUT", f"activities/{activity_id}", json=data)
        if resp is None:
            return False
        try:
            res_data = resp.json()
            if res_data.get("success"):
                log.info("pipedrive.activity.updated", activity_id=activity_id)
                return True
        except Exception as e:
            log.warning("pipedrive.activity.update_failed", error=str(e))
        return False

    async def delete_activity(self, activity_id: int) -> bool:
        resp = await self._request("DELETE", f"activities/{activity_id}")
        if resp is None:
            return False
        try:
            if resp.status_code == 204:
                return True
            res_data = resp.json()
            if res_data.get("success"):
                log.info("pipedrive.activity.deleted", activity_id=activity_id)
                return True
        except Exception as e:
            log.warning("pipedrive.activity.delete_failed", error=str(e))
        return False

    async def update_organization(self, org_id: int, data: dict) -> bool:
        """Atualiza Endereço, CNPJ e Domínio no Pipedrive e no Banco Local."""
        from core.database import async_session
        from models import Organization
        from sqlalchemy import select

        payload: Dict[str, Any] = {}
        if data.get("address"):
            payload["address"] = data.get("address")
        if data.get("domain"):
            payload["website"] = data.get("domain")
        if data.get("name"):
            payload["name"] = data.get("name")

        if not payload:
            return True

        pipedrive_success = False
        resp = await self._request("PUT", f"organizations/{org_id}", json=payload)
        if resp is not None:
            pipedrive_success = resp.status_code == 200
            log.info(
                "pipedrive.org.updated",
                org_id=org_id,
                status=resp.status_code,
            )

        # Atualiza banco local
        try:
            async with async_session() as session:
                stmt = select(Organization).where(Organization.pipedrive_id == org_id)
                res = await session.execute(stmt)
                org = res.scalars().first()
                if org:
                    if data.get("cnpj"):
                        org.cnpj = (
                            data["cnpj"].replace(".", "").replace("/", "").replace("-", "")
                        )
                    if data.get("domain"):
                        org.domain = data.get("domain")
                    if data.get("address"):
                        org.address = data.get("address")
                    if data.get("linkedin_url"):
                        org.linkedin_url = data.get("linkedin_url")
                    if data.get("logo_url"):
                        org.logo_url = data.get("logo_url")
                    if data.get("name"):
                        org.name = data.get("name")
                    await session.commit()
                    log.info("pipedrive.org.local_updated", org_id=org_id)
        except Exception as e:
            log.warning("pipedrive.org.local_update_failed", error=str(e))

        return pipedrive_success

    async def update_person(self, person_id: int, data: dict) -> bool:
        from core.database import async_session
        from models import Employee
        from sqlalchemy import select

        payload: Dict[str, Any] = {}
        if data.get("phone"):
            payload["phone"] = [{"value": data["phone"], "primary": True}]
        if data.get("email"):
            payload["email"] = [{"value": data["email"], "primary": True}]
        if data.get("name"):
            payload["name"] = data["name"]

        pipedrive_success = False
        if payload:
            resp = await self._request("PUT", f"persons/{person_id}", json=payload)
            if resp is not None:
                pipedrive_success = resp.status_code == 200

        try:
            async with async_session() as session:
                stmt = select(Employee).where(Employee.pipedrive_id == str(person_id))
                res = await session.execute(stmt)
                emp = res.scalars().first()
                if emp:
                    if data.get("phone"):
                        emp.phone = data["phone"]
                    if data.get("email"):
                        emp.email = data["email"]
                    if data.get("name"):
                        emp.name = data["name"]
                    await session.commit()
        except Exception as e:
            log.warning("pipedrive.person.local_update_failed", error=str(e))

        return pipedrive_success

    # ---------------------------------------------------------------------
    # Listing / Sync
    # ---------------------------------------------------------------------

    async def list_organizations(self) -> List[dict]:
        """Lista empresas priorizando o banco local; sincroniza com Pipedrive se vazio."""
        from core.database import async_session
        from models import Employee, Organization
        from sqlalchemy import func, select

        async with async_session() as session:
            stmt = (
                select(Organization)
                .where(Organization.is_excluded != 1)
                .order_by(Organization.last_enrichment.desc())
            )
            res = await session.execute(stmt)
            local_orgs = res.scalars().all()

        if not local_orgs:
            resp = await self._request(
                "GET",
                "organizations",
                params={"user_id": self.user_id, "start": 0, "limit": 500},
            )
            if resp is not None and resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get("success"):
                        all_orgs = data.get("data") or []
                        async with async_session() as session:
                            for org in all_orgs:
                                pid = org.get("id")
                                name = (org.get("name") or "").strip()

                                open_deals = org.get("open_deals_count", 0)
                                if open_deals == 0:
                                    continue
                                if not name or len(name) < 2:
                                    continue

                                stmt = select(Organization).where(
                                    (Organization.pipedrive_id == pid)
                                    | (func.lower(Organization.name) == name.lower())
                                )
                                res = await session.execute(stmt)
                                db_org = res.scalars().first()

                                if db_org and db_org.is_excluded == 1:
                                    continue

                                if not db_org:
                                    db_org = Organization(pipedrive_id=pid, name=name)
                                    session.add(db_org)
                                    log.info("pipedrive.sync.new_org", name=name)
                                else:
                                    db_org.pipedrive_id = pid
                                    if not db_org.name:
                                        db_org.name = name

                                p_domain = org.get("website")
                                if p_domain and len(str(p_domain)) > 3:
                                    db_org.domain = p_domain

                                p_address = org.get("address")
                                if p_address and len(str(p_address)) > 3:
                                    db_org.address = p_address

                            await session.commit()
                        async with async_session() as session:
                            stmt = select(Organization).order_by(
                                Organization.last_enrichment.desc()
                            )
                            res = await session.execute(stmt)
                            local_orgs = res.scalars().all()
                except Exception as e:
                    log.warning("pipedrive.sync_failed", error=str(e))

        result: List[dict] = []
        async with async_session() as session:
            for o in local_orgs:
                count_stmt = select(func.count(Employee.id)).where(
                    (Employee.company_id == o.id)
                    & (Employee.department != "Quadro Societário")
                )
                count_res = await session.execute(count_stmt)
                emp_count = count_res.scalar() or 0

                pics_stmt = (
                    select(Employee.profile_pic)
                    .where(
                        (Employee.company_id == o.id)
                        & (Employee.department != "Quadro Societário")
                        & (Employee.profile_pic.is_not(None))
                        & (Employee.profile_pic != "")
                    )
                    .limit(3)
                )
                pics_res = await session.execute(pics_stmt)
                pics = [p for p in pics_res.scalars().all()]

                result.append(
                    {
                        "id": o.pipedrive_id or o.id,
                        "name": o.name,
                        "domain": o.domain,
                        "cnpj": o.cnpj,
                        "address": o.address,
                        "local_id": o.id,
                        "logo": o.logo_url,
                        "linkedin": o.linkedin_url,
                        "category": o.category,
                        "product_focus": o.product_focus,
                        "employee_count": emp_count,
                        "employee_pics": pics,
                    }
                )

        return result

    # ---------------------------------------------------------------------
    # Activities
    # ---------------------------------------------------------------------

    async def sync_overdue_activities(self) -> Dict[str, Any]:
        today = date.today().isoformat()
        resp = await self._request(
            "GET",
            "activities",
            params={"user_id": self.user_id, "done": 0},
        )
        if resp is None or resp.status_code != 200:
            return {"status": "error", "message": "Sem tarefas."}
        try:
            data = resp.json()
            if not data.get("success"):
                return {"status": "error", "message": "Sem tarefas."}
            activities = data.get("data") or []
            updated = 0
            for act in activities:
                due = act.get("due_date")
                if due and due < today:
                    r = await self._request(
                        "PUT",
                        f"activities/{act.get('id')}",
                        json={"due_date": today},
                    )
                    if r is not None and r.status_code == 200:
                        updated += 1
            return {"status": "success", "message": f"{updated} atrasos perdoados."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def smart_reschedule_activities(self) -> Dict[str, Any]:
        """Remanejamento Inteligente v2 — mesma lógica, via `_request`."""
        today_date = date.today()
        if today_date.weekday() >= 5:
            today_date += timedelta(days=(7 - today_date.weekday()))
        log.info("pipedrive.smart_reschedule.start", base_date=today_date.isoformat())

        try:
            resp_act = await self._request(
                "GET",
                "activities",
                params={"user_id": self.user_id, "limit": 500},
            )
            if resp_act is None or resp_act.status_code != 200:
                return {"status": "error", "message": "Falha ao buscar atividades."}
            act_data = resp_act.json()
            if not act_data.get("success"):
                return {"status": "error", "message": "Falha ao buscar atividades."}

            resp_deals = await self._request(
                "GET",
                "deals",
                params={"user_id": self.user_id, "limit": 500, "status": "open"},
            )
            deals_data = resp_deals.json() if resp_deals is not None else {"success": False}

            deal_stages: Dict[int, int] = {}
            if deals_data.get("success"):
                for d in deals_data.get("data") or []:
                    deal_stages[d["id"]] = d.get("stage_id")

            activities = act_data.get("data") or []
            deal_open_tasks: Dict[int, list] = defaultdict(list)
            deal_last_done: Dict[int, str] = {}
            all_stages: set[int] = set()

            for act in activities:
                deal_id = act.get("deal_id")
                if not deal_id:
                    continue
                stage_id = deal_stages.get(deal_id, 0)
                all_stages.add(stage_id)
                is_done = act.get("done") == 1
                due_date = act.get("due_date")
                if is_done:
                    if due_date:
                        current_last = deal_last_done.get(deal_id, "1900-01-01")
                        if due_date > current_last:
                            deal_last_done[deal_id] = due_date
                else:
                    act["stage_id"] = stage_id
                    deal_open_tasks[deal_id].append(act)

            sorted_deals = sorted(
                deal_open_tasks.keys(),
                key=lambda did: deal_last_done.get(did, "1900-01-01"),
            )

            stage_queues: Dict[int, list] = defaultdict(list)
            for did in sorted_deals:
                stage_id = deal_stages.get(did, 0)
                stage_queues[stage_id].extend(deal_open_tasks[did])

            scheduled_updates: List[tuple[int, str]] = []
            current_day = today_date
            sorted_stages = sorted(list(all_stages))
            daily_load: Dict[str, int] = defaultdict(int)
            deal_day_map: Dict[tuple, bool] = {}

            has_tasks = True
            while has_tasks:
                has_tasks = False
                for stage_id in sorted_stages:
                    if stage_queues[stage_id]:
                        task = stage_queues[stage_id].pop(0)
                        deal_id = task.get("deal_id")
                        has_tasks = True
                        target_day = current_day
                        found_day = False
                        attempt = 0
                        while not found_day and attempt < 30:
                            d_str = target_day.isoformat()
                            if target_day.weekday() >= 5:
                                target_day += timedelta(days=1)
                                continue
                            if (
                                daily_load[d_str] < 10
                                and (d_str, deal_id) not in deal_day_map
                            ):
                                scheduled_updates.append((task.get("id"), d_str))
                                daily_load[d_str] += 1
                                deal_day_map[(d_str, deal_id)] = True
                                found_day = True
                            else:
                                target_day += timedelta(days=1)
                                attempt += 1

            updated = 0
            for tid, d_str in scheduled_updates:
                r = await self._request(
                    "PUT", f"activities/{tid}", json={"due_date": d_str}
                )
                if r is not None and r.status_code == 200:
                    updated += 1

            final_day = (
                max(u[1] for u in scheduled_updates)
                if scheduled_updates
                else today_date.isoformat()
            )
            log.info("pipedrive.smart_reschedule.done", updated=updated)
            return {
                "status": "success",
                "message": (
                    f"Remanejamento Balanceado: {updated} tarefas priorizadas "
                    "por negócio e distribuídas por etapa. Máximo 1 tarefa por negócio/dia."
                ),
                "stats": {
                    "updated": updated,
                    "start_date": today_date.isoformat(),
                    "end_date": str(final_day),
                },
            }
        except Exception as e:
            log.exception("pipedrive.smart_reschedule.failed")
            return {"status": "error", "message": str(e)}

    # ---------------------------------------------------------------------
    # Delete (agressivo)
    # ---------------------------------------------------------------------

    async def delete_organization(self, org_id: int):
        from core.database import async_session
        from models import Employee, Organization
        from sqlalchemy import delete, or_, select

        target_pid = None
        org_local_id = None

        try:
            async with async_session() as session:
                stmt = select(Organization).where(
                    or_(Organization.pipedrive_id == org_id, Organization.id == org_id)
                )
                res = await session.execute(stmt)
                org = res.scalars().first()
                if org:
                    target_pid = org.pipedrive_id
                    org_local_id = org.id
                    log.info(
                        "pipedrive.delete.org_found",
                        name=org.name,
                        local_id=org.id,
                        pipedrive_id=target_pid,
                    )
                else:
                    target_pid = org_id
                    log.info("pipedrive.delete.org_not_local", assumed_pipedrive_id=org_id)
        except Exception as e:
            log.warning("pipedrive.delete.local_lookup_failed", error=str(e))
            target_pid = org_id

        pipedrive_success = False
        error_code = None

        if target_pid:
            resp = await self._request("DELETE", f"organizations/{target_pid}")
            if resp is not None:
                try:
                    res_data = (
                        {"success": True} if resp.status_code == 204 else resp.json()
                    )
                except Exception:
                    res_data = {"success": False}

                if resp.status_code in (200, 204) and res_data.get("success"):
                    pipedrive_success = True
                    log.info("pipedrive.delete.org_ok", pipedrive_id=target_pid)
                elif (
                    resp.status_code == 403
                    or res_data.get("code") == "ERR_ORGANIZATION_MISSING_PERMISSIONS"
                ):
                    error_code = "ERR_ORGANIZATION_MISSING_PERMISSIONS"
                    log.warning(
                        "pipedrive.delete.permission_denied", pipedrive_id=target_pid
                    )
                    try:
                        deals_resp = await self._request(
                            "GET", f"organizations/{target_pid}/deals",
                            params={"status": "open"},
                        )
                        if deals_resp is not None and deals_resp.status_code == 200:
                            d_data = deals_resp.json()
                            if d_data.get("success") and d_data.get("data"):
                                for deal in d_data["data"]:
                                    deal_id = deal["id"]
                                    del_resp = await self._request(
                                        "DELETE", f"deals/{deal_id}"
                                    )
                                    if (
                                        del_resp is not None
                                        and del_resp.status_code in (200, 204)
                                    ):
                                        log.info(
                                            "pipedrive.delete.deal_ok", deal_id=deal_id
                                        )
                                    else:
                                        await self._request(
                                            "PUT",
                                            f"deals/{deal_id}",
                                            json={
                                                "status": "lost",
                                                "lost_reason": "Removido via Hierarchy Mapper",
                                            },
                                        )
                    except Exception as deal_err:
                        log.warning(
                            "pipedrive.delete.cleanup_deals_failed", error=str(deal_err)
                        )
                else:
                    error_code = res_data.get("code")

        # Blacklist local
        try:
            async with async_session() as session:
                stmt = None
                if target_pid is not None and org_local_id is not None:
                    stmt = select(Organization).where(
                        or_(
                            Organization.pipedrive_id == target_pid,
                            Organization.id == org_local_id,
                        )
                    )
                elif target_pid is not None:
                    stmt = select(Organization).where(
                        Organization.pipedrive_id == target_pid
                    )
                elif org_local_id is not None:
                    stmt = select(Organization).where(Organization.id == org_local_id)

                if stmt is not None:
                    res = await session.execute(stmt)
                    org = res.scalars().first()
                    if org:
                        await session.execute(
                            delete(Employee).where(Employee.company_id == org.id)
                        )
                        org.is_excluded = 1
                        org.cnpj = None
                        org.domain = None
                        await session.commit()
                        log.info("pipedrive.delete.blacklisted", name=org.name)
                    elif target_pid:
                        new_blocked = Organization(
                            pipedrive_id=target_pid,
                            is_excluded=1,
                            name="EXCLUDED_ORG",
                        )
                        session.add(new_blocked)
                        await session.commit()
                        log.info(
                            "pipedrive.delete.blacklist_created", pipedrive_id=target_pid
                        )
        except Exception as e:
            log.warning("pipedrive.delete.blacklist_failed", error=str(e))

        if not pipedrive_success and error_code == "ERR_ORGANIZATION_MISSING_PERMISSIONS":
            return "partial_success_permissions"

        return pipedrive_success

    # ---------------------------------------------------------------------
    # Raio-X
    # ---------------------------------------------------------------------

    async def get_organization_details(
        self, org_id: int, done: Optional[int] = None
    ) -> dict:
        """Busca Raio-X completo — preserva lógica original com fan-out paralelo."""
        deals_resp = await self._request(
            "GET",
            f"organizations/{org_id}/deals",
            params={"user_id": self.user_id},
        )
        deals = (
            deals_resp.json().get("data") or []
            if deals_resp is not None and deals_resp.status_code == 200
            else []
        )

        stages_map = await self.get_all_stages()

        for d in deals:
            d["stage_name"] = stages_map.get(d.get("stage_id"), f"Estágio {d.get('stage_id')}")
            d["formatted_value"] = f"{d.get('currency', 'BRL')} {d.get('value', 0):,.2f}"

        primary_deal = next((d for d in deals if d.get("status") == "open"), None)
        if not primary_deal and deals:
            primary_deal = deals[0]
        primary_deal_id = primary_deal.get("id") if primary_deal else None

        done_values = [0, 1] if done is None else [done]

        # Fan-out paralelo — chamadas independentes
        tasks: list[asyncio.Task] = []
        keys: list[str] = []

        keys.append("persons")
        tasks.append(asyncio.create_task(self._request("GET", f"organizations/{org_id}/persons")))
        keys.append("notes")
        tasks.append(asyncio.create_task(self._request("GET", "notes", params={"org_id": org_id})))
        keys.append("updates")
        tasks.append(asyncio.create_task(self._request("GET", f"organizations/{org_id}/flow")))
        for i, dv in enumerate(done_values):
            keys.append(f"activities_{i}")
            tasks.append(
                asyncio.create_task(
                    self._request(
                        "GET", f"organizations/{org_id}/activities", params={"done": dv}
                    )
                )
            )

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        raw_results: Dict[str, list] = {}
        for key, resp in zip(keys, responses):
            if isinstance(resp, Exception) or resp is None:
                raw_results[key] = []
                continue
            try:
                raw_results[key] = resp.json().get("data") or []
            except Exception:
                raw_results[key] = []

        merged_activities: list[dict] = []
        for i in range(len(done_values)):
            merged_activities.extend(raw_results.get(f"activities_{i}", []))

        results = {
            "persons": raw_results.get("persons", []),
            "notes": raw_results.get("notes", []),
            "updates": raw_results.get("updates", []),
            "activities": merged_activities,
        }

        # Deep discovery de contatos
        found_person_ids: set = set()

        def extract_pid(val):
            if not val:
                return None
            if isinstance(val, dict):
                return val.get("id") or val.get("value")
            return val

        for act in results["activities"]:
            pid = extract_pid(act.get("person_id"))
            if pid:
                found_person_ids.add(pid)
        for deal in deals:
            pid = extract_pid(deal.get("person_id"))
            if pid:
                found_person_ids.add(pid)

        existing_ids = {extract_pid(p.get("id")) for p in results["persons"] if p.get("id")}
        missing_ids = [pid for pid in found_person_ids if pid and pid not in existing_ids]

        if missing_ids:
            log.info("pipedrive.deep_discovery", count=len(missing_ids))
            person_tasks = [self.get_person_details(pid) for pid in list(missing_ids)[:10]]
            persons_found = await asyncio.gather(*person_tasks, return_exceptions=True)
            for p in persons_found:
                if isinstance(p, Exception) or not p:
                    continue
                results["persons"].append(p)

        if primary_deal_id:
            results["activities"] = [
                a for a in results["activities"] if a.get("deal_id") == primary_deal_id
            ]
            results["notes"] = [
                n for n in results["notes"] if n.get("deal_id") == primary_deal_id
            ]

        return {
            "id": org_id,
            "primary_deal_id": primary_deal_id,
            "deals": deals,
            "persons": results["persons"],
            "activities": results["activities"],
            "notes": results["notes"],
            "updates": results["updates"],
        }

    # ---------------------------------------------------------------------
    # Create helpers
    # ---------------------------------------------------------------------

    async def create_activity(self, data: dict) -> dict:
        if not data.get("user_id"):
            data["user_id"] = self.user_id
        resp = await self._request("POST", "activities", json=data)
        if resp is None:
            return {"success": False}
        try:
            res_json = resp.json()
            if not res_json.get("success"):
                log.warning(
                    "pipedrive.activity.create_failed_api",
                    error=res_json.get("error"),
                    error_info=res_json.get("error_info"),
                    payload=data
                )
            return res_json
        except Exception as e:
            log.warning("pipedrive.activity.create_parse_failed", error=str(e))
            return {"success": False}

    async def create_person(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        org_id: int | None = None,
    ) -> dict:
        payload = {
            "name": name,
            "owner_id": self.user_id,
            "org_id": org_id,
            "email": [{"value": email, "primary": True}] if email else None,
            "phone": [{"value": phone, "primary": True}] if phone else None,
        }
        resp = await self._request("POST", "persons", json=payload)
        if resp is None:
            return {"success": False}
        try:
            return resp.json()
        except Exception:
            return {"success": False}

    async def update_deal(self, deal_id: int, data: dict) -> dict:
        resp = await self._request("PUT", f"deals/{deal_id}", json=data)
        if resp is None:
            return {"success": False}
        try:
            return resp.json()
        except Exception:
            return {"success": False}


# Singleton
pipedrive_service = PipedriveService()


__all__ = [
    "PipedriveService",
    "pipedrive_service",
]
