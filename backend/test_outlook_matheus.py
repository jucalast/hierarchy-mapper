import win32com.client
import unicodedata

def normalize(s):
    if not s: return ""
    return "".join(c for c in unicodedata.normalize('NFD', s.lower()) if unicodedata.category(c) != 'Mn').strip()

outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
inbox = outlook.GetDefaultFolder(6) # Inbox
sent = outlook.GetDefaultFolder(5) # Sent items

query = "matheus"

print("--- INBOX ---")
items = inbox.Items
items.Sort("[ReceivedTime]", True)
for i in range(1, min(500, items.Count) + 1):
    try:
        msg = items.Item(i)
        to_str = getattr(msg, 'To', '')
        s_email = getattr(msg, 'SenderEmailAddress', '')
        s_name = getattr(msg, 'SenderName', '')
        sub = getattr(msg, 'Subject', '')
        
        if query in normalize(s_email) or query in normalize(s_name) or query in normalize(to_str) or query in normalize(sub):
            print(f"- [INBOX] From: {s_name} ({s_email}) To: {to_str} | Sub: {sub}")
    except:
        pass

print("--- SENT ---")
items = sent.Items
items.Sort("[ReceivedTime]", True)
for i in range(1, min(500, items.Count) + 1):
    try:
        msg = items.Item(i)
        to_str = getattr(msg, 'To', '')
        s_email = getattr(msg, 'SenderEmailAddress', '')
        s_name = getattr(msg, 'SenderName', '')
        sub = getattr(msg, 'Subject', '')
        
        if query in normalize(s_email) or query in normalize(s_name) or query in normalize(to_str) or query in normalize(sub):
            print(f"- [SENT] From: {s_name} ({s_email}) To: {to_str} | Sub: {sub}")
    except:
        pass
