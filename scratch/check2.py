import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from modules.crm.service.pipedrive_service import PipedriveService

async def main():
    service = PipedriveService()
    
    print('Buscando negocios no bucket Reunião Realizada (stage_id=26)...')
    deals_resp = await service.make_request('GET', 'deals?stage_id=26&limit=500&status=open')
    if not deals_resp or deals_resp.status_code != 200:
        print('Erro ao buscar deals')
        return
        
    deals = deals_resp.json().get('data', [])
    if not deals:
        print('Nenhum deal em Reunião Realizada.')
        return
        
    print(f'Encontrados {len(deals)} deals. Filtrando por tarefa Ciesp...')
    
    match_count = 0
    for d in deals:
        deal_id = d.get('id')
        title = d.get('title')
        org_name = d.get('org_name', 'Sem empresa')
        
        act_resp = await service.make_request('GET', f'deals/{deal_id}/activities')
        if not act_resp or act_resp.status_code != 200:
            continue
            
        acts = act_resp.json().get('data') or []
        for a in acts:
            subject_lower = a.get('subject', '').lower()
            # Palavras-chave: encontrar contato, conseguir contato, achar contato, buscar contato, contato
            if 'contato' in subject_lower and any(verb in subject_lower for verb in ['encontrar', 'conseguir', 'achar', 'buscar', 'pesquisar']):
                match_count += 1
                status = "Concluida" if a.get("done") else "Pendente"
                print(f'- Deal ID: {deal_id} | Empresa: {org_name} | Titulo: {title} | Status Tarefa: {status}')
                break
                
    if match_count == 0:
        print('Nenhum negocio com a tarefa Ciesp foi encontrado.')

if __name__ == '__main__':
    asyncio.run(main())
