
import asyncio
import os
import sys

# Ajusta o sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from core.config import settings
from modules.crm.service.pipedrive_service import pipedrive_service

async def check_contacts():
    org_id = 1074
    # Usando o método _request que é mais direto ou get_organization_details
    resp = await pipedrive_service._request("GET", f"organizations/{org_id}/persons")
    if resp is None or resp.status_code != 200:
        print(f"Erro ao buscar contatos: {resp.status_code if resp else 'No response'}")
        return

    data = resp.json()
    persons = data.get("data") or []
    if not persons:
        print("Nenhum contato encontrado.")
        return

    for p in persons:
        name = p.get("name")
        emails = p.get("email")
        phones = p.get("phone")
        print(f"Nome: {name}")
        print(f"Emails: {emails}")
        print(f"Phones: {phones}")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(check_contacts())
