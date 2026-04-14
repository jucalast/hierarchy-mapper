import httpx
from typing import List, Dict, Any, Optional
import os
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

class PipedriveService:
    def __init__(self):
        self.api_token = os.getenv("PIPEDRIVE_API_TOKEN")
        self.user_id = 24921888 # ID João Luccas
        self.base_url = "https://api.pipedrive.com/v1"

    async def create_organization(self, data: dict):
        """Cria uma nova organização no Pipedrive e retorna o ID."""
        url = f"{self.base_url}/organizations?api_token={self.api_token}"
        payload = {
            "name": data.get("name"),
            "address": data.get("address"),
            "c04f98a7a9762df2f8a42e5d7a641a0292723326": data.get("domain")
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
        return None

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
        if data.get("domain"): payload["c04f98a7a9762df2f8a42e5d7a641a0292723326"] = data.get("domain") # Sincroniza o domínio oficial
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

        return pipedrive_success

    async def list_organizations(self):
        """
        Lista empresas priorizando o banco de dados local para velocidade.
        Tenta sincronizar com o Pipedrive em paralelo.
        """
        from core.database import async_session
        from models import Organization
        from sqlalchemy import select

        # 1. Busca imediata no banco local
        async with async_session() as session:
            stmt = select(Organization).order_by(Organization.last_enrichment.desc())
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
                                
                                # 🔍 FILTRO: Ignora empresas com negócios PERDIDOS e nenhum ABERTO
                                open_deals = org.get("open_deals_count", 0)
                                lost_deals = org.get("lost_deals_count", 0)
                                if open_deals == 0 and lost_deals > 0:
                                    continue
                                
                                # Tenta achar por ID ou por Nome (Case Insensitive) para evitar duplicidade
                                from sqlalchemy import func
                                stmt = select(Organization).where(
                                    (Organization.pipedrive_id == pid) | 
                                    (func.lower(Organization.name) == name.lower())
                                )
                                res = await session.execute(stmt)
                                db_org = res.scalars().first()
                                
                                if not db_org:
                                    db_org = Organization(pipedrive_id=pid, name=name)
                                    session.add(db_org)
                                    print(f"[Pipedrive Sync] Nova empresa: {name}")
                                else:
                                    # Atualiza registro existente (Sincroniza IDs, mas preserva NOME se ele já estiver 'limpo')
                                    db_org.pipedrive_id = pid
                                    if not db_org.name: 
                                        db_org.name = name
                                    print(f"[Pipedrive Sync] Atualizando: {name}")
                                    
                                # Atualiza metadados apenas se vierem novos e válidos do Pipedrive
                                p_domain = org.get("c04f98a7a9762df2f8a42e5d7a641a0292723326")
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

    async def get_organization_details(self, org_id: int):
        """Busca o 'Raio-X' completo da empresa: Contatos, Tarefas, Negócios e Notas."""
        import asyncio
        async with httpx.AsyncClient() as client:
            # 1. Busca Negócios Primeiro para identificar o Principal
            deals_resp = await client.get(f"{self.base_url}/organizations/{org_id}/deals?api_token={self.api_token}")
            deals_data = deals_resp.json()
            deals = deals_data.get("data") or []
            
            # Identifica o Negócio Principal (Aberto preferencialmente, ou o mais recente)
            primary_deal = next((d for d in deals if d.get("status") == "open"), None)
            if not primary_deal and deals:
                primary_deal = deals[0] # Pega o mais recente
            
            primary_deal_id = primary_deal.get("id") if primary_deal else None

            # 2. Prepara URLs filtradas (ou gerais se não houver deal)
            urls = {
                "persons": f"{self.base_url}/organizations/{org_id}/persons?api_token={self.api_token}",
                "activities": f"{self.base_url}/organizations/{org_id}/activities?api_token={self.api_token}",
                "notes": f"{self.base_url}/notes?org_id={org_id}&api_token={self.api_token}",
                "updates": f"{self.base_url}/organizations/{org_id}/flow?api_token={self.api_token}"
            }
            
            tasks = {key: client.get(url) for key, url in urls.items()}
            responses = await asyncio.gather(*tasks.values())
            results = {key: resp.json().get("data") or [] for key, resp in zip(tasks.keys(), responses)}
            
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

# Singleton
pipedrive_service = PipedriveService()
