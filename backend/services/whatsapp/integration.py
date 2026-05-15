"""
WhatsApp Integration - Conecta ao WhatsApp Service (Node.js porta 8001)
Enriquece dados de contatos com status do WhatsApp
"""

import httpx
import logging
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

WHATSAPP_SERVICE_URL = "http://localhost:8001/api/whatsapp"
TIMEOUT = 5.0  # segundos


class WhatsAppIntegration:
    """Integração com WhatsApp Service para enriquecimento de contatos."""
    
    @staticmethod
    async def _get_service_url() -> str:
        """Carrega dinamicamente a URL do WhatsApp Service a partir do banco de dados (SaaS)."""
        try:
            from services.ai.business_context_service import BusinessContextService
            from core.config import settings
            t_id = await BusinessContextService.get_first_tenant_id()
            if t_id:
                creds = await BusinessContextService.get_integration_credentials(t_id, "whatsapp")
                if creds and creds.get("service_url"):
                    return creds["service_url"]
            return getattr(settings, "WHATSAPP_SERVICE_URL", "http://localhost:8001/api/whatsapp")
        except Exception:
            return "http://localhost:8001/api/whatsapp"

    @staticmethod
    async def get_contact_status(phone_number: str) -> Optional[Dict]:
        """
        Busca status de um contato no WhatsApp.
        
        Args:
            phone_number: Número de telefone (com ou sem @c.us)
        
        Returns:
            Dict com dados do contato ou None se não encontrado
        """
        if not phone_number or not phone_number.strip():
            return None
        
        # Limpar número: remover caracteres especiais
        clean_number = phone_number.replace("+", "").replace("-", "").replace(" ", "").replace("@c.us", "")
        
        try:
            service_url = await WhatsAppIntegration._get_service_url()
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                # Tentar buscar pelo número no WhatsApp Service
                url = f"{service_url}/contacts/by-number/{clean_number}"
                response = await client.get(url)
                
                if response.status_code == 200:
                    contact_data = response.json()
                    contact_data["status"] = "found"
                    return contact_data
                elif response.status_code == 404:
                    # Número não encontrado no WhatsApp
                    return {
                        "number": clean_number,
                        "status": "not_found",
                        "message": "Número não identificado no WhatsApp"
                    }
                else:
                    logger.warning(f"WhatsApp Service returned {response.status_code} for {clean_number}")
                    return {
                        "number": clean_number,
                        "status": "error",
                        "message": f"WhatsApp Service error: {response.status_code}"
                    }
                    
        except httpx.TimeoutException:
            logger.error(f"Timeout ao contactar WhatsApp Service para {clean_number}")
            return {
                "number": clean_number,
                "status": "timeout",
                "message": "WhatsApp Service indisponível (timeout)"
            }
        except Exception as e:
            logger.error(f"Erro ao consultar WhatsApp Service: {str(e)}")
            return {
                "number": clean_number,
                "status": "error",
                "message": f"Erro: {str(e)}"
            }
    
    @staticmethod
    async def search_contact_by_name(name: str, min_similarity: float = 0.7) -> Optional[List[Dict]]:
        """
        Busca contatos por nome com busca fuzzy.
        
        Args:
            name: Nome para buscar
            min_similarity: Limiar de similaridade (0-1)
        
        Returns:
            Lista de contatos encontrados
        """
        if not name or not name.strip():
            return []
        
        try:
            service_url = await WhatsAppIntegration._get_service_url()
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                url = f"{service_url}/contacts/search"
                params = {
                    "name": name,
                    "minSimilarity": min_similarity,
                    "limit": 10
                }
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("contacts", [])
                else:
                    logger.warning(f"WhatsApp search failed: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Erro ao buscar contatos por nome: {str(e)}")
            return []
    
    @staticmethod
    async def enrich_employee_with_whatsapp(employee_data: Dict) -> Dict:
        """
        Enriquece dados de funcionário com informações do WhatsApp.
        
        Args:
            employee_data: Dict com dados do employee (name, email, phone, role, dept)
        
        Returns:
            Mesmo dict com campos adicionados:
            - whatsapp_status: "found", "not_found", "error", "timeout"
            - whatsapp_active: bool se status == "found"
            - whatsapp_data: dict com dados completos se encontrado
        """
        result = employee_data.copy()
        result["whatsapp_status"] = "unknown"
        result["whatsapp_active"] = False
        result["whatsapp_data"] = None
        
        # Se não tem telefone, não pode enriquecer
        if not employee_data.get("email") and not employee_data.get("phone"):
            return result
        
        # Prioridade: email com WhatsApp Business > phone
        search_value = employee_data.get("phone") or employee_data.get("email")
        
        if not search_value:
            return result
        
        # Buscar no WhatsApp
        whatsapp_result = await WhatsAppIntegration.get_contact_status(search_value)
        
        if whatsapp_result:
            result["whatsapp_status"] = whatsapp_result.get("status", "unknown")
            result["whatsapp_active"] = whatsapp_result.get("status") == "found"
            result["whatsapp_data"] = whatsapp_result
        
        return result
    
    @staticmethod
    async def enrich_employees_batch(employees: List[Dict]) -> List[Dict]:
        """
        Enriquece múltiplos empregados com dados do WhatsApp (paralelo).
        
        Args:
            employees: Lista de dicts com dados de employees
        
        Returns:
            Lista com mesmos employees + dados WhatsApp
        """
        if not employees:
            return []
        
        import asyncio
        
        try:
            # Executar enriquecimento em paralelo com limite de 10 simultâneas
            tasks = [WhatsAppIntegration.enrich_employee_with_whatsapp(emp) for emp in employees]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            return results
        except Exception as e:
            logger.error(f"Erro ao enriquecer batch: {str(e)}")
            return employees


    @staticmethod
    async def send_message(chat_id: str, message: str) -> Dict:
        """
        Envia uma mensagem de WhatsApp para um ID ou número.
        Suporta: 55... @c.us, ID@lid, ou número puro.
        """
        if not chat_id or not message:
            return {"ok": False, "error": "Faltam dados de destino ou mensagem."}
            
        # Limpeza e Normalização do ID
        target_jid = chat_id
        if not "@" in target_jid:
            # LIDs (Linked IDs) do Baileys/Multidevice costumam ter 15+ dígitos
            # Números brasileiros com o 9 extra têm 13 dígitos (ex: 5511999998888)
            if target_jid.isdigit() and len(target_jid) >= 15:
                target_jid = f"{target_jid}@lid"
            elif target_jid.isdigit():
                target_jid = f"{target_jid}@c.us"

        try:
            service_url = await WhatsAppIntegration._get_service_url()
            async with httpx.AsyncClient(timeout=TIMEOUT * 3) as client:
                url = f"{service_url}/send"

                # Para contatos LID (ID interno >13 dígitos), o bridge pode rejeitar
                # o campo 'number' (que espera um telefone real). Tenta chatId-only primeiro,
                # pois alguns bridges roteiam via chatId sem validar o número.
                cid_num = target_jid.split("@")[0] if "@" in target_jid else target_jid
                is_lid = cid_num.isdigit() and len(cid_num) > 13

                if is_lid:
                    # Tentativa 1: chatId-only (sem number) com @c.us
                    jid_cus = f"{cid_num}@c.us"
                    for try_payload in [
                        {"chatId": jid_cus, "message": message},
                        {"chatId": target_jid, "message": message},
                        {"to": jid_cus, "message": message},
                    ]:
                        try:
                            r = await client.post(url, json=try_payload)
                            if r.status_code == 200:
                                return {"ok": True, "result": r.json()}
                        except Exception:
                            pass

                # Tentativa padrão: number + chatId
                payload = {"number": target_jid, "chatId": target_jid, "message": message}
                response = await client.post(url, json=payload)

                if response.status_code == 200:
                    return {"ok": True, "result": response.json()}
                else:
                    err_msg = response.json().get("error") or response.text or f"Erro {response.status_code}"
                    return {"ok": False, "error": err_msg}
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem WhatsApp: {str(e)}")
            return {"ok": False, "error": str(e)}


# Test/Demo
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test 1: Buscar por número
        print("Test 1: Buscar por número")
        result = await WhatsAppIntegration.get_contact_status("5511987654321")
        print(f"Result: {result}\n")
        
        # Test 2: Buscar por nome
        print("Test 2: Buscar por nome")
        results = await WhatsAppIntegration.search_contact_by_name("João")
        print(f"Results: {results}\n")
        
        # Test 3: Enriquecer employee
        print("Test 3: Enriquecer employee")
        emp = {"name": "João Silva", "phone": "5511987654321", "role": "Gerente"}
        enriched = await WhatsAppIntegration.enrich_employee_with_whatsapp(emp)
        print(f"Enriched: {enriched}\n")
    
    asyncio.run(test())
