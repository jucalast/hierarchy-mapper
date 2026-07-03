"""
services.crm.pipedrive_service
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
from collections import defaultdict, deque
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

from core.infra.cache import get_cache
from core.config import settings
from core.infra.http_client import get_http_client
from core.observability.logging_config import get_logger
from core.observability.metrics import external_api_requests_total, update_circuit_metric
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
    # Cache TTL de open org IDs — atualizado em background, nunca bloqueia requests
    _open_org_ids_cache: Optional[set] = None
    _open_org_ids_cache_ts: float = 0.0
    _OPEN_ORG_IDS_TTL: float = 300.0  # 5 minutos
    # Mapa org_id -> stage_name para o estágio real do deal aberto mais recente
    _org_stage_cache: Dict[int, str] = {}

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

    async def refresh_open_org_ids_cache(self) -> None:
        """Atualiza o cache de org IDs com negócios abertos em background.

        Chamado pelo SyncIntelligenceHub — nunca pelo request handler.
        """
        age = time.time() - PipedriveService._open_org_ids_cache_ts
        if age < PipedriveService._OPEN_ORG_IDS_TTL:
            return
        try:
            ids: set = set()
            org_stage_map: Dict[int, str] = {}
            start = 0
            limit = 500
            has_more = True

            # Busca mapa de estágios para resolver stage_id -> nome
            stages_full = {}
            try:
                stages_full = await self.get_all_stages_full()
            except Exception:
                pass

            while has_more:
                deals_resp = await self._request("GET", "deals", params={"status": "open", "limit": limit, "start": start})
                if deals_resp is not None and deals_resp.status_code == 200:
                    data = deals_resp.json()
                    deals = data.get("data") or []
                    if not deals:
                        break
                        
                    for d in deals:
                        org_info = d.get("org_id")
                        if org_info:
                            oid = org_info.get("value") if isinstance(org_info, dict) else org_info
                            if oid:
                                oid = int(oid)
                                ids.add(oid)
                                # Mapeia org -> stage (usa o primeiro deal encontrado por org)
                                if oid not in org_stage_map:
                                    sid = d.get("stage_id")
                                    if sid is not None:
                                        stage_info = stages_full.get(sid)
                                        stage_order_nr = 0
                                        if isinstance(stage_info, dict):
                                            stage_name = stage_info.get("name", f"Estágio {sid}")
                                            stage_order_nr = stage_info.get("order_nr", 0)
                                        elif isinstance(stage_info, str):
                                            stage_name = stage_info
                                        else:
                                            stage_name = d.get("stage_order_nr", f"Estágio {sid}")
                                        org_stage_map[oid] = {"name": stage_name, "order_nr": stage_order_nr}
                                
                    pagination = data.get("additional_data", {}).get("pagination", {})
                    has_more = pagination.get("more_items_in_collection", False)
                    if has_more:
                        start = pagination.get("next_start")
                else:
                    status = deals_resp.status_code if deals_resp else 'Timeout'
                    raise Exception(f"Falha ao buscar negócios do Pipedrive: HTTP {status}")
                    
                # Stop gap to avoid infinite loops
                if start > 10000:
                    break

            PipedriveService._open_org_ids_cache = ids
            PipedriveService._org_stage_cache = org_stage_map
            PipedriveService._open_org_ids_cache_ts = time.time()
            log.info("pipedrive.open_org_ids_cache.refreshed", count=len(ids))
        except Exception as e:
            log.warning("pipedrive.open_org_ids_cache.refresh_failed", error=str(e))

    def _update_retry_after(self, resp: httpx.Response) -> None:
        if resp.status_code != 429:
            return
        retry_after = resp.headers.get("retry-after")
        if retry_after:
            try:
                raw = int(retry_after)
                # Pipedrive retorna Retry-After em milissegundos (ex: 59721 ms ≈ 60s).
                # Valores > 3600 são impossíveis em segundos (1h), logo são ms.
                seconds = raw / 1000 if raw > 3600 else raw
                PipedriveService._retry_after_until = time.time() + seconds + 0.5
                log.warning(
                    "pipedrive.rate_limited",
                    retry_after=int(retry_after),
                    cooldown_sec=int(seconds),
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

    async def _ensure_credentials(self) -> None:
        """Carrega dinamicamente as credenciais de integração do banco de dados (SaaS)."""
        try:
            from modules.ai.service.context.business_context_service import BusinessContextService
            t_id = await BusinessContextService.get_first_tenant_id()
            if t_id:
                creds = await BusinessContextService.get_integration_credentials(t_id, "pipedrive")
                if creds:
                    token = creds.get("api_token")
                    uid = creds.get("user_id")
                    if token:
                        self.api_token = token
                    if uid:
                        self.user_id = int(uid)
        except Exception as e:
            log.warning("pipedrive_service.ensure_credentials_failed", error=str(e))

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
        await self._ensure_credentials()
        try:
            self._breaker.ensure_available()
        except CircuitOpenError:
            update_circuit_metric(self._breaker.name, True)
            log.warning("pipedrive.circuit_open")
            raise RuntimeError("Pipedrive temporariamente indisponível (Circuit Breaker aberto)")

        import urllib.parse
        req_params = dict(params) if params else {}
        req_params["api_token"] = self.api_token
        
        raw_url = f"{self.base_url}/{endpoint.lstrip('/')}"
        parsed = urllib.parse.urlparse(raw_url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        query.update(req_params)
        
        new_query = urllib.parse.urlencode(query)
        url = parsed._replace(query=new_query).geturl()

        client = get_http_client()
        t_out = timeout or settings.pipedrive.request_timeout_sec

        async with PipedriveService._semaphore:
            wait = PipedriveService._retry_after_until - time.time()
            if wait > 0:
                # Falha rápido — não bloqueia o event loop nem o frontend.
                # O chamador (sync_hub, etc.) é responsável por retentar depois.
                log.info("pipedrive.cooldown_wait", seconds=int(wait))
                raise RuntimeError(
                    f"Pipedrive em cooldown por rate limit. Tente novamente em {int(wait)}s"
                )

            try:
                resp = await client.request(
                    method, url, json=json, params=None, timeout=t_out
                )
            except Exception as e:
                raise RuntimeError(f"Erro de conexão com Pipedrive: {e}")

            if resp.status_code == 429:
                self._update_retry_after(resp)
                wait = PipedriveService._retry_after_until - time.time()
                # Se for um rate limit de curta duração (<= 3 segundos), tenta aguardar e refazer a chamada
                if 0 < wait <= 3.0:
                    import random
                    jitter = random.uniform(0.1, 0.4)
                    sleep_time = wait + jitter
                    log.info("pipedrive.rate_limit.retry_sleep", seconds=round(sleep_time, 2))
                    await asyncio.sleep(sleep_time)
                    try:
                        resp = await client.request(
                            method, url, json=json, params=params, timeout=t_out
                        )
                        if resp.status_code != 429:
                            PipedriveService._retry_after_until = 0.0
                            if resp.status_code < 500:
                                self._breaker.record_success()
                                update_circuit_metric(self._breaker.name, False)
                            return resp
                    except Exception:
                        pass

                # Se ainda persistir ou for maior que 3 segundos
                wait = PipedriveService._retry_after_until - time.time()
                if wait > 0:
                    raise RuntimeError(
                        f"Pipedrive Rate Limit. Tente novamente em {max(1, int(wait + 0.99))}s"
                    )

            if resp.status_code == 429:
                raise RuntimeError(f"Pipedrive Rate Limit persistente. Tente novamente em {self.get_retry_after_seconds()}s")

            if resp.status_code >= 500:
                self._breaker.record_failure(reason=f"http_{resp.status_code}")
                update_circuit_metric(self._breaker.name, True)
                raise RuntimeError(f"Erro interno no Pipedrive (HTTP {resp.status_code})")

            # Sucesso ou erro de cliente (404, 403 etc)
            if resp.status_code < 500:
                self._breaker.record_success()
                update_circuit_metric(self._breaker.name, False)

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

    _users_cache: Dict[int, str] = {}
    _users_pics_cache: Dict[int, Optional[str]] = {}
    _users_cache_time: float = 0

    async def get_users_map(self) -> Dict[int, str]:
        """Retorna mapeamento {user_id: user_name} com cache de 1 hora."""
        if time.time() - self._users_cache_time < 3600 and self._users_cache:
            return self._users_cache
        
        try:
            resp = await self._request("GET", "users")
            if resp and resp.status_code == 200:
                data = resp.json().get("data") or []
                self._users_cache = {u["id"]: u["name"] for u in data if "id" in u and "name" in u}
                self._users_pics_cache = {u["id"]: u.get("icon_url") for u in data if "id" in u}
                self._users_cache_time = time.time()
                return self._users_cache
        except Exception:
            pass
        return self._users_cache

    async def get_users_pics_map(self) -> Dict[int, Optional[str]]:
        """Retorna mapeamento {user_id: icon_url} com cache de 1 hora."""
        await self.get_users_map()
        return self._users_pics_cache

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
            "owner_id": data.get("owner_id") or self.user_id,
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

    async def create_deal(self, title: str, org_id: Optional[int] = None, stage_name: Optional[str] = "Entrada") -> Optional[int]:
        """Cria um negócio no Pipedrive, vinculado à organização, no estágio pelo nome."""
        stage_id: Optional[int] = None
        if stage_name:
            stages = await self.get_all_stages_full()
            for sid, info in stages.items():
                if info.get("name", "").strip().lower() == stage_name.strip().lower():
                    stage_id = sid
                    break
            if not stage_id:
                log.warning("pipedrive.deal.stage_not_found", stage_name=stage_name)

        payload: dict = {
            "title": title,
            "user_id": self.user_id,
        }
        if org_id:
            payload["org_id"] = org_id
        if stage_id:
            payload["stage_id"] = stage_id

        resp = await self._request("POST", "deals", json=payload)
        if resp is None:
            return None
        try:
            res_data = resp.json()
            if res_data.get("success"):
                deal_id = res_data["data"]["id"]
                log.info("pipedrive.deal.created", deal_id=deal_id, title=title, stage_id=stage_id, org_id=org_id)
                return deal_id
            log.warning(
                "pipedrive.deal.api_error",
                error=res_data.get("error"),
                error_info=res_data.get("error_info"),
                http_status=resp.status_code,
                payload=payload,
            )
        except Exception as e:
            log.warning("pipedrive.deal.create_failed", error=str(e))
        return None

    async def get_person_details(self, person_id: int) -> Optional[dict]:
        resp = await self._request("GET", f"persons/{person_id}")
        if resp is not None and resp.status_code == 200:
            return resp.json().get("data")
        return None

    async def get_activity(self, activity_id: int) -> Optional[dict]:
        """Busca detalhes de uma atividade específica."""
        resp = await self._request("GET", f"activities/{activity_id}")
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

    async def add_participant(self, deal_id: int, person_id: int) -> bool:
        """Adiciona uma pessoa como participante de um negócio."""
        resp = await self._request(
            "POST", 
            f"deals/{deal_id}/participants", 
            json={"person_id": person_id}
        )
        if resp is not None and resp.status_code in (200, 201):
            log.info("pipedrive.participant.added", deal_id=deal_id, person_id=person_id)
            return True
        return False

    async def delete_note(self, note_id: int) -> bool:
        resp = await self._request("DELETE", f"notes/{note_id}")
        if resp is None:
            return False
        try:
            if resp.status_code == 204:
                return True
            res_data = resp.json()
            if res_data.get("success"):
                log.info("pipedrive.note.deleted", note_id=note_id)
                return True
        except Exception as e:
            log.warning("pipedrive.note.delete_failed", error=str(e))
        return False

    async def update_organization(self, org_id: int, data: dict) -> bool:
        """Atualiza Endereço, CNPJ e Domínio no Pipedrive e no Banco Local."""
        from core.infra.database import async_session
        from models import Organization
        from sqlalchemy import select

        payload: Dict[str, Any] = {}
        if "address" in data:
            payload["address"] = data.get("address")
        if "domain" in data:
            payload["website"] = data.get("domain")
        if "name" in data:
            payload["name"] = data.get("name")
        if "owner_id" in data:
            payload["owner_id"] = data.get("owner_id")

        local_keys = [
            "cnpj", "domain", "address", "linkedin_url", "logo_url", "name",
            "description", "category", "product_focus", "temperature", "prospecting_context"
        ]
        has_local_update = any(k in data for k in local_keys)

        if not payload and not has_local_update:
            return True

        pipedrive_success = True
        if payload:
            resp = await self._request("PUT", f"organizations/{org_id}", json=payload)
            if resp is not None:
                pipedrive_success = resp.status_code == 200
                log.info(
                    "pipedrive.org.updated",
                    org_id=org_id,
                    status=resp.status_code,
                )
            else:
                pipedrive_success = False

        # Atualiza banco local
        try:
            async with async_session() as session:
                stmt = select(Organization).where(Organization.pipedrive_id == org_id)
                res = await session.execute(stmt)
                org = res.scalars().first()
                if org:
                    if "cnpj" in data:
                        val = data["cnpj"]
                        org.cnpj = (
                            val.replace(".", "").replace("/", "").replace("-", "").strip()
                            if val else None
                        )
                    if "domain" in data:
                        org.domain = data.get("domain") or None
                    if "address" in data:
                        org.address = data.get("address") or None
                    if "linkedin_url" in data:
                        org.linkedin_url = data.get("linkedin_url") or None
                    if "logo_url" in data:
                        org.logo_url = data.get("logo_url") or None
                    if "name" in data:
                        org.name = data.get("name")
                    if "description" in data:
                        org.description = data.get("description") or None
                    if "category" in data:
                        org.category = data.get("category") or None
                    if "product_focus" in data:
                        org.product_focus = data.get("product_focus") or None
                    if "temperature" in data:
                        org.temperature = data.get("temperature") or None
                    if "prospecting_context" in data:
                        org.prospecting_context = data.get("prospecting_context") or None
                    await session.commit()
                    log.info("pipedrive.org.local_updated", org_id=org_id)
        except Exception as e:
            log.warning("pipedrive.org.local_update_failed", error=str(e))

        return pipedrive_success

    async def update_person(self, person_id: int, data: dict) -> bool:
        from core.infra.database import async_session
        from models import Employee
        from sqlalchemy import select

        payload: Dict[str, Any] = {}
        if data.get("phone"):
            payload["phone"] = data["phone"] if isinstance(data["phone"], list) else [{"value": data["phone"], "primary": True}]
        if data.get("email"):
            payload["email"] = data["email"] if isinstance(data["email"], list) else [{"value": data["email"], "primary": True}]
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

    async def delete_person(self, person_id: int) -> bool:
        resp = await self._request("DELETE", f"persons/{person_id}")
        if resp is not None and resp.status_code == 403:
            raise RuntimeError("Você não tem permissão no Pipedrive para excluir contatos. Entre em contato com o administrador do CRM.")
            
        pipedrive_success = resp is not None and resp.status_code in [200, 201, 204, 404]
        if not pipedrive_success:
            return False
            
        from core.infra.database import async_session
        from models import Employee
        from sqlalchemy import select
        try:
            async with async_session() as session:
                stmt = select(Employee).where(Employee.pipedrive_id == str(person_id))
                res = await session.execute(stmt)
                emp = res.scalars().first()
                if emp:
                    emp.pipedrive_id = None
                    await session.commit()
        except Exception as e:
            log.warning("pipedrive.person.local_delete_failed", error=str(e))
            
        return pipedrive_success

    # ---------------------------------------------------------------------
    # Listing / Sync
    # ---------------------------------------------------------------------

    async def sync_all_parallel(self) -> Dict[str, Any]:
        """
        Sincronização massiva de organizações do Pipedrive para o banco local.
        Paginado e resiliente.
        """
        from core.infra.database import async_session
        from models import Organization
        from sqlalchemy import select, func
        
        log.info("pipedrive.sync_all.start")
        start_time = time.time()
        
        try:
            total_synced = 0
            start = 0
            limit = 100
            has_more = True
            
            while has_more:
                resp = await self._request(
                    "GET",
                    "organizations",
                    params={"user_id": self.user_id, "start": start, "limit": limit, "sort": "id DESC"},
                )
                
                if resp is None or resp.status_code != 200:
                    log.error("pipedrive.sync_all.failed_page", start=start)
                    break
                    
                data = resp.json()
                if not data.get("success"):
                    break
                    
                all_orgs = data.get("data") or []
                if not all_orgs:
                    break
                
                async with async_session() as session:
                    for org in all_orgs:
                        pid = org.get("id")
                        name = (org.get("name") or "").strip()
                        if not name or not pid: continue

                        # Busca por Pipedrive ID
                        stmt = select(Organization).where(Organization.pipedrive_id == pid)
                        res = await session.execute(stmt)
                        db_org = res.scalars().first()

                        if db_org and db_org.is_excluded == 1:
                            continue

                        if not db_org:
                            # Tenta por nome para evitar duplicatas manuais
                            stmt_name = select(Organization).where(func.lower(Organization.name) == name.lower())
                            res_name = await session.execute(stmt_name)
                            db_org = res_name.scalars().first()
                            
                            if not db_org:
                                db_org = Organization(pipedrive_id=pid, name=name)
                                session.add(db_org)
                                total_synced += 1
                            else:
                                db_org.pipedrive_id = pid
                        
                        # Atualiza campos se estiverem vazios
                        if not db_org.domain:
                            p_domain = org.get("website")
                            if p_domain and len(str(p_domain)) > 3:
                                db_org.domain = p_domain

                        if not db_org.address:
                            p_address = org.get("address")
                            if p_address:
                                if isinstance(p_address, dict):
                                    db_org.address = p_address.get("label") or p_address.get("formatted_address")
                                elif len(str(p_address)) > 3:
                                    db_org.address = str(p_address)
                    
                    await session.commit()
                
                # Controle de paginação
                pagination = data.get("additional_data", {}).get("pagination", {})
                has_more = pagination.get("more_items_in_collection", False)
                if has_more:
                    start = pagination.get("next_start")
                
                # Stop gap para não entrar em loop infinito
                if start > 5000: break 

            duration = time.time() - start_time
            log.info("pipedrive.sync_all.done", total=total_synced, duration_sec=round(duration, 2))
            return {"status": "success", "synced": total_synced}
            
        except Exception as e:
            log.error("pipedrive.sync_all.error", error=str(e))
            return {"status": "error", "message": str(e)}

    async def list_organizations(self) -> List[dict]:
        """Lista empresas do banco local com estatísticas otimizadas.

        Lê apenas do banco local para resposta imediata. A sincronização com
        o Pipedrive é feita em background pelo SyncIntelligenceHub. Os open
        org IDs são mantidos em cache TTL e atualizados via
        refresh_open_org_ids_cache() sem bloquear o request.
        """
        from core.infra.database import async_session
        from models import Employee, Organization
        from sqlalchemy import func, select, and_, or_

        # Aguarda até 5 segundos se o cache não estiver pronto (startup warm-up)
        # Evita drawer vazio se o frontend for mais rápido que o primeiro request ao Pipedrive
        attempts = 0
        while PipedriveService._open_org_ids_cache is None and attempts < 10:
            await asyncio.sleep(0.5)
            attempts += 1

        # Usa o cache de open org IDs (filtro obrigatório para mostrar apenas ativos)
        open_org_ids = PipedriveService._open_org_ids_cache
        
        # Se o cache ainda não carregou (SyncHub ainda não rodou), dispara refresh inline
        # para não deixar o drawer vazio no primeiro acesso após reinício do backend.
        if open_org_ids is None:
            log.info("pipedrive.list_orgs.cache_not_ready_forcing_refresh")
            try:
                await self.refresh_open_org_ids_cache()
                open_org_ids = PipedriveService._open_org_ids_cache
            except Exception as e:
                log.warning("pipedrive.list_orgs.inline_refresh_failed", error=str(e))
        
        # 2. Busca as organizações locais ativas
        async with async_session() as session:
            if open_org_ids is not None:
                stmt = (
                    select(Organization)
                    .where(
                        and_(
                            Organization.is_excluded != 1,
                            Organization.pipedrive_id.in_(list(open_org_ids))
                        )
                    )
                    .order_by(Organization.last_enrichment.desc())
                )
            else:
                log.warning("pipedrive.list_orgs.cache_unavailable_fallback_to_all")
                stmt = (
                    select(Organization)
                    .where(Organization.is_excluded != 1)
                    .order_by(Organization.last_enrichment.desc())
                )
            
            res = await session.execute(stmt)
            local_orgs = res.scalars().all()

            if not local_orgs:
                return []

            # 3. OTIMIZAÇÃO: Busca contagens de funcionários em lote (Group By)
            org_ids = [o.id for o in local_orgs]
            count_stmt = (
                select(Employee.company_id, func.count(Employee.id))
                .where(
                    and_(
                        Employee.company_id.in_(org_ids),
                        Employee.department != "Quadro Societário"
                    )
                )
                .group_by(Employee.company_id)
            )
            count_res = await session.execute(count_stmt)
            counts_map = {row[0]: row[1] for row in count_res.all()}

            # 4. OTIMIZAÇÃO: Busca fotos de funcionários em lote (Heurística: pega alguns de cada)
            # Inclui profile_pic salvo OU linkedin_url para gerar avatar via unavatar.io
            pics_stmt = (
                select(Employee.company_id, Employee.profile_pic, Employee.linkedin_url)
                .where(
                    and_(
                        Employee.company_id.in_(org_ids),
                        or_(
                            and_(Employee.profile_pic.is_not(None), Employee.profile_pic != ""),
                            Employee.linkedin_url.is_not(None),
                        )
                    )
                )
            )
            pics_res = await session.execute(pics_stmt)
            pics_raw = pics_res.all()

            def _linkedin_to_unavatar(url: str) -> str | None:
                """Extrai username do LinkedIn e retorna URL do unavatar.io."""
                import re
                if not url:
                    return None
                m = re.search(r'linkedin\.com/in/([^/\?#]+)', url)
                if m:
                    username = m.group(1).strip('/')
                    if username:
                        return f"https://unavatar.io/linkedin/{username}"
                return None

            pics_map: dict = defaultdict(list)
            for cid, profile_pic, linkedin_url in pics_raw:
                if len(pics_map[cid]) >= 3:
                    continue
                pic = profile_pic or _linkedin_to_unavatar(linkedin_url)
                if pic:
                    pics_map[cid].append(pic)

            # 5. Monta o resultado final
            result = []
            users_map = await self.get_users_map()
            users_pics_map = await self.get_users_pics_map()
            for o in local_orgs:
                pid = o.pipedrive_id or o.id
                stage_data = PipedriveService._org_stage_cache.get(pid) if pid else None
                stage_name = stage_data.get("name") if isinstance(stage_data, dict) else stage_data
                stage_order_nr = stage_data.get("order_nr", 0) if isinstance(stage_data, dict) else 0
                result.append({
                    "id": pid,
                    "name": o.name,
                    "domain": o.domain,
                    "cnpj": o.cnpj,
                    "address": o.address,
                    "local_id": o.id,
                    "logo": o.logo_url,
                    "linkedin": o.linkedin_url,
                    "category": o.category,
                    "product_focus": o.product_focus,
                    "employee_count": counts_map.get(o.id, 0),
                    "employee_pics": pics_map.get(o.id, []),
                    "source": o.source,
                    "icp_score": o.icp_score,
                    "icp_tier": o.icp_tier,
                    "owner_id": o.owner_id,
                    "owner_name": users_map.get(o.owner_id) if o.owner_id in users_map else "Sistema",
                    "owner_avatar": users_pics_map.get(o.owner_id) if o.owner_id in users_pics_map else None,
                    "stage_name": stage_name,
                    "stage_order_nr": stage_order_nr,
                })

            return result


    # ---------------------------------------------------------------------
    # Activities
    # ---------------------------------------------------------------------

    async def sync_overdue_activities(self) -> Dict[str, Any]:
        from datetime import datetime, timezone, timedelta
        sao_paulo_tz = timezone(timedelta(hours=-3))
        today = datetime.now(sao_paulo_tz).date().isoformat()
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
            async def _update_overdue_task(act_id: int) -> bool:
                try:
                    r = await self._request(
                        "PUT",
                        f"activities/{act_id}",
                        json={"due_date": today},
                    )
                    return r is not None and r.status_code == 200
                except Exception as e:
                    log.warning("pipedrive.sync_overdue.task_failed", task_id=act_id, error=str(e))
                    return False

            tasks_to_update = [
                act.get("id")
                for act in activities
                if act.get("deal_id") and act.get("due_date") and act.get("due_date") < today
            ]

            results = await asyncio.gather(*[_update_overdue_task(tid) for tid in tasks_to_update])
            updated = sum(1 for res in results if res)
            return {"status": "success", "message": f"{updated} atrasos perdoados."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def smart_reschedule_activities(self) -> Dict[str, Any]:
        """Remanejamento Inteligente v3 — Espaçamento de 7 dias e prioridade +1sem."""
        from datetime import datetime, timezone, timedelta
        sao_paulo_tz = timezone(timedelta(hours=-3))
        today_date = datetime.now(sao_paulo_tz).date()
        if today_date.weekday() >= 5:
            today_date += timedelta(days=(7 - today_date.weekday()))
        log.info("pipedrive.smart_reschedule.start", base_date=today_date.isoformat())

        try:
            # Busca paginada de atividades PENDENTES — apenas do usuário João Luccas, apenas deals abertos
            activities: list = []
            _start = 0
            while True:
                resp_act = await self._request(
                    "GET",
                    "activities",
                    params={"user_id": self.user_id, "limit": 500, "done": 0, "start": _start},
                )
                if resp_act is None or resp_act.status_code != 200:
                    return {"status": "error", "message": "Falha ao buscar atividades pendentes."}
                act_data = resp_act.json()
                if not act_data.get("success"):
                    return {"status": "error", "message": "Falha ao buscar atividades pendentes."}
                activities.extend(act_data.get("data") or [])
                pag = (act_data.get("additional_data") or {}).get("pagination") or {}
                if not pag.get("more_items_in_collection"):
                    break
                _start = pag.get("next_start", _start + 500)
                if _start > 10000:
                    break

            # Busca paginada de atividades CONCLUÍDAS — histórico de último contato por deal
            deal_last_done: Dict[int, str] = {}
            _start = 0
            while True:
                resp_done_act = await self._request(
                    "GET",
                    "activities",
                    params={"user_id": self.user_id, "limit": 500, "done": 1, "start": _start},
                )
                if not resp_done_act or resp_done_act.status_code != 200:
                    break
                done_data = resp_done_act.json()
                if not done_data.get("success"):
                    break
                for act in done_data.get("data") or []:
                    deal_id = act.get("deal_id")
                    if not deal_id:
                        continue
                    due_date = act.get("due_date")
                    if due_date:
                        current_last = deal_last_done.get(deal_id, "1900-01-01")
                        if due_date > current_last:
                            deal_last_done[deal_id] = due_date
                pag = (done_data.get("additional_data") or {}).get("pagination") or {}
                if not pag.get("more_items_in_collection"):
                    break
                _start = pag.get("next_start", _start + 500)
                if _start > 10000:
                    break

            # Busca paginada de deals ABERTOS — apenas do usuário João Luccas
            deal_stages: Dict[int, int] = {}
            deal_expected_close: Dict[int, str] = {}
            _start = 0
            while True:
                resp_deals = await self._request(
                    "GET",
                    "deals",
                    params={"user_id": self.user_id, "status": "open", "limit": 500, "start": _start},
                )
                if resp_deals is None or resp_deals.status_code != 200:
                    break
                deals_data = resp_deals.json()
                if not deals_data.get("success"):
                    break
                for d in deals_data.get("data") or []:
                    deal_stages[d["id"]] = d.get("stage_id")
                    deal_expected_close[d["id"]] = d.get("expected_close_date")
                pag = (deals_data.get("additional_data") or {}).get("pagination") or {}
                if not pag.get("more_items_in_collection"):
                    break
                _start = pag.get("next_start", _start + 500)
                if _start > 10000:
                    break

            log.info(
                "pipedrive.smart_reschedule.scope",
                user_id=self.user_id,
                open_deals=len(deal_stages),
                pending_activities=len(activities),
            )

            deal_open_tasks: Dict[int, list] = defaultdict(list)
            all_stages: set[int] = set()

            for act in activities:
                deal_id = act.get("deal_id")
                if not deal_id:
                    continue
                
                # 🚀 FILTRO CRÍTICO: Só processa atividades de negócios que estão ABERTOS
                # Se o deal_id não está no mapa deal_stages, significa que ele não é um deal "open"
                stage_id = deal_stages.get(deal_id)
                if stage_id is None:
                    continue

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

            # Ordenação por prioridade global (negócios sem atividades ou mais antigos primeiro)
            sorted_deals = sorted(
                deal_open_tasks.keys(),
                key=lambda did: deal_last_done.get(did, "1900-01-01"),
            )

            # --- Distribuição proporcional por stage ---
            # Agrupa tasks por stage mantendo ordem de prioridade (mais antigos primeiro)
            DAILY_LIMIT = 10
            stage_task_list: Dict[int, list] = defaultdict(list)
            for did in sorted_deals:
                for task in deal_open_tasks[did]:
                    stage_task_list[task.get("stage_id")].append(task)

            # Calcula a quota diária de cada stage proporcional ao seu total de tasks
            total_tasks_count = sum(len(v) for v in stage_task_list.values())
            stage_daily_quota: Dict[int, int] = {}
            if total_tasks_count > 0:
                stages_sorted_by_size = sorted(
                    stage_task_list.keys(), key=lambda s: -len(stage_task_list[s])
                )
                allocated = 0
                for i, sid in enumerate(stages_sorted_by_size):
                    if i == len(stages_sorted_by_size) - 1:
                        stage_daily_quota[sid] = max(1, DAILY_LIMIT - allocated)
                    else:
                        weight = len(stage_task_list[sid]) / total_tasks_count
                        q = max(1, round(weight * DAILY_LIMIT))
                        stage_daily_quota[sid] = q
                        allocated += q

            # Intercala as filas em round-robin ponderado (pela quota) para manter
            # proporção por stage dentro de cada bloco de DAILY_LIMIT tarefas
            stage_deques: Dict[int, deque] = {
                sid: deque(tasks) for sid, tasks in stage_task_list.items()
            }
            global_queue: list = []
            stages_order = sorted(stage_deques.keys(), key=lambda s: -len(stage_task_list[s]))
            while any(stage_deques.values()):
                for sid in stages_order:
                    q = stage_deques[sid]
                    for _ in range(stage_daily_quota.get(sid, 1)):
                        if q:
                            global_queue.append(q.popleft())

            scheduled_updates: List[tuple[int, str]] = []
            scheduled_deal_updates: Dict[int, str] = {}
            daily_load: Dict[str, int] = defaultdict(int)
            daily_stage_load: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
            deal_day_map: Dict[tuple, bool] = {}

            for task in global_queue:
                deal_id = task.get("deal_id")
                stage_id = task.get("stage_id")

                # Calcula a data mínima permitida baseada na última tarefa realizada
                last_done = deal_last_done.get(deal_id)
                if last_done:
                    try:
                        last_dt = datetime.strptime(last_done, "%Y-%m-%d").date()
                        if last_dt >= today_date:
                            min_allowed = last_dt + timedelta(days=7)
                        else:
                            min_allowed = today_date
                    except Exception:
                        min_allowed = today_date
                else:
                    min_allowed = today_date

                target_day = min_allowed
                found_day = False
                attempt = 0
                while not found_day and attempt < 365:
                    d_str = target_day.isoformat()
                    if target_day.weekday() >= 5:
                        target_day += timedelta(days=1)
                        continue

                    stage_quota = stage_daily_quota.get(stage_id, 1)
                    # Aceita se: total do dia < limite, stage ainda tem cota e deal não tem outra task no mesmo dia
                    if (
                        daily_load[d_str] < DAILY_LIMIT
                        and daily_stage_load[d_str][stage_id] < stage_quota
                        and (d_str, deal_id) not in deal_day_map
                    ):
                        if task.get("due_date") != d_str:
                            scheduled_updates.append((task.get("id"), d_str))

                        daily_load[d_str] += 1
                        daily_stage_load[d_str][stage_id] += 1
                        deal_day_map[(d_str, deal_id)] = True
                        deal_last_done[deal_id] = d_str

                        current_close = deal_expected_close.get(deal_id)
                        if not current_close or current_close < d_str:
                            if current_close != d_str:
                                scheduled_deal_updates[deal_id] = d_str
                            deal_expected_close[deal_id] = d_str

                        found_day = True
                    else:
                        target_day += timedelta(days=1)
                        attempt += 1

            # Para evitar Timeout no frontend (Next.js) e Rate Limits absurdos no Pipedrive,
            # vamos limitar o número máximo de atualizações por vez a 30 (lotes menores e muito rápidos).
            # O usuário pode clicar no botão novamente se houver mais atrasados.
            MAX_UPDATES = 30
            scheduled_updates = scheduled_updates[:MAX_UPDATES]
            
            # Execução Sequencial para Background
            # Como está rodando de madrugada/invisível, não temos pressa. Executar sequencialmente
            # impede o erro de "Too Many Requests" (429) do Pipedrive que derruba o serviço.
            updated = 0
            for tid, d_str in scheduled_updates:
                try:
                    r = await self._request("PUT", f"activities/{tid}", json={"due_date": d_str})
                    if r is not None and r.status_code == 200:
                        updated += 1
                except Exception as e:
                    log.warning("pipedrive.smart_reschedule.task_failed", task_id=tid, error=str(e))
                    await asyncio.sleep(2) # Dorme em caso de erro

            deal_updates_list = list(scheduled_deal_updates.items())[:MAX_UPDATES]
            
            updated_deals = 0
            for did, d_str in deal_updates_list:
                try:
                    r = await self._request("PUT", f"deals/{did}", json={"expected_close_date": d_str})
                    if r is not None and r.status_code == 200:
                        updated_deals += 1
                except Exception as e:
                    log.warning("pipedrive.smart_reschedule.deal_failed", deal_id=did, error=str(e))
                    await asyncio.sleep(2)

            final_day = (
                max(u[1] for u in scheduled_updates)
                if scheduled_updates
                else today_date.isoformat()
            )
            log.info("pipedrive.smart_reschedule.done", updated=updated, updated_deals=updated_deals)
            return {
                "status": "success",
                "message": (
                    f"Remanejamento Balanceado: {updated} tarefas priorizadas "
                    "por negócio e distribuídas por etapa. Máximo 1 tarefa por negócio/dia."
                ),
                "stats": {
                    "updated": updated,
                    "updated_deals": updated_deals,
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
        from core.infra.database import async_session
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
            params={},
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
        keys.append("org")
        tasks.append(asyncio.create_task(self._request("GET", f"organizations/{org_id}")))
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

        # --- Enriquecimento de Nomes de Usuários (Evita Delay de Denormalização do Pipedrive) ---
        users_map = await self.get_users_map()
        persons_list = raw_results.get("persons", [])
        persons_map = {p["id"]: p.get("name") for p in persons_list if "id" in p}
        
        for act in merged_activities:
            # Pipedrive às vezes retorna user_id como objeto ou int
            uid = act.get("user_id")
            if isinstance(uid, dict):
                act["owner_name"] = uid.get("name") or act.get("owner_name")
            elif isinstance(uid, int) and uid in users_map:
                act["owner_name"] = users_map[uid]
            
            # Resolve nome da pessoa (contato)
            pid = act.get("person_id")
            if isinstance(pid, dict):
                act["person_name"] = pid.get("name") or act.get("person_name")
            elif isinstance(pid, int) and pid in persons_map:
                act["person_name"] = persons_map[pid]

        for deal in deals:
            uid = deal.get("user_id")
            if isinstance(uid, dict):
                deal["owner_name"] = uid.get("name") or deal.get("owner_name")
            elif isinstance(uid, int) and uid in users_map:
                deal["owner_name"] = users_map[uid]
            
            pid = deal.get("person_id")
            if isinstance(pid, dict):
                deal["person_name"] = pid.get("name") or deal.get("person_name")
            elif isinstance(pid, int) and pid in persons_map:
                deal["person_name"] = persons_map[pid]

        for note in raw_results.get("notes", []):
            uid = note.get("user_id")
            if isinstance(uid, dict):
                note["owner_name"] = uid.get("name")
            elif isinstance(uid, int) and uid in users_map:
                note["owner_name"] = users_map[uid]

        org_data = raw_results.get("org", {})
        if isinstance(org_data, dict):
            # Resolve nome do dono da organização
            oid = org_data.get("owner_id")
            users_pics_map = await self.get_users_pics_map()
            if isinstance(oid, dict):
                org_data["owner_name"] = oid.get("name")
                org_data["owner_avatar"] = oid.get("icon_url")
                if not org_data.get("owner_avatar") and isinstance(oid.get("id"), int):
                    org_data["owner_avatar"] = users_pics_map.get(oid["id"])
            elif isinstance(oid, int):
                if oid in users_map:
                    org_data["owner_name"] = users_map[oid]
                org_data["owner_avatar"] = users_pics_map.get(oid)

        results = {
            "org": org_data,
            "persons": raw_results.get("persons", []),
            "notes": raw_results.get("notes", []),
            "updates": raw_results.get("updates", []),
            "activities": merged_activities,
            "deals": deals,
        }

        # --- Persistência de Pessoas no Banco Local (Hierarquia) ---
        try:
            from core.infra.database import async_session
            from models import Employee, Organization
            from sqlalchemy import select

            async with async_session() as session:
                # 1. Resolve o ID local da organização
                stmt_org = select(Organization).where(Organization.pipedrive_id == org_id)
                res_org = await session.execute(stmt_org)
                local_org = res_org.scalars().first()

                if local_org:
                    # Enriquece org_data com campos do banco local não presentes no Pipedrive
                    if isinstance(results["org"], dict):
                        # Telefone: busca do banco ou da API do Google Maps (cache permanente)
                        phone = local_org.maps_phone
                        if not phone:
                            from modules.intelligence.service.company_phone_service import fetch_and_cache_company_phone
                            phone = await fetch_and_cache_company_phone(local_org.id, session)
                        if phone:
                            results["org"]["maps_phone"] = phone
                        if local_org.domain and not results["org"].get("domain"):
                            results["org"]["domain"] = local_org.domain

                    for p in results["persons"]:
                        pid = str(p.get("id"))
                        name = p.get("name")
                        if not pid or not name: continue

                         # 2. Busca/Cria funcionário
                        # Primeiro, tenta buscar por pipedrive_id
                        stmt_emp = select(Employee).where(Employee.pipedrive_id == pid)
                        res_emp = await session.execute(stmt_emp)
                        db_emp = res_emp.scalars().first()

                        import unicodedata
                        def normalize_name(s: str) -> str:
                            return "".join(
                                c for c in unicodedata.normalize('NFD', s.lower())
                                if unicodedata.category(c) != 'Mn'
                            ).replace(" ", "").replace("-", "").strip()

                        # Busca se há um duplicado local com o mesmo nome e sem pipedrive_id
                        stmt_dup = select(Employee).where(
                            Employee.company_id == local_org.id,
                            Employee.pipedrive_id.is_(None)
                        )
                        res_dup = await session.execute(stmt_dup)
                        all_dups = res_dup.scalars().all()
                        
                        normalized_name = normalize_name(name)
                        dup_emp = next((e for e in all_dups if normalize_name(e.name) == normalized_name), None)

                        if dup_emp:
                            # Temos um contato local sem pipedrive_id. Queremos preservar o ID desse contato local!
                            # Vincula o pipedrive_id
                            dup_emp.pipedrive_id = pid
                            if dup_emp.source == "discovery":
                                dup_emp.source = "pipedrive + local"
                            
                            if db_emp and db_emp.id != dup_emp.id:
                                # Se já existia um registro separado com o pipedrive_id, mescla as informações do db_emp para o dup_emp
                                if not dup_emp.role and db_emp.role:
                                    dup_emp.role = db_emp.role
                                if not dup_emp.department and db_emp.department:
                                    dup_emp.department = db_emp.department
                                if not dup_emp.seniority and db_emp.seniority:
                                    dup_emp.seniority = db_emp.seniority
                                if not dup_emp.linkedin_url and db_emp.linkedin_url:
                                    dup_emp.linkedin_url = db_emp.linkedin_url
                                if not dup_emp.description and db_emp.description:
                                    dup_emp.description = db_emp.description
                                if not dup_emp.profile_pic and db_emp.profile_pic:
                                    dup_emp.profile_pic = db_emp.profile_pic
                                if not dup_emp.email and db_emp.email:
                                    dup_emp.email = db_emp.email
                                if not dup_emp.phone and db_emp.phone:
                                    dup_emp.phone = db_emp.phone
                                if not dup_emp.location and db_emp.location:
                                    dup_emp.location = db_emp.location
                                if not dup_emp.whatsapp_number and db_emp.whatsapp_number:
                                    dup_emp.whatsapp_number = db_emp.whatsapp_number
                                
                                # Limpa campos únicos do db_emp para evitar conflito de UNIQUE antes do delete/flush
                                db_emp.pipedrive_id = None
                                db_emp.linkedin_url = None
                                db_emp.email = None
                                db_emp.whatsapp_number = None
                                
                                await session.delete(db_emp)
                                log.info("pipedrive.persons.merged_and_deleted_synced_duplicate", name=name, keep_id=dup_emp.id, deleted_id=db_emp.id)
                            else:
                                log.info("pipedrive.persons.linked_pipedrive_id_to_local", name=name, employee_id=dup_emp.id, pipedrive_id=pid)
                            
                            db_emp = dup_emp
                        else:
                            # Se não há duplicado local com esse nome
                            if not db_emp:
                                db_emp = Employee(
                                    pipedrive_id=pid,
                                    company_id=local_org.id,
                                    name=name,
                                    source="pipedrive",
                                    is_discovery=1
                                )
                                session.add(db_emp)
                            
                        # 3. Atualiza campos se vazios
                        if not db_emp.email and p.get("email"):
                            emails = p.get("email")
                            if isinstance(emails, list) and emails:
                                db_emp.email = emails[0].get("value")
                        
                        if not db_emp.phone and p.get("phone"):
                            phones = p.get("phone")
                            if isinstance(phones, list) and phones:
                                db_emp.phone = phones[0].get("value")
                    
                    await session.commit()
                    log.info("pipedrive.persons.synced", org_id=org_id, count=len(results["persons"]))
        except Exception as e:
            log.warning("pipedrive.persons.sync_failed", error=str(e))

        # Deep discovery de contatos (se necessário)
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

        # Busca dados extras no banco local (ICP Score/Tier)
        icp_info = {"icp_score": None, "icp_tier": None, "linkedin_url": None}
        try:
            from core.infra.database import async_session
            from models import Organization
            from sqlalchemy import select
            async with async_session() as session:
                stmt = select(Organization).where(Organization.pipedrive_id == org_id)
                res = await session.execute(stmt)
                org = res.scalars().first()
                if org:
                    icp_info["icp_score"] = org.icp_score
                    icp_info["icp_tier"] = org.icp_tier
                    icp_info["linkedin_url"] = org.linkedin_url
                    icp_info["cnpj"] = org.cnpj
                    icp_info["domain"] = org.domain
                    icp_info["description"] = org.description
                    icp_info["category"] = org.category
                    icp_info["product_focus"] = org.product_focus
                    icp_info["temperature"] = org.temperature
                    icp_info["prospecting_context"] = org.prospecting_context
                    if org.photo_url:
                        icp_info["photo_url"] = org.photo_url
                    if org.logo_url:
                        icp_info["logo_url"] = org.logo_url
                        icp_info["logo"] = org.logo_url
                        if isinstance(org_data, dict):
                            org_data["logo_url"] = org.logo_url
                            org_data["logo"] = org.logo_url
                            org_data["organization_logo"] = org.logo_url
                            org_data["company_logo"] = org.logo_url
        except Exception:
            pass

        return {
            "id": org_id,
            "primary_deal_id": primary_deal_id,
            "deals": deals,
            "persons": results["persons"],
            "activities": results["activities"],
            "notes": results["notes"],
            "updates": results["updates"],
            "org": results["org"],
            **icp_info
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
        # Tenta buscar contato existente para evitar duplicidade e mesclar dados
        existing_person_id = None
        existing_person = None
        
        # 1. Busca por e-mail primeiro
        if email:
            search_resp = await self._request(
                "GET", 
                "persons/search", 
                params={"term": email, "search_by_email": 1, "exact_match": 1, "limit": 1}
            )
            if search_resp and search_resp.status_code == 200:
                data = search_resp.json()
                items = data.get("data", {}).get("items") or []
                if items and items[0].get("item"):
                    existing_person = items[0]["item"]
                    existing_person_id = existing_person["id"]

        # 2. Se não achou por e-mail, mas temos nome e org_id, busca por nome na mesma empresa
        if not existing_person_id and name and org_id:
            search_resp = await self._request(
                "GET", 
                "persons/search", 
                params={"term": name, "exact_match": 0, "limit": 5}
            )
            if search_resp and search_resp.status_code == 200:
                data = search_resp.json()
                items = data.get("data", {}).get("items") or []
                for i in items:
                    p = i.get("item", {})
                    org = p.get("organization")
                    if org and org.get("id") == org_id:
                        n1, n2 = name.lower(), p.get("name", "").lower()
                        if n1 in n2 or n2 in n1:
                            existing_person = p
                            existing_person_id = p["id"]
                            break
                            
        # Se encontrou um contato existente, vamos ATUALIZÁ-LO (mesclar) preservando Pipedrive
        if existing_person_id and existing_person:
            update_payload = {}
            
            # Atualiza o nome apenas se o novo for mais completo
            if len(name.strip()) > len(existing_person.get("name", "").strip()):
                update_payload["name"] = name
                
            # Se a pessoa não tinha organização, e agora temos, vincula
            if org_id and not existing_person.get("organization"):
                update_payload["org_id"] = org_id
                
            # Adiciona email apenas se a pessoa já não tivesse nenhum
            if email and not existing_person.get("primary_email"):
                 update_payload["email"] = [{"value": email, "primary": True}]
                 
            # Adiciona telefone apenas se a pessoa já não tivesse nenhum (array phones)
            if phone and not existing_person.get("phones"):
                 update_payload["phone"] = [{"value": phone, "primary": True}]

            if update_payload:
                await self._request("PUT", f"persons/{existing_person_id}", json=update_payload)
                log.info("pipedrive.person.merged", person_id=existing_person_id, updates=update_payload)
            else:
                log.info("pipedrive.person.merge_skipped", person_id=existing_person_id, reason="no new data")

            # Retorna os dados como se tivesse sido criado com sucesso
            return {"success": True, "data": {"id": existing_person_id}}

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

    async def create_procurement_contact(self, org_id: int, domain: str) -> dict:
        """
        Garante que existe um contato 'Departamento de Compras' vinculado à organização.
        Idempotente: não cria duplicata se já existir contato com compras@domínio.
        """
        procurement_email = f"compras@{domain}"

        search_resp = await self._request(
            "GET",
            "persons/search",
            params={"term": procurement_email, "search_by_email": 1, "exact_match": 1, "limit": 1},
        )
        if search_resp and search_resp.status_code == 200:
            items = search_resp.json().get("data", {}).get("items") or []
            if items:
                existing_id = items[0]["item"]["id"]
                log.info(
                    "pipedrive.procurement_contact.exists",
                    person_id=existing_id,
                    email=procurement_email,
                )
                return {"success": True, "data": {"id": existing_id}, "existing": True}

        result = await self.create_person(
            name="Departamento de Compras",
            email=procurement_email,
            org_id=org_id,
        )
        log.info(
            "pipedrive.procurement_contact.created",
            email=procurement_email,
            org_id=org_id,
        )
        return result

    async def update_deal(self, deal_id: int, data: dict) -> dict:
        resp = await self._request("PUT", f"deals/{deal_id}", json=data)
        if resp is None:
            return {"success": False}
        try:
            return resp.json()
        except Exception:
            return {"success": False}

    async def get_pipeline_board(self) -> dict:
        """Busca os estágios do pipeline padrão e todos os negócios abertos para montar o Kanban."""
        try:
            stages_resp = await self._request("GET", "stages")
            if stages_resp is None or stages_resp.status_code != 200:
                return {"success": False, "error": "Erro ao buscar stages"}
            
            stages = stages_resp.json().get("data") or []
            stages = sorted(stages, key=lambda x: x.get("order_nr", 0))

            deals_resp = await self._request("GET", "deals", params={"status": "open", "limit": 500})
            if deals_resp is None or deals_resp.status_code != 200:
                return {"success": False, "error": "Erro ao buscar deals"}
            
            deals = deals_resp.json().get("data") or []

            return {
                "success": True,
                "data": {
                    "stages": stages,
                    "deals": deals
                }
            }
        except Exception as e:
            log.error("pipedrive.get_pipeline_board.error", error=str(e))
            return {"success": False, "error": str(e)}


# Singleton
pipedrive_service = PipedriveService()


AUTO_RESCHEDULE_SETTING_KEY = "crm_auto_reschedule_overdue"
# Chave separada do toggle acima de propósito: o toggle é editado pelo usuário via tela de
# preferências (POST /settings/{key} substitui o `value` inteiro), então guardar o controle de
# "já rodou hoje" na mesma chave faria o usuário apagá-lo sem querer ao ligar/desligar o switch.
AUTO_RESCHEDULE_LAST_RUN_KEY = "crm_auto_reschedule_last_run"


async def run_daily_overdue_reschedule_if_needed() -> None:
    """Roda `sync_overdue_activities()` uma vez por dia calendário (fuso America/Sao_Paulo),
    apenas se o toggle `crm_auto_reschedule_overdue` estiver habilitado.

    Pensado para ser chamado a cada boot do backend (lifespan de main.py): se o servidor
    já rodou hoje, ou se o usuário desligou o toggle (ex: período de férias), não faz nada.
    """
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import select
    from core.infra.database import async_session
    from models.system.system_setting import SystemSetting

    sao_paulo_tz = timezone(timedelta(hours=-3))
    today = datetime.now(sao_paulo_tz).date().isoformat()

    async with async_session() as session:
        toggle_result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == AUTO_RESCHEDULE_SETTING_KEY)
        )
        toggle_setting = toggle_result.scalars().first()

        # Ainda não configurado pelo usuário — habilitado por padrão.
        enabled = toggle_setting.value.get("enabled", True) if toggle_setting else True
        if not enabled:
            log.info("crm.auto_reschedule.disabled_skip")
            return

        last_run_result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == AUTO_RESCHEDULE_LAST_RUN_KEY)
        )
        last_run_setting = last_run_result.scalars().first()

        if last_run_setting and last_run_setting.value.get("date") == today:
            log.info("crm.auto_reschedule.already_run_today", date=today)
            return

        try:
            sync_result = await pipedrive_service.sync_overdue_activities()
            log.info("crm.auto_reschedule.completed", date=today, result=sync_result)
        except Exception as e:
            log.warning("crm.auto_reschedule.failed", error=str(e))
            return

        if last_run_setting:
            last_run_setting.value = {"date": today}
        else:
            session.add(SystemSetting(key=AUTO_RESCHEDULE_LAST_RUN_KEY, category="crm", value={"date": today}))
        await session.commit()


__all__ = [
    "PipedriveService",
    "pipedrive_service",
    "run_daily_overdue_reschedule_if_needed",
    "AUTO_RESCHEDULE_SETTING_KEY",
]
