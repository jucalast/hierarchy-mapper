import requests
import os
from dotenv import load_dotenv
from collections import defaultdict
import json

load_dotenv(os.path.join(os.path.dirname(__file__), '../backend/.env'))

PIPEDRIVE_API_TOKEN = os.environ.get('PIPEDRIVE_API_TOKEN')
if PIPEDRIVE_API_TOKEN:
    PIPEDRIVE_API_TOKEN = PIPEDRIVE_API_TOKEN.strip()

BASE_URL = 'https://api.pipedrive.com/v1'

def get_users():
    url = f"{BASE_URL}/users?api_token={PIPEDRIVE_API_TOKEN}"
    response = requests.get(url)
    return response.json()

def get_activities(user_id=None):
    url = f"{BASE_URL}/activities?api_token={PIPEDRIVE_API_TOKEN}&limit=500"
    if user_id:
        url += f"&user_id={user_id}"
    
    activities = []
    start = 0
    while True:
        res = requests.get(url + f"&start={start}")
        data = res.json()
        if not data.get('data'):
            break
        activities.extend(data['data'])
        
        pagination = data.get('additional_data', {}).get('pagination', {})
        if not pagination.get('more_items_in_collection'):
            break
        start = pagination.get('next_start')
        
    return activities

def main():
    users_data = get_users()
    if not users_data.get('success'):
        print("Error fetching users:", users_data)
        return
        
    joao_id = None
    for user in users_data.get('data', []):
        if 'joão' in user['name'].lower() and 'luccas' in user['name'].lower():
            joao_id = user['id']
            break
            
    if not joao_id:
        for user in users_data.get('data', []):
            if 'joão' in user['name'].lower() or 'joao' in user['name'].lower():
                joao_id = user['id']
                break
                
    if not joao_id:
        return
        
    activities = get_activities(joao_id)
    
    grouped_tasks = defaultdict(list)
    for act in activities:
        key = f"{act.get('subject')} (Type: {act.get('type')})"
        grouped_tasks[key].append(act['id'])
        
    # generate markdown
    md_lines = []
    md_lines.append(f"# Tarefas de João Luccas no Pipedrive")
    md_lines.append(f"Total de tarefas encontradas: {len(activities)}")
    md_lines.append(f"Total de tipos de tarefas únicos (agrupados por assunto e tipo): {len(grouped_tasks)}\n")
    
    md_lines.append("## Tarefas Agrupadas\n")
    
    sorted_groups = sorted(grouped_tasks.items(), key=lambda x: len(x[1]), reverse=True)
    
    for key, ids in sorted_groups:
        if len(ids) > 1:
            md_lines.append(f"### {key} - {len(ids)} tarefas")
            formatted_ids = ", ".join(map(str, ids))
            md_lines.append(f"- IDs: {formatted_ids}\n")
            
    md_lines.append("\n## Tarefas Únicas\n")
    for key, ids in sorted_groups:
        if len(ids) == 1:
            md_lines.append(f"- **{key}** (ID: {ids[0]})")
            
    with open('pipedrive_tarefas.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))
        
if __name__ == '__main__':
    main()
