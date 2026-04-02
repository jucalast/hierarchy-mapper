import httpx
from typing import List, Dict, Any, Optional
import os
from dotenv import load_dotenv

load_dotenv()

class PipedriveService:
    def __init__(self):
        self.api_token = os.getenv("PIPEDRIVE_API_TOKEN")
        self.user_id = 24921888 # ID João Luccas
        self.base_url = "https://api.pipedrive.com/v1"

    async def update_organization(self, org_id: int, data: dict):
        """Atualiza Endereço, CNPJ e Domínio no Pipedrive (Assíncrono)."""
        url = f"{self.base_url}/organizations/{org_id}?api_token={self.api_token}"
        
        # Mapeamento do que é enviado
        payload = {
            "address": data.get("address"),
            # Se você usar campos customizados, adicione a chave aqui
        }
        
        print(f"[Pipedrive] 📝 Sincronizando Org #{org_id} com IA...")
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.put(url, json=payload)
                return resp.status_code == 200
        except Exception as e:
            print(f"[Pipedrive] Error update: {e}")
            return False

    async def list_organizations(self):
        """Lista empresas filtradas para João Luccas (Assíncrono)."""
        url = f"{self.base_url}/organizations?user_id={self.user_id}&start=0&limit=500&api_token={self.api_token}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                data = resp.json()
                if not data.get("success"): return []
                
                all_orgs = data.get("data") or []
                filtered = []
                for org in all_orgs:
                    if int(org.get("owner_id", {}).get("id", 0)) != self.user_id:
                        continue
                    
                    open_deals = int(org.get("open_deals_count", 0))
                    lost_deals = int(org.get("lost_deals_count", 0))
                    
                    if open_deals > 0 or (lost_deals == 0):
                        filtered.append(org)
                
                return filtered
        except: return []

    async def sync_overdue_activities(self):
        """Implementação básica para evitar erro de atributo no router."""
        print("[Pipedrive] ⏳ Sincronização de tarefas não implementada nesta versão legada.")
        return {"status": "skipped"}

# Singleton
pipedrive_service = PipedriveService()
