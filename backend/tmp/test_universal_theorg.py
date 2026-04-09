import asyncio
import os
import sys
import httpx
import re
import unicodedata

def simplify_text(text):
    if not text: return ""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

async def test_theorg_direct(target_name, brand):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        t_brand = simplify_text(brand).lower().replace(" ", "-")
        base_name = simplify_text(target_name).lower().replace(".", "").strip()
        name_parts = [p for p in base_name.split() if len(p) > 1 or p.isalpha()]
        
        # Variações de Slug: [nome-completo, nome-sobrenome, nome-primeiro-segundo]
        slugs = [
            "-".join(name_parts),
            f"{name_parts[0]}-{name_parts[-1]}" if len(name_parts) > 1 else name_parts[0],
        ]
        if len(name_parts) > 2:
            slugs.append(f"{name_parts[0]}-{name_parts[1]}")

        print(f"\n[The Org Test] Searching lead: {target_name} | Company: {brand}")
        
        found = False
        for s in list(set(slugs)):
            check_url = f"https://theorg.com/org/{t_brand}/org-chart/{s}"
            print(f"   -> Testing slug: {s}...")
            
            try:
                resp = await client.get(check_url, follow_redirects=True, headers=headers)
                if resp.status_code == 200:
                    print(f"   [OK] Success! Profile found.")
                    
                    # Extração de Cargo Real
                    import html
                    role = "Not identified in meta-tags"
                    # Prioridade 1: og:title
                    title_match = re.search(r'property="og:title" content="[^"-]*-\s*([^|@"]*)\s', resp.text, re.I)
                    if not title_match:
                        # Prioridade 2: tag <title>
                        title_match = re.search(fr"<title>[^<]*{re.escape(name_parts[0])}[^<]*-\s*([^|@<]*)\s+", resp.text, re.I)
                    
                    if title_match:
                        role = title_match.group(1).strip()
                        # Limpeza Profissional
                        role = html.unescape(role)
                        role = re.sub(fr'\s+(at|na|da|in|of|@)\s+.*', '', role, flags=re.IGNORECASE)
                        role = role.strip().title()
                    
                    print(f"   [ROLE] Official Role: {role}")
                    found = True
                    break
                else:
                    print(f"   [-] HTTP {resp.status_code}")
            except Exception as e:
                print(f"   [!] Error: {e}")

        if not found:
            print(f"   [NOT FOUND] Candidate {target_name} not found with tested slugs.")

if __name__ == "__main__":
    # Teste em lote com 10 perfis reais do log
    targets = [
        ("Camila Lomba", "Knorr-Bremse"),
        ("Clisman Luz", "Knorr-Bremse"),
        ("Davy Morais", "Knorr-Bremse"),
        ("Victor Franchescoli Faria", "Knorr-Bremse"),
        ("Gláucia Souza", "Knorr-Bremse"),
        ("Talles Cristian", "Knorr-Bremse"),
        ("Maiara Betim", "Knorr-Bremse"),
        ("Renilton S. Carvalho Carvalho", "Knorr-Bremse"),
        ("Glauber Silva", "Knorr-Bremse"),
        ("Gustavo Okumura", "Knorr-Bremse")
    ]
    
    for name, brand in targets:
        asyncio.run(test_theorg_direct(name, brand))
