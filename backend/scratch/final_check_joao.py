from services.communication.email_client import EmailClient
import pythoncom
import time

def test_find_joao():
    try:
        pythoncom.CoInitialize()
        client = EmailClient(use_outlook_app=True)
        
        print("\n--- TESTE DE BUSCA REAL: JOAO ---")
        
        # Forçamos a busca que preenche o cache
        start_time = time.time()
        results = client.search_contacts("joao")
        end_time = time.time()
        
        print(f"Tempo de resposta: {end_time - start_time:.2f}s")
        print(f"Total de contatos no cache: {len(client._contacts_cache)}")
        
        if results:
            print(f"\n✅ SUCESSO! Encontrados {len(results)} contatos:")
            for r in results:
                print(f" - {r['name']} ({r['email']}) [Fonte: {r['source']}]")
        else:
            print("\n❌ FALHA: Nenhum contato com 'joao' encontrado no cache.")
            print("\nMostrando os 10 primeiros nomes do cache para conferir o que foi lido:")
            for i, c in enumerate(client._contacts_cache[:10]):
                print(f" {i+1}. {c['name']} (E-mail: {c['email']})")

    except Exception as e:
        print(f"Erro no teste: {e}")

if __name__ == "__main__":
    test_find_joao()
