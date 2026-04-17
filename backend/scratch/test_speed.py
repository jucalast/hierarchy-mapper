from services.communication.email_client import EmailClient
import pythoncom
import time

def test_cache_speed():
    try:
        pythoncom.CoInitialize()
        client = EmailClient(use_outlook_app=True)
        
        print("\n--- TESTE DE VELOCIDADE DE CACHE ---")
        
        # 1. Primeira busca (Constrói o Cache)
        print("1a Busca (Construindo Cache)...")
        start = time.time()
        res1 = client.search_contacts("joao")
        print(f"Tempo 1a busca: {time.time() - start:.2f}s")
        
        # 2. Segunda busca (Usa o Cache)
        print("2a Busca (Usando Cache)...")
        start = time.time()
        res2 = client.search_contacts("joao")
        print(f"Tempo 2a busca: {time.time() - start:.4f}s")
        
        if res2:
            print(f"\nResultados encontrados para 'joao': {len(res2)}")
            for r in res2[:3]:
                print(f" - {r['name']} ({r['email']})")
        else:
            print("\nNenhum 'joao' encontrado, tentando 'bruna'...")
            res3 = client.search_contacts("bruna")
            for r in res3[:3]:
                print(f" - {r['name']} ({r['email']})")

    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    test_cache_speed()
