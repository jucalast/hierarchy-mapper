import asyncio
import sys
import os
from datetime import date, timedelta

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
        
    print(f'Encontrados {len(deals)} deals. Iniciando processamento...')
    
    count_updated = 0
    for d in deals:
        deal_id = d.get('id')
        title = d.get('title')
        org_id = d.get('org_id')
        if isinstance(org_id, dict):
            org_id = org_id.get('value')
            
        act_resp = await service.make_request('GET', f'deals/{deal_id}/activities')
        if not act_resp or act_resp.status_code != 200:
            continue
            
        acts = act_resp.json().get('data') or []
        
        target_act = None
        for a in acts:
            subject_lower = a.get('subject', '').lower()
            if 'contato' in subject_lower and any(v in subject_lower for v in ['encontrar', 'conseguir', 'achar', 'buscar', 'pesquisar']):
                target_act = a
                break
                
        if target_act:
            count_updated += 1
            print(f"Processando Deal ID {deal_id} ({title})...")
            
            # 1. Marcar a tarefa encontrada como concluida (se já não estiver)
            if not target_act.get('done'):
                await service.update_activity(target_act.get('id'), {"done": 1})
                print(f"  -> Tarefa original '{target_act.get('subject')}' marcada como concluída.")
            else:
                print(f"  -> Tarefa original '{target_act.get('subject')}' já estava concluída.")
            
            # Verifica se as tarefas que vamos criar já existem para evitar duplicidade
            has_apresentacao = any('enviar apresentação' in a.get('subject', '').lower() for a in acts)
            has_reuniao = any('marcar reunião' in a.get('subject', '').lower() for a in acts)

            today_str = date.today().isoformat()
            tomorrow_str = (date.today() + timedelta(days=1)).isoformat()

            # 2. Criar tarefa realizada "Enviar apresentacao"
            if not has_apresentacao:
                payload_presentation = {
                    "subject": "Enviar apresentação",
                    "done": 1,
                    "deal_id": deal_id,
                    "org_id": org_id,
                    "type": "task",
                    "due_date": today_str
                }
                await service.make_request("POST", "activities", json=payload_presentation)
                print("  -> Tarefa 'Enviar apresentação' criada (concluída).")
            else:
                print("  -> Tarefa 'Enviar apresentação' já existia neste negócio.")
                
            # 3. Criar proxima tarefa pendente "Marcar reunião"
            if not has_reuniao:
                payload_meeting = {
                    "subject": "Marcar reunião",
                    "done": 0,
                    "deal_id": deal_id,
                    "org_id": org_id,
                    "type": "task",
                    "due_date": tomorrow_str
                }
                await service.make_request("POST", "activities", json=payload_meeting)
                print("  -> Tarefa 'Marcar reunião' criada (pendente para amanhã).")
            else:
                print("  -> Tarefa 'Marcar reunião' já existia neste negócio.")
                
            print("---")
            
    print(f"Finalizado! {count_updated} negócios foram atualizados.")

if __name__ == '__main__':
    asyncio.run(main())
