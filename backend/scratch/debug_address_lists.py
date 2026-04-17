import win32com.client

def debug_address_lists():
    try:
        outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        print("--- Address Lists ---")
        for addr_list in outlook.AddressLists:
            print(f"Name: {addr_list.Name} (Count: {addr_list.AddressEntries.Count})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_address_lists()
