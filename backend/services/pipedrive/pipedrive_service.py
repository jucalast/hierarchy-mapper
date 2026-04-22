import asyncio
import time
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta

from core.config import settings


class PipedriveService:
    _stages_cache = {} 
    _retry_after_until = 0 # Timestamp de quando o bloqueio acaba
    _client = None
    _semaphore = asyncio.Semaphore(10) # Limita concorrência global a 10 requests simultâneos

    def __init__(self):
        self.api_token = settings.PIPEDRIVE_API_TOKEN
        self.user_id = settings.PIPEDRIVE_USER_ID
        self.base_url = "https://api.pipedrive.com/v1"

    async def get_client(self):
        if PipedriveService._client is None or PipedriveService._client.is_closed:
            PipedriveService._client = httpx.AsyncClient(timeout=30.0)
        return PipedriveService._client

    def _update_retry_after(self, resp):
        """Extrai o tempo de espera dos headers do Pipedrive se for 429."""
        if resp and resp.status_code == 429:
            retry_after = resp.headers.get("retry-after")
            if retry_after:
                try:
                    PipedriveService._retry_after_until = time.time() + int(retry_after) + 0.5 # Margem de segurança
                    print(f"[Pipedrive Service] ⏳ Bloqueio detectado! Retry-After: {retry_after}s")
                except: pass

    async def make_request(self, method: str, endpoint: str, **kwargs):
        """Método centralizado para chamadas Pipedrive com monitoramento de cota e espera automática."""
        url = f"{self.base_url}/{endpoint}"
        connector = "&" if "?" in endpoint else "?"
        url += f"{connector}api_token={self.api_token}"
            
        async with PipedriveService._semaphore:
            # 1. Verifica se estamos em cooldown
            wait_time = PipedriveService._retry_after_until - time.time()
            if wait_time > 0:
                print(f"[Pipedrive Service] 💤 Aguardando reset do Rate Limit ({int(wait_time)}s)...")
                await asyncio.sleep(wait_time)

            client = await self.get_client()
            try:
                resp = await client.request(method, url, **kwargs)
                
                # 2. Se deu 429, atualiza timer e tenta novamente UMA vez após o tempo
                if resp.status_code == 429:
                    self._update_retry_after(resp)
                    wait_time = PipedriveService._retry_after_until - time.time()
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
                        # Retry
                        resp = await client.request(method, url, **kwargs)
                
                return resp
            except Exception as e:
                print(f"[Pipedrive Service] Erro na requisição {endpoint}: {e}")
                return None

    def get_retry_after_seconds(self) -> int:
        """Retorna quantos segundos faltam para o reset do Pipedrive."""
        remaining = int(PipedriveService._retry_after_until - time.time())
        return max(0, remaining)

    async def get_all_stages(self):
        """Busca todos os estágios do pipeline com cache para poupar API."""
        if PipedriveService._stages_cache:
            return PipedriveService._stages_cache
            
        resp = await self.make_request("GET", "stages")
        if resp and resp.status_code == 200:
            s_data = resp.json().get("data") or []
            PipedriveService._stages_cache = {s["id"]: s["name"] for s in s_data}
            return PipedriveService._stages_cache
        return {}

    async def create_organization(self, data: dict):
        """Cria uma nova organização no Pipedrive e retorna o ID."""
        url = f"{self.base_url}/organizations?api_token={self.api_token}"
        payload = {
            "name": data.get("name"),
            "address": data.get("address"),
            "website": data.get("domain")
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload)
                res_data = resp.json()
                if res_data.get("success"):
                    org_id = res_data["data"]["id"]
                    print(f"[Pipedrive Service] ✨ Nova empresa criada no Pipedrive: {org_id}")
                    return org_id
        except Exception as e:
            print(f"[Pipedrive Service] Erro ao criar empresa no Pipedrive: {e}")
    async def get_person_details(self, person_id: int):
        """Busca detalhes completos de uma pessoa (email, fone)."""
        url = f"{self.base_url}/persons/{person_id}?api_token={self.api_token}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json().get("data")
                    return data
        except Exception as e:
            print(f"[Pipedrive Service] Erro ao buscar pessoa {person_id}: {e}")
        return None

    async def update_activity(self, activity_id: int, data: dict):
        """Atualiza uma atividade existente no Pipedrive."""
        url = f"{self.base_url}/activities/{activity_id}?api_token={self.api_token}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.put(url, json=data)
                res_data = resp.json()
                if res_data.get("success"):
                    print(f"[Pipedrive Service] Success: Atividade {activity_id} atualizada.")
                    return True
        except Exception as e:
            print(f"[Pipedrive Service] Erro ao atualizar atividade: {e}")
        return False

    async def delete_activity(self, activity_id: int):
        """Remove uma atividade do Pipedrive."""
        url = f"{self.base_url}/activities/{activity_id}?api_token={self.api_token}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(url)
                res_data = resp.json()
                if res_data.get("success"):
                    print(f"[Pipedrive Service] Atividade {activity_id} removida com sucesso.")
                    return True
        except Exception as e:
            print(f"[Pipedrive Service] Erro ao remover atividade: {e}")
        return False

    async def update_organization(self, org_id: int, data: dict):
        """Atualiza Endereço, CNPJ e Domínio no Pipedrive e no Banco Local."""
        from core.database import async_session
        from models import Organization
        from sqlalchemy import select

        # 1. Update no Pipedrive
        # c04f98a7a9762df2f8a42e5d7a641a0292723326 -> CHAVE DO DOMÍNIO IDENTIFICADA NO CÓDIGO
        url = f"{self.base_url}/organizations/{org_id}?api_token={self.api_token}"
        payload = {}
        if data.get("address"): payload["address"] = data.get("address")
        if data.get("domain"): payload["website"] = data.get("domain") # Sincroniza o domínio oficial
        if data.get("name"): payload["name"] = data.get("name")
        
        # Pipedrive não fará requisição sem payload
        if not payload:
            return True
            
        pipedrive_success = False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.put(url, json=payload)
                print(f"[Pipedrive Service] Update Status: {resp.status_code}")
                pipedrive_success = resp.status_code == 200
        except Exception as e: 
            print(f"[Pipedrive Service] Erro Pipedrive API: {e}")

        # 2. Update no Banco Local (Garante que o Drawer mostre o dado novo imediatamente)
        try:
            async with async_session() as session:
                stmt = select(Organization).where(Organization.pipedrive_id == org_id)
                res = await session.execute(stmt)
                org = res.scalars().first()
                if org:
                    if data.get("cnpj"): org.cnpj = data.get("cnpj").replace(".", "").replace("/", "").replace("-", "")
                    if data.get("domain"): org.domain = data.get("domain")
                    if data.get("address"): org.address = data.get("address")
                    if data.get("linkedin_url"): org.linkedin_url = data.get("linkedin_url")
                    if data.get("logo_url"): org.logo_url = data.get("logo_url")
                    if data.get("name"): org.name = data.get("name")
                    await session.commit()
                    print(f"[Pipedrive Service] Banco Local atualizado via Confirmação Intelligence.")
        except Exception as e:
            print(f"[Pipedrive Service] Erro ao atualizar banco local: {e}")

    async def update_person(self, person_id: int, data: dict):
        """
        Atualiza dados de uma pessoa no Pipedrive e no banco local.
        """
        from core.database import async_session
        from models import Employee
        from sqlalchemy import select

        url = f"{self.base_url}/persons/{person_id}?api_token={self.api_token}"
        
        # 1. Update no Pipedrive
        payload = {}
        if data.get("phone"): 
            payload["phone"] = [{"value": data["phone"], "primary": True}]
        if data.get("email"): payload["email"] = [{"value": data["email"], "primary": True}]
        if data.get("name"): payload["name"] = data["name"]
        
        pipedrive_success = False
        if payload:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.put(url, json=payload)
                    pipedrive_success = resp.status_code == 200
            except Exception as e:
                print(f"[Pipedrive Service] Erro ao atualizar pessoa no API: {e}")

        # 2. Update Banco Local
        try:
            async with async_session() as session:
                stmt = select(Employee).where(Employee.pipedrive_id == str(person_id))
                res = await session.execute(stmt)
                emp = res.scalars().first()
                if emp:
                    if data.get("phone"): emp.phone = data["phone"]
                    if data.get("email"): emp.email = data["email"]
                    if data.get("name"): emp.name = data["name"]
                    await session.commit()
        except Exception as e:
            print(f"[Pipedrive Service] Erro ao atualizar banco local (Person): {e}")

        return pipedrive_success

    async def list_organizations(self):
        """
        Lista empresas priorizando o banco de dados local para velocidade.
        Tenta sincronizar com o Pipedrive em paralelo.
        """
        from core.database import async_session
        from models import Organization
        from sqlalchemy import select

        # 1. Busca imediata no banco local (Filtrando as excluídas)
        async with async_session() as session:
            stmt = select(Organization).where(Organization.is_excluded != 1).order_by(Organization.last_enrichment.desc())
            res = await session.execute(stmt)
            local_orgs = res.scalars().all()
            
        # 2. Se o banco está vazio ou queremos atualizar, sincroniza com Pipedrive
        if not local_orgs:
            url = f"{self.base_url}/organizations?user_id={self.user_id}&start=0&limit=500&api_token={self.api_token}"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(url)
                    data = resp.json()
                    if data.get("success"):
                        all_orgs = data.get("data") or []
                        async with async_session() as session:
                            for org in all_orgs:
                                pid = org.get("id")
                                name = org.get("name", "").strip()
                                
                                # 🔍 FILTRO AGRESSIVO: Só traz empresas com NEGÓCIOS ABERTOS
                                # Isso garante que se você excluiu o negócio, ela suma do Drawer
                                open_deals = org.get("open_deals_count", 0)
                                if open_deals == 0:
                                    continue
                                
                                # 🔍 FILTRO 2: Ignora se o nome for muito genérico ou vazio
                                if not name or len(name) < 2:
                                    continue
                                
                                # Tenta achar por ID ou por Nome (Case Insensitive) para evitar duplicidade
                                from sqlalchemy import func
                                stmt = select(Organization).where(
                                    (Organization.pipedrive_id == pid) | 
                                    (func.lower(Organization.name) == name.lower())
                                )
                                res = await session.execute(stmt)
                                db_org = res.scalars().first()
                                
                                # 🔍 FILTRO 3: Se já existe na BLACKLIST local, ignora permanentemente
                                if db_org and db_org.is_excluded == 1:
                                    continue

                                if not db_org:
                                    # SE NÃO EXISTE LOCALMENTE, SÓ ADICIONA SE TIVER NEGÓCIO ABERTO (Já garantido pelo filtro acima)
                                    db_org = Organization(pipedrive_id=pid, name=name)
                                    session.add(db_org)
                                    print(f"[Pipedrive Sync] Nova empresa detectada: {name}")
                                else:
                                    # Atualiza registro existente
                                    db_org.pipedrive_id = pid
                                    if not db_org.name: 
                                        db_org.name = name
                                    # print(f"[Pipedrive Sync] Atualizando: {name}")
                                    
                                # Atualiza metadados apenas se vierem novos e válidos do Pipedrive
                                p_domain = org.get("website")
                                if p_domain and len(str(p_domain)) > 3: 
                                    db_org.domain = p_domain
                                
                                p_address = org.get("address")
                                if p_address and len(str(p_address)) > 3: 
                                    db_org.address = p_address
                            
                            await session.commit()
                        async with async_session() as session:
                            stmt = select(Organization).order_by(Organization.last_enrichment.desc())
                            res = await session.execute(stmt)
                            local_orgs = res.scalars().all()
            except Exception as e:
                print(f"[Pipedrive Sync] Erro: {e}")

        # Retorna o formato que o frontend espera
        result = []
        async with async_session() as session:
            for o in local_orgs:
                # Busca os 3 últimos funcionários com foto
                from models import Employee
                from sqlalchemy import select, func
                
                # Employee count (Excluindo Sócios)
                count_stmt = select(func.count(Employee.id)).where(
                    (Employee.company_id == o.id) & (Employee.department != "Quadro Societário")
                )
                count_res = await session.execute(count_stmt)
                emp_count = count_res.scalar() or 0
                
                # Top 3 pics (Apenas Funcionários reais)
                pics_stmt = select(Employee.profile_pic).where(
                    (Employee.company_id == o.id) & 
                    (Employee.department != "Quadro Societário") &
                    (Employee.profile_pic != None) & 
                    (Employee.profile_pic != "")
                ).limit(3)
                pics_res = await session.execute(pics_stmt)
                pics = [p for p in pics_res.scalars().all()]
                
                result.append({
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
                    "employee_pics": pics
                })
        
        return result

    async def sync_overdue_activities(self):
        """Move todas as atrasadas para hoje (Perdoar Atrasos)."""
        today = date.today().isoformat()
        url_fetch = f"{self.base_url}/activities?user_id={self.user_id}&done=0&api_token={self.api_token}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url_fetch)
                data = resp.json()
                if not data or not data.get("success"): return {"status": "error", "message": "Sem tarefas."}
                activities = data.get("data") or []
                updated = 0
                for act in activities:
                    due = act.get("due_date")
                    if due and due < today:
                        await client.put(f"{self.base_url}/activities/{act.get('id')}?api_token={self.api_token}", json={"due_date": today})
                        updated += 1
                return {"status": "success", "message": f"{updated} atrasos perdoados."}
        except Exception as e: return {"status": "error", "message": str(e)}

    async def smart_reschedule_activities(self):
        """
        Remanejamento Inteligente v2:
        - Group by Deal (Negócio)
        - Priority: Oldest last activity
        - balanced by Pipeline Stage
        - Respect 10/day and Weekends
        """
        from collections import defaultdict
        today_date = date.today()
        
        # Garante que começamos em dia útil
        if today_date.weekday() >= 5:
            today_date += timedelta(days=(7 - today_date.weekday()))

        print(f"[Smart Scheduler] Iniciando v2. Data base: {today_date.isoformat()}")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 1. Busca Atividades
                url_act = f"{self.base_url}/activities?user_id={self.user_id}&limit=500&api_token={self.api_token}"
                resp_act = await client.get(url_act)
                act_data = resp_act.json()
                if not act_data.get("success"): return {"status": "error", "message": "Falha ao buscar atividades."}
                
                # 2. Busca Negócios (Deals) para saber as etapas
                url_deals = f"{self.base_url}/deals?user_id={self.user_id}&limit=500&status=open&api_token={self.api_token}"
                resp_deals = await client.get(url_deals)
                deals_data = resp_deals.json()
                
                # Mapeia Estágio do Negócio
                deal_stages = {}
                if deals_data.get("success"):
                    for d in (deals_data.get("data") or []):
                        deal_stages[d['id']] = d.get('stage_id')

                # 3. Processa Histórico e Tarefas Abertas por Negócio
                activities = act_data.get("data") or []
                deal_open_tasks = defaultdict(list)
                deal_last_done = {}
                
                all_stages = set()

                for act in activities:
                    deal_id = act.get("deal_id")
                    if not deal_id: continue
                    
                    stage_id = deal_stages.get(deal_id, 0) # 0 se não encontrar estágio
                    all_stages.add(stage_id)
                    
                    is_done = act.get("done") == 1
                    due_date = act.get("due_date")
                    
                    if is_done:
                        if due_date:
                            current_last = deal_last_done.get(deal_id, "1900-01-01")
                            if due_date > current_last:
                                deal_last_done[deal_id] = due_date
                    else:
                        act['stage_id'] = stage_id
                        deal_open_tasks[deal_id].append(act)

                # 4. Agrupa Tarefas Abertas por Estágio e Ordena por Prioridade (Último Follow-up)
                stage_queues = defaultdict(list) # stage_id -> [list of tasks]
                
                # Ordenar negócios globalmente primeiro
                sorted_deals = sorted(
                    deal_open_tasks.keys(),
                    key=lambda did: deal_last_done.get(did, "1900-01-01")
                )

                for did in sorted_deals:
                    stage_id = deal_stages.get(did, 0)
                    stage_queues[stage_id].extend(deal_open_tasks[did])

                # 5. Distribuição Round-Robin Equilibrada
                scheduled_updates = []
                current_day = today_date
                
                # Ordena os estágios para processamento consistente
                sorted_stages = sorted(list(all_stages))
                
                # Mapa para controlar quantas tarefas já colocamos em cada dia
                # (date_str) -> count
                daily_load = defaultdict(int)
                
                # Mapa para garantir que um mesmo negócio não tenha 2 tarefas no mesmo dia
                # (date_str, deal_id) -> bool
                deal_day_map = {}

                has_tasks = True
                while has_tasks:
                    has_tasks = False
                    for stage_id in sorted_stages:
                        if stage_queues[stage_id]:
                            task = stage_queues[stage_id].pop(0)
                            deal_id = task.get("deal_id")
                            has_tasks = True
                            
                            # Tenta encontrar o primeiro dia disponível para essa tarefa
                            # Respeitando: 1. Limite de 10/dia, 2. Um negócio por dia, 3. Finais de semana
                            target_day = current_day
                            found_day = False
                            
                            max_attempts = 30 # Proteção contra infinitos
                            attempt = 0
                            
                            while not found_day and attempt < max_attempts:
                                d_str = target_day.isoformat()
                                # Pula final de semana
                                if target_day.weekday() >= 5:
                                    target_day += timedelta(days=1)
                                    continue
                                
                                # Verifica carga (10/dia) e duplicidade de negócio no mesmo dia
                                if daily_load[d_str] < 10 and (d_str, deal_id) not in deal_day_map:
                                    scheduled_updates.append((task.get("id"), d_str))
                                    daily_load[d_str] += 1
                                    deal_day_map[(d_str, deal_id)] = True
                                    found_day = True
                                else:
                                    target_day += timedelta(days=1)
                                    attempt += 1
                
                # 6. Executa Updates
                updated = 0
                for tid, d_str in scheduled_updates:
                    upd_url = f"{self.base_url}/activities/{tid}?api_token={self.api_token}"
                    r = await client.put(upd_url, json={"due_date": d_str})
                    if r.status_code == 200: updated += 1
                
                final_day = max([u[1] for u in scheduled_updates]) if scheduled_updates else today_date.isoformat()
                
                print(f"[Smart Scheduler] Concluído v2 (Balanced): {updated} tasks.")
                return {
                    "status": "success",
                    "message": f"Remanejamento Balanceado: {updated} tarefas priorizadas por negócio e distribuídas por etapa. Máximo 1 tarefa por negócio/dia.",
                    "stats": {"updated": updated, "start_date": today_date.isoformat(), "end_date": str(final_day)}
                }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    async def delete_organization(self, org_id: int):
        """Exclui uma organização no Pipedrive pelo ID e do banco de dados local (Blacklist)."""
        from core.database import async_session
        from models import Organization, Employee
        from sqlalchemy import select, delete, or_
        
        target_pid = None
        org_local_id = None
        
        # 🕵️ 1. BUSCA AGRESSIVA NO BANCO LOCAL PARA IDENTIFICAR A EMPRESA
        try:
            async with async_session() as session:
                # O org_id recebido pode ser o Pipedrive ID OU o ID local
                stmt = select(Organization).where(
                    or_(Organization.pipedrive_id == org_id, Organization.id == org_id)
                )
                res = await session.execute(stmt)
                org = res.scalars().first()
                
                if org:
                    target_pid = org.pipedrive_id
                    org_local_id = org.id
                    print(f"[Pipedrive Service] Empresa encontrada localmente: {org.name} (Local ID: {org.id}, Pipedrive ID: {target_pid})")
                else:
                    # Se não achou localmente, assumimos que o org_id seja o Pipedrive ID
                    target_pid = org_id
                    print(f"[Pipedrive Service] Empresa não encontrada localmente. Assumindo org_id {org_id} como Pipedrive ID.")
        except Exception as e:
            print(f"[Pipedrive Service] Erro ao buscar empresa local: {e}")
            target_pid = org_id # Fallback

        pipedrive_success = False
        error_code = None
        
        # 2. DELETAR DO PIPEDRIVE (Só se tivermos um Pipedrive ID válido)
        if target_pid:
            url = f"{self.base_url}/organizations/{target_pid}?api_token={self.api_token}"
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.delete(url)
                    res_data = resp.json() if resp.status_code != 204 else {"success": True}
                    
                    if resp.status_code in [200, 204] and res_data.get("success"):
                        pipedrive_success = True
                        print(f"[Pipedrive Service] Organização {target_pid} excluída com sucesso no Pipedrive.")
                    elif resp.status_code == 403 or res_data.get("code") == "ERR_ORGANIZATION_MISSING_PERMISSIONS":
                        error_code = "ERR_ORGANIZATION_MISSING_PERMISSIONS"
                        print(f"[Pipedrive Service] 🛡️ Permissão negada para excluir Org {target_pid}. Tentando limpar negócios...")
                        
                        # Limpa negócios (mais agressivo)
                        try:
                            deals_url = f"{self.base_url}/organizations/{target_pid}/deals?status=open&api_token={self.api_token}"
                            d_resp = await client.get(deals_url)
                            d_data = d_resp.json()
                            if d_data.get("success") and d_data.get("data"):
                                for deal in d_data["data"]:
                                    deal_id = deal["id"]
                                    del_resp = await client.delete(f"{self.base_url}/deals/{deal_id}?api_token={self.api_token}")
                                    if del_resp.status_code in [200, 204]:
                                        print(f"[Pipedrive Service] 🗑️ Negócio {deal_id} EXCLUÍDO.")
                                    else:
                                        await client.put(
                                            f"{self.base_url}/deals/{deal_id}?api_token={self.api_token}", 
                                            json={"status": "lost", "lost_reason": "Removido via Hierarchy Mapper"}
                                        )
                        except Exception as deal_err:
                            print(f"[Pipedrive Service] ⚠️ Falha ao limpar negócios: {deal_err}")
                    else:
                        error_code = res_data.get("code")
            except Exception as e:
                print(f"[Pipedrive Service] Erro Pipedrive API: {e}")

        # 3. BLACKLIST LOCAL: Marca como EXCLUÍDA no banco (Impedir re-sync)
        try:
            async with async_session() as session:
                # O org_local_id ou target_pid DEVEM existir aqui se a empresa foi encontrada no passo 1
                stmt = None
                if target_pid is not None and org_local_id is not None:
                    stmt = select(Organization).where(or_(Organization.pipedrive_id == target_pid, Organization.id == org_local_id))
                elif target_pid is not None:
                    stmt = select(Organization).where(Organization.pipedrive_id == target_pid)
                elif org_local_id is not None:
                    stmt = select(Organization).where(Organization.id == org_local_id)
                
                if stmt is not None:
                    res = await session.execute(stmt)
                    org = res.scalars().first()
                    
                    if org:
                        # Limpa funcionários
                        await session.execute(delete(Employee).where(Employee.company_id == org.id))
                        
                        # Blacklist
                        org.is_excluded = 1
                        org.cnpj = None
                        org.domain = None
                        await session.commit()
                        print(f"[Pipedrive Service] Blacklist ativada para {org.name} (Local ID: {org.id}).")
                    elif target_pid:
                        # Se não existia, cria registro de bloqueio
                        new_blocked = Organization(pipedrive_id=target_pid, is_excluded=1, name="EXCLUDED_ORG")
                        session.add(new_blocked)
                        await session.commit()
                        print(f"[Pipedrive Service] Criado registro de bloqueio para Pipedrive ID {target_pid}.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Pipedrive Service] Erro ao processar blacklist local: {e}")

        if not pipedrive_success and error_code == "ERR_ORGANIZATION_MISSING_PERMISSIONS":
            return "partial_success_permissions"
            
        return pipedrive_success

    async def get_organization_details(self, org_id: int, done: Optional[int] = None):
        """Busca o 'Raio-X' completo da empresa: Contatos, Tarefas, Negócios e Notas."""
        import asyncio
        async with httpx.AsyncClient() as client:
            # 1. Busca Negócios Primeiro para identificar o Principal (Filtrado por Usuário)
            deals_resp = await client.get(f"{self.base_url}/organizations/{org_id}/deals?user_id={self.user_id}&api_token={self.api_token}")
            deals_data = deals_resp.json()
            deals = deals_data.get("data") or []
            
            # --- MAPEAMENTO DE ESTÁGIOS (STAGE NAMES) com Cache ---
            if not PipedriveService._stages_cache:
                try:
                    stages_resp = await client.get(f"{self.base_url}/stages?api_token={self.api_token}")
                    if stages_resp.status_code == 200:
                        s_data = stages_resp.json().get("data") or []
                        PipedriveService._stages_cache = {s["id"]: s["name"] for s in s_data}
                        print(f"[Pipedrive Service] 🗄️ Cache de estágios populado ({len(s_data)} itens).")
                except Exception as e:
                    print(f"[Pipedrive Service] Erro ao mapear estágios: {e}")
            
            stages_map = PipedriveService._stages_cache
            
            # Enriquece os deals com o nome da etapa e formata valor
            for d in deals:
                d["stage_name"] = stages_map.get(d.get("stage_id"), f"Estágio {d.get('stage_id')}")
                # Garante que o valor seja legível
                d["formatted_value"] = f"{d.get('currency', 'BRL')} {d.get('value', 0):,.2f}"

            # Identifica o Negócio Principal (Aberto preferencialmente, ou o mais recente)
            primary_deal = next((d for d in deals if d.get("status") == "open"), None)
            if not primary_deal and deals:
                primary_deal = deals[0] # Pega o mais recente
            
            primary_deal_id = primary_deal.get("id") if primary_deal else None

            # Filtro de status de atividade (Se None, buscamos ambos para 'All')
            done_values = [0, 1] if done is None else [done]
            
            # 2. Prepara URLs (Removido user_id para visibilidade total da organização)
            urls = {
                "persons": f"{self.base_url}/organizations/{org_id}/persons?api_token={self.api_token}",
                "notes": f"{self.base_url}/notes?org_id={org_id}&api_token={self.api_token}",
                "updates": f"{self.base_url}/organizations/{org_id}/flow?api_token={self.api_token}"
            }
            
            # Adiciona as atividades
            for i, dv in enumerate(done_values):
                urls[f"activities_{i}"] = f"{self.base_url}/organizations/{org_id}/activities?done={dv}&api_token={self.api_token}"

            tasks = {key: client.get(url) for key, url in urls.items()}
            responses = await asyncio.gather(*tasks.values())
            raw_results = {key: resp.json().get("data") or [] for key, resp in zip(tasks.keys(), responses)}
            
            # Merge das fatias de atividades
            merged_activities = []
            for i in range(len(done_values)):
                merged_activities.extend(raw_results.get(f"activities_{i}", []))
            
            results = {
                "persons": raw_results["persons"],
                "notes": raw_results["notes"],
                "updates": raw_results["updates"],
                "activities": merged_activities
            }

            # 🕵️ DESCOBERTA PROFUNDA DE CONTATOS (Garante que Bianca e outros sejam encontrados)
            found_person_ids = set()
            
            def extract_pid(val):
                if not val: return None
                if isinstance(val, dict):
                    return val.get("id") or val.get("value")
                return val

            for act in results["activities"]:
                pid = extract_pid(act.get("person_id"))
                if pid: found_person_ids.add(pid)
            for deal in deals:
                pid = extract_pid(deal.get("person_id"))
                if pid: found_person_ids.add(pid)
            
            # Filtra IDs que já temos na lista primária para evitar requests duplicadas
            existing_ids = {extract_pid(p.get("id")) for p in results["persons"] if p.get("id")}
            missing_ids = [pid for pid in found_person_ids if pid and pid not in existing_ids]
            
            if missing_ids:
                print(f"[Pipedrive Service] 🔍 Deep Discovery: Buscando mais {len(missing_ids)} contatos via IDs de atividades/deals...")
                person_tasks = [self.get_person_details(pid) for pid in list(missing_ids)[:10]]
                persons_found = await asyncio.gather(*person_tasks)
                results["persons"].extend([p for p in persons_found if p])

            # 3. FILTRAGEM: Se temos um negócio principal, limpamos o ruído das outras atividades
            if primary_deal_id:
                results["activities"] = [a for a in results["activities"] if a.get("deal_id") == primary_deal_id]
                results["notes"] = [n for n in results["notes"] if n.get("deal_id") == primary_deal_id]
            
            return {
                "id": org_id,
                "primary_deal_id": primary_deal_id,
                "deals": deals,
                "persons": results["persons"],
                "activities": results["activities"],
                "notes": results["notes"],
                "updates": results["updates"]
            }

    async def create_activity(self, data: dict):
        """Cria uma atividade no Pipedrive."""
        url = f"{self.base_url}/activities?api_token={self.api_token}"
        # Garante que campos obrigatórios existem
        if not data.get("user_id"): data["user_id"] = self.user_id
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=data)
            return resp.json()

    async def update_activity(self, activity_id: int, data: dict):
        """Atualiza uma atividade existente."""
        url = f"{self.base_url}/activities/{activity_id}?api_token={self.api_token}"
        async with httpx.AsyncClient() as client:
            resp = await client.put(url, json=data)
            return resp.json()

    async def create_person(self, name: str, email: str = None, phone: str = None, org_id: int = None):
        """Cria uma pessoa no Pipedrive e vincula à organização."""
        url = f"{self.base_url}/persons?api_token={self.api_token}"
        payload = {
            "name": name,
            "owner_id": self.user_id,
            "org_id": org_id,
            "email": [{"value": email, "primary": True}] if email else None,
            "phone": [{"value": phone, "primary": True}] if phone else None
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
            return resp.json()

    async def update_person(self, person_id: int, data: dict):
        """Atualiza dados de uma pessoa."""
        url = f"{self.base_url}/persons/{person_id}?api_token={self.api_token}"
        async with httpx.AsyncClient() as client:
            resp = await client.put(url, json=data)
            return resp.json()

    async def update_deal(self, deal_id: int, data: dict):
        """Atualiza um negócio (útil para vincular person_id post-sync)."""
        url = f"{self.base_url}/deals/{deal_id}?api_token={self.api_token}"
        async with httpx.AsyncClient() as client:
            resp = await client.put(url, json=data)
            return resp.json()

# Singleton
pipedrive_service = PipedriveService()
