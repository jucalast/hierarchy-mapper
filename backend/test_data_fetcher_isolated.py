import asyncio
import httpx
import sys

async def test_end_to_end():
    print("Iniciando Teste End-to-End para Email e Pipedrive Context Isolation...")
    
    # 1. Testar se o endpoint de Email agora filtra corretamente pelo Q
    email = "Matheus.Muniz@knorr-bremse.com"
    email_url = f"http://127.0.0.1:8002/api/email/messages?folder=Inbox&limit=10&q={email}"
    print(f"\n[Test 1] Buscando Emails para {email} via {email_url}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(email_url)
            if resp.status_code == 200:
                data = resp.json()
                messages = data.get("messages", [])
                print(f"Status: OK. Found {len(messages)} messages.")
                for m in messages:
                    print(f" - [{m.get('date')}] From: {m.get('sender')} | Subject: {m.get('subject')}")
                    # Validating if it actually matches
                    s_lower = m.get('sender', '').lower()
                    if email.lower() not in s_lower:
                        print("   --> ⚠️ AVISO: Mensagem não parece ser do Matheus!")
            else:
                print(f"FAILED: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Erro ao testar Email: {e}")

    # 2. Testar Pipeline com ContextFetcher fake ou simular a função localmente
    print("\n[Test 2] Testando Filtro de Negócios no Pipedrive...")
    try:
        from core.database import async_session
        from services.ai.data_fetcher import fetch_contextual_data
        
        intent_info = {
            "query_type": "agent_workflow",
            "data_scope": ["employees", "deals", "activities", "emails"]
        }
        
        selected_entities = [
            {
                "id": 10,
                "name": "Knorr Bremse",
                "type": "organization"
            },
            {
                "id": "Matheus.Muniz@knorr-bremse.com",
                "name": "Muniz, Matheus",
                "type": "email",
                "value": "Matheus.Muniz@knorr-bremse.com"
            }
        ]
        
        async with async_session() as session:
            # ID da organização Knorr Bremse localmente (pode ser 10, como na UI)
            org_id = 10 
            message = "analise a empresa @Knorr Bremse e as conversas com @Muniz, Matheus e fomente as tarefas do pipedrive com as atualizações"
            
            context = await fetch_contextual_data(
                intent_info=intent_info,
                org_id=org_id,
                message=message,
                session=session,
                selected_entities=selected_entities
            )
            
            # Validação Pipedrive
            pd_details = context.get("pipedrive_details", {})
            activities = pd_details.get("activities", [])
            print(f" Atividades carregadas: {len(activities)}")
            
            # Verificar deal_id das atividades
            # Tem que pertencer aos "deals" (no caso, abertos pelo usuário)
            user_deals = [d['id'] for d in pd_details.get('deals', [])]
            print(f" User Deals (Open/Recents): {user_deals}")
            
            anomalies = []
            for act in activities:
                # Na service, limitamos ao primary_deal_id, mas se vier a activity 7870 (que é do João Luccas)
                # Ela será exibida. Vamos ver se tem alguma tarefa sem deal ou de outro deal
                d_id = act.get('deal_id')
                print(f"  - Atividade {act['id']}: '{act.get('subject')}' | Deal: {d_id}")
                if d_id and d_id not in user_deals:
                    anomalies.append(act['id'])
            
            if anomalies:
                print(f" ❌ Falha: Encontramos atividades de outros negócios: {anomalies}")
            else:
                print(f" ✅ Pipedrive Activities filtradas corretamente (Apenas Negócios do Usuário: {user_deals})")

            # Validação Email (Do Data Fetcher)
            email_result = context.get('email_result', {}).get('resultado', {}).get('messages_by_contact', [])
            print(f"\n Emails recuperados pelo Pipeline: {len(email_result)} contatos avaliados.")
            for er in email_result:
                print(f" Contact: {er.get('contact', '')} ({er.get('email', '')})")
                print(f" Human threads: {len(er.get('human_threads', []))}")
                for ht in er.get('human_threads', []):
                    print(f"   -> {ht.get('sender')} - {ht.get('subject')}")
                    
    except Exception as e:
        print(f"Erro ao testar Context Fetcher: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_end_to_end())
