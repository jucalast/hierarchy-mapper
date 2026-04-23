
with open(r'c:\Users\João Luccas\Desktop\LINKB2B\hierarchy-mapper\backend\services\ai\data_fetcher.py', 'rb') as f:
    content = f.read()

# Procura o início da função corrompida
search_str = b'def sanitize_email_body'
idx = content.rfind(search_str)

if idx != -1:
    new_content = content[:idx] + b"""def sanitize_email_body(body: str) -> str:
    if not body:
        return ""
    import re
    clean = re.sub(r"<[^>]+>", " ", body)
    clean = re.sub(r"\\s+", " ", clean)
    return clean.strip()[:2000]
"""
    with open(r'c:\Users\João Luccas\Desktop\LINKB2B\hierarchy-mapper\backend\services\ai\data_fetcher.py', 'wb') as f:
        f.write(new_content)
    print("File repaired successfully.")
else:
    print("Could not find function to repair.")
