import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.infra.database import async_session
from models import Organization
from modules.crm.service.pipedrive_service import PipedriveService
from sqlalchemy import select

async def main():
    service = PipedriveService()
    
    # 1. Search for Rocha Auto Peças to get its Pipedrive ID
    orgs = await service.search_organization("Rocha Auto Peças")
    org_id = None
    for org in orgs:
        if org and "Rocha Auto Peças" in org.get("name", ""):
            org_id = org.get("id")
            break
    
    print(f"Org ID: {org_id}")
    if not org_id:
        print("Organization not found.")
        return

    # 2. Get deals for this org
    resp_deals = await service._request("GET", "deals", params={"org_id": org_id, "limit": 10})
    deal_id = None
    if resp_deals and resp_deals.status_code == 200:
        deals = resp_deals.json().get("data") or []
        for d in deals:
            print(f"Found deal: {d.get('title')} (ID: {d.get('id')})")
            deal_id = d.get("id")
            break
            
    print(f"Deal ID: {deal_id}")

    # 3. Get activities for this org/deal
    params = {"user_id": service.user_id, "done": 0, "limit": 100}
    if org_id:
        params["org_id"] = org_id
        
    resp_act = await service._request("GET", "activities", params=params)
    act_id = None
    if resp_act and resp_act.status_code == 200:
        activities = resp_act.json().get("data") or []
        for act in activities:
            print(f"Found activity: {act.get('subject')} (ID: {act.get('id')})")
            if "contato" in act.get("subject", "").lower():
                act_id = act.get("id")
                break

    print(f"Activity ID to complete: {act_id}")

    # 4. Update the task to done
    if act_id:
        resp_update = await service._request("PUT", f"activities/{act_id}", json={"done": 1})
        if resp_update and resp_update.status_code == 200:
            print(f"Activity {act_id} marked as done.")
        else:
            print(f"Failed to update activity: {resp_update.text if resp_update else 'None'}")
    else:
        print("No 'encontrar contato' activity found.")

    # 5. Add a note
    note_content = """<p><strong>Contatos encontrados:</strong></p>
<ul>
<li><strong>André Roberto Ribeiro</strong> (Especialista em Compras e Cadastro - Suprimentos): Pontuação 95 (A). É o contato ideal devido ao seu cargo e departamento estarem diretamente alinhados com a aquisição de embalagens.</li>
<li><strong>Jederson Rodrigues Thomé</strong> (Comprador - Operations): Pontuação 90 (A). Como comprador, é um alvo primário, e a otimização de embalagens impacta diretamente a eficiência operacional.</li>
<li><strong>Roberto Rocha</strong> (Sócio-Fundador - Operations): Pontuação 70 (B). Como fundador, ele tem uma visão estratégica sobre custos e eficiência, sendo um influenciador chave para decisões de investimento ou mudanças estratégicas.</li>
</ul>
<p><strong>Próximas ações sugeridas:</strong></p>
<ul>
<li>Entrar em contato com André Roberto Ribeiro por e-mail, focando em como a J.Ferres pode otimizar custos e processos de embalagem.</li>
<li>Entrar em contato com Jederson Rodrigues Thomé por e-mail, destacando como as soluções de embalagem podem reduzir danos e otimizar a logística interna.</li>
<li>Considerar um contato com Roberto Rocha para discutir o impacto estratégico das embalagens na rentabilidade e eficiência da empresa.</li>
</ul>"""

    note_payload = {
        "content": note_content,
        "org_id": org_id,
    }
    if deal_id:
        note_payload["deal_id"] = deal_id

    resp_note = await service._request("POST", "notes", json=note_payload)
    if resp_note and resp_note.status_code == 201:
        print("Note successfully added.")
    else:
        print(f"Failed to add note: {resp_note.text if resp_note else 'None'}")

if __name__ == "__main__":
    asyncio.run(main())
