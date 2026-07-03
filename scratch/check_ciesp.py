import asyncio
import os
import sys

# Adiciona o diretório backend ao sys.path para importar os módulos
sys.path.insert(0, os.path.abspath("backend"))

from modules.crm.service.pipedrive_service import PipedriveService

async def main():
    service = PipedriveService()
    
    print("Buscando negócios no bucket 'Reunião Agendada' (stage_id = 4)...")
    deals_resp = await service.make_request("GET", "deals?stage_id=4&limit=500&status=open")
    if not deals_resp or deals_resp.status_code != 200:
        print("Erro ao buscar deals")
        return
        
    deals = deals_resp.json().get("data", [])
    if not deals:
        print("Nenhum deal em Reunião Agendada.")
        return
        
    print(f"Encontrados {len(deals)} deals abertos no bucket 'Reunião Agendada'.")
    print("Filtrando aqueles com a tarefa 'Conseguir contato na rodada de negócios Ciesp'...")
    
    match_count = 0
    for d in deals:
        deal_id = d.get("id")
        title = d.get("title")
        org_name = d.get("org_name", "Sem empresa")
        
        # busca activities do deal
        act_resp = await service.make_request("GET", f"deals/{deal_id}/activities")
        if not act_resp or act_resp.status_code != 200:
            continue
            
        acts = act_resp.json().get("data")
        if not acts:
            continue
            
        has_ciesp = False
        for a in acts:
            if a.get("subject") and "Ciesp" in a.get("subject", "") and "rodada de" in a.get("subject", ""):
                has_ciesp = True
                break
                
        if has_ciesp:
            match_count += 1
            print(f"- Deal ID: {deal_id} | Empresa: {org_name} | Título: {title}")
            
    if match_count == 0:
        print("Nenhum negócio com a tarefa específica foi encontrado.")
        
if __name__ == "__main__":
    asyncio.run(main())
