"""
modules.intelligence.service.sync_hub
======================================
Hub de sincronizacao background: Pipedrive + WhatsApp + Email -> SQLite.

Executado como asyncio.Task no startup. Aguarda servicos externos ficarem
online (WhatsApp :8001, Email :8002) com timeout configuravel.

Classe: SyncIntelligenceHub | Metodo principal: sync_all()
"""
import asyncio
import httpx
from sqlalchemy.future import select
from sqlalchemy import func
from core.infra.database import async_session
from models.organization import Organization
from models.people.employee import Employee
from modules.crm.service.pipedrive_service import PipedriveService
import time
import os

class SyncIntelligenceHub:
    """
    Sincroniza dados de Pipedrive, Outlook e WhatsApp para o SQLite local.
    Isso permite buscas instantâneas sem depender de APIs externas em tempo real.
    """
    
    def __init__(self):
        self.pipedrive_svc = PipedriveService()
        self.wa_url = "http://localhost:8001/api/whatsapp/contacts/all?limit=5000&onlyMyContacts=false"
        self.mail_url = "http://localhost:8002/api/email/contacts/all"

    async def wait_for_service(self, url, name, timeout=30):
        """Aguardar até que um serviço esteja online e Retornando 200 OK."""
        start = time.time()
        base_url = url.split("/api/")[0]
        while time.time() - start < timeout:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    # WhatsApp/Email retornam 503 se não estiverem prontos. Queremos 200.
                    resp = await client.get(url) # Tenta o endpoint específico
                    if resp.status_code == 200:
                        return True
            except:
                pass
            await asyncio.sleep(2)
        print(f"[SyncHub] ⚠️ Serviço {name} não está pronto para sincronia (Timeout em {url})")
        return False
        
    async def sync_all(self, force=False):
        """Executa a sincronização global periódica."""
        # Delay inicial — deixa o servidor servir requests antes de rodar sync pesado
        await asyncio.sleep(40)
        
        while True:
            try:
                print("[SyncHub] 🔄 Verificando estado da inteligência local...")
                
                # 1. Pipedrive (Com Cooldown de 1 hora para evitar loop de cota)
                try:
                    current_time = time.time()
                    last_pd_sync = getattr(self, "_last_pd_sync", 0)

                    async with async_session() as session:
                        res = await session.execute(select(func.count()).select_from(Organization))
                        org_count = res.scalar()

                        # Só sincroniza se:
                        # - Forçado OU
                        # - Banco vazio E passou mais de 1 hora desde a última tentativa
                        if force or (org_count < 1 and (current_time - last_pd_sync) > 3600):
                            print("[SyncHub] Sincronizando Pipedrive (Carga inicial)...")
                            await self.pipedrive_svc.sync_all_parallel()
                            self._last_pd_sync = current_time
                        elif org_count < 1:
                            print(f"[SyncHub] Pipedrive vazio, mas aguardando cooldown de cota (Próxima tentativa em {int(3600 - (current_time - last_pd_sync))}s)")

                    # Atualiza cache de open org IDs (usado pelo list_organizations)
                    await self.pipedrive_svc.refresh_open_org_ids_cache()
                except Exception as e:
                    print(f"[SyncHub] ❌ Erro Pipedrive: {e}")
                    
                # 2. WhatsApp
                await self.sync_whatsapp(force=force)
                
                # 3. Outlook
                await self.sync_outlook(force=force)
                
                # Reseta o force após a primeira rodada
                force = False
                
                # Verifica se já temos uma massa crítica de dados para relaxar o loop
                async with async_session() as session:
                    res_wa = await session.execute(select(func.count()).select_from(Employee).where(Employee.source == "whatsapp"))
                    res_mail = await session.execute(select(func.count()).select_from(Employee).where(Employee.source == "outlook"))
                    
                    wa_ok = res_wa.scalar() > 0
                    mail_ok = res_mail.scalar() > 0
                    
                    if wa_ok and mail_ok:
                        interval = 600 # 10 min
                    else:
                        print(f"[SyncHub] Aguardando dados (WA: {wa_ok}, Mail: {mail_ok}). Tentando de novo em 1 min...")
                        interval = 60 # 1 min
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                print(f"[SyncHub] 🔥 Erro no loop de sincronização: {e}")
                await asyncio.sleep(30)

    async def sync_whatsapp(self, force=False):
        """Mapeia contatos do WhatsApp para a tabela de 'Employees' local."""
        try:
            async with async_session() as session:
                res = await session.execute(select(func.count()).select_from(Employee).where(Employee.source == "whatsapp"))
                wa_count = res.scalar()
                if not force and wa_count > 0:
                    print(f"[SyncHub] ✅ WhatsApp já possui {wa_count} contatos indexados.")
                    return

            if not await self.wait_for_service(self.wa_url, "WhatsApp"):
                return

            print("[SyncHub] 📥 Buscando contatos do WhatsApp (Pode demorar devido ao volume)...")
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.get(self.wa_url)
                if resp.status_code == 200:
                    data = resp.json()
                    contacts = data.get('contacts', [])
                    added = 0
                    async with async_session() as session:
                        for c in contacts:
                            if not c.get('id'): continue
                            stmt = select(Employee).where(Employee.whatsapp_number == c['id'])
                            res = await session.execute(stmt)
                            if not res.scalars().first():
                                session.add(Employee(
                                    name=c.get('name', 'Contato WhatsApp'),
                                    whatsapp_number=c['id'],
                                    phone=c.get('number'),
                                    source="whatsapp",
                                    is_discovery=1
                                ))
                                added += 1
                        await session.commit()
                    print(f"[SyncHub] ✅ WhatsApp: {added} novos contatos indexados.")
        except Exception as e:
            print(f"[SyncHub] ❌ Erro WhatsApp: {e}")

    async def sync_outlook(self, force=False):
        """Mapeia contatos do Outlook para a tabela de 'Employees' local."""
        try:
            async with async_session() as session:
                res = await session.execute(select(func.count()).select_from(Employee).where(Employee.source == "outlook"))
                mail_count = res.scalar()
                if not force and mail_count > 0:
                    print(f"[SyncHub] ✅ Outlook já possui {mail_count} contatos indexados.")
                    return

            if not await self.wait_for_service(self.mail_url, "Outlook"):
                return

            print("[SyncHub] 📥 Buscando contatos do Outlook...")
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.get(self.mail_url)
                if resp.status_code == 200:
                    data = resp.json()
                    contacts = data.get('results', [])
                    added = 0
                    async with async_session() as session:
                        for c in contacts:
                            if not c.get('email'): continue
                            stmt = select(Employee).where(Employee.email == c['email'])
                            res = await session.execute(stmt)
                            if not res.scalars().first():
                                session.add(Employee(
                                    name=c.get('name', 'Contato Outlook'),
                                    email=c['email'],
                                    source="outlook",
                                    is_discovery=1
                                ))
                                added += 1
                        await session.commit()
                    print(f"[SyncHub] ✅ Outlook: {added} novos contatos indexados.")
        except Exception as e:
            print(f"[SyncHub] ❌ Erro Outlook: {e}")
