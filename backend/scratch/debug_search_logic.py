from services.communication.email_client import EmailClient
import pythoncom

def debug_search():
    try:
        pythoncom.CoInitialize()
        client = EmailClient(use_outlook_app=True)
        
        print("\n--- INICIANDO DEPURAÇÃO DE BUSCA ---")
        query = "joao"
        print(f"Termo de busca: '{query}'")
        
        results = client.search_contacts(query)
        
        if results:
            print(f"\nSucesso! Encontramos {len(results)} resultados:")
            for r in results:
                print(f" - {r['name']} ({r['email']}) [Fonte: {r['source']}]")
        else:
            print("\nNenhum resultado encontrado. Vamos verificar o porquê...")
            
    except Exception as e:
        print(f"Erro na depuração: {e}")

if __name__ == "__main__":
    debug_search()
