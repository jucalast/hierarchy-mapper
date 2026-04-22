
import win32com.client
import pythoncom

def map_outlook_stores():
    pythoncom.CoInitialize()
    print("--- RELATÓRIO DE CONTAS E PASTAS DO OUTLOOK ---")
    try:
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        
        print(f"Total de Contas (Accounts): {outlook.Accounts.Count}")
        for i in range(1, outlook.Accounts.Count + 1):
            acc = outlook.Accounts.Item(i)
            print(f"   [CONTA {i}] Nome: {acc.DisplayName} | Smtp: {getattr(acc, 'SmtpAddress', 'N/A')}")

        print(f"\nTotal de Lojas (Stores): {outlook.Stores.Count}")
        for i in range(1, outlook.Stores.Count + 1):
            store = outlook.Stores.Item(i)
            print(f"   [LOJA {i}] Nome: {store.DisplayName}")
            try:
                root = store.GetRootFolder()
                # Tenta achar o Inbox dessa loja
                for folder in root.Folders:
                    try:
                        # olFolderInbox = 6
                        if folder.DefaultItemType == 0: # MailItem
                            print(f"      - Pasta: {folder.Name} (Mensagens: {folder.Items.Count})")
                    except: pass
            except Exception as e:
                print(f"      - Erro ao acessar pastas desta loja: {e}")

        # Verifica pra onde a pasta PADRAO aponta
        try:
            default_inbox = outlook.GetDefaultFolder(6)
            print(f"\n[AVISO] A Pasta Inbox Padrão (6) é: {default_inbox.Parent.Name} -> {default_inbox.Name} (Mensagens: {default_inbox.Items.Count})")
        except:
            print("\n[ERRO] Não foi possível acessar a pasta padrão (6).")

    except Exception as e:
        print(f"ERRO CRITICO AO MAPEAR: {e}")

if __name__ == "__main__":
    map_outlook_stores()
