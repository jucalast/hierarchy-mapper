
import win32com.client
import pythoncom

def map_deep_folders():
    pythoncom.CoInitialize()
    print("--- MAPEAMENTO PROFUNDO DE PASTAS (JOAO.MOURA) ---")
    try:
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        target_account = None
        for store in outlook.Stores:
            if "joao.moura" in store.DisplayName.lower():
                target_account = store
                break
        
        if not target_account:
            print("Conta joao.moura não encontrada. Usando Store padrão.")
            target_account = outlook.DefaultStore

        root = target_account.GetRootFolder()
        
        def walk_folders(folder, indent=0):
            try:
                # Filtrar apenas pastas de e-mail (DefaultItemType 0)
                if folder.DefaultItemType == 0:
                    print("  " * indent + f"|-- {folder.Name} ({folder.Items.Count} msgs)")
                
                for sub in folder.Folders:
                    walk_folders(sub, indent + 1)
            except: pass

        walk_folders(root)

    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    map_deep_folders()
