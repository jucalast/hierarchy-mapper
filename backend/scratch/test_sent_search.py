import win32com.client
import pythoncom
import unicodedata

def normalize(s):
    if not s: return ""
    return "".join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn').strip()

def test_sent_items_search(query=""):
    try:
        pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        
        # 5 = olFolderSentMail
        sent_folder = outlook.GetDefaultFolder(5)
        print(f"\n--- BUSCANDO NOS ÚLTIMOS ITENS ENVIADOS ({sent_folder.Items.Count} total) ---")
        
        items = sent_folder.Items
        items.Sort("[ReceivedTime]", True) # Mais recentes primeiro
        
        clean_query = normalize(query)
        found_recipients = {}
        
        # Analisa os últimos 50 e-mails enviados
        max_scan = min(50, items.Count)
        print(f"Escaneando os últimos {max_scan} envios...")
        
        for i in range(1, max_scan + 1):
            try:
                msg = items.Item(i)
                # O destinatário pode ser múltiplo
                for recipient in msg.Recipients:
                    name = recipient.Name
                    email = ""
                    try:
                        # Tenta pegar o endereço SMTP
                        if recipient.Type == 1 or True: # olTo
                            addr_entry = recipient.AddressEntry
                            if addr_entry.Type == "SMTP":
                                email = addr_entry.Address
                            else:
                                eu = addr_entry.GetExchangeUser()
                                if eu: email = eu.PrimarySmtpAddress
                                else: email = addr_entry.Address
                    except:
                        email = recipient.Address
                    
                    if name and email and email not in found_recipients:
                        if not query or clean_query in normalize(name) or clean_query in normalize(email):
                            found_recipients[email] = name
            except:
                continue
        
        if found_recipients:
            print(f"\nEncontramos {len(found_recipients)} contatos únicos em envios recentes:")
            for email, name in found_recipients.items():
                print(f" - {name} <{email}>")
        else:
            print("Nenhum contato encontrado nos envios recentes.")
            
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    # Primeiro listamos alguns pra ver se funciona
    test_sent_items_search()
