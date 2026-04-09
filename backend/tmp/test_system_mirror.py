import asyncio
import httpx
import re
import html
import unicodedata

def simplify_text(text: str) -> str:
    if not text: return ""
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

async def test_system_theorg_logic(name: str, temp_brand: str):
    print(f"\n[MIRROR TEST] Candidate: {name} | Brand: {temp_brand}")
    
    theorg_info = ""
    theorg_role = "Não Encontrado"
    theorg_url = "N/A"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
            }
            
            t_brand = simplify_text(temp_brand).lower().replace(" ", "-")
            base_name = simplify_text(name).lower().replace(".", "").strip()
            name_parts = [p for p in base_name.split() if len(p) > 1 or p.isalpha()]
            
            if not name_parts:
                print("[-] Name too short or invalid")
                return

            # Variações: [nome-completo, nome-sobrenome, nome-primeiro-segundo]
            slugs = [
                "-".join(name_parts),
                f"{name_parts[0]}-{name_parts[-1]}" if len(name_parts) > 1 else name_parts[0],
            ]
            if len(name_parts) > 2:
                slugs.append(f"{name_parts[0]}-{name_parts[1]}")
            
            for s in list(set(slugs)):
                check_url = f"https://theorg.com/org/{t_brand}/org-chart/{s}"
                print(f"  -> Tentando slug: {s}...")
                
                try:
                    resp = await client.get(check_url, follow_redirects=True, timeout=5.0, headers=headers)
                    final_url = str(resp.url).lower()
                    
                    # SEGURANÇA MÁXIMA (Espelho do b2b_scanner.py)
                    candidate_first_name = name_parts[0].lower()
                    page_title_match = re.search(r'<title>(.*?)</title>', resp.text, re.I | re.S)
                    page_title = page_title_match.group(1).lower() if page_title_match else ""
                    final_slug = final_url.split('/')[-1]
                    
                    print(f"     [DEBUG] URL Final: {final_url}")
                    print(f"     [DEBUG] Title Tag: {page_title[:100]}...")

                    if resp.status_code == 200 and (candidate_first_name in final_slug) and (candidate_first_name in page_title):
                        theorg_url = str(resp.url)
                        theorg_info = f" [HIERARCHY CONFIRMED]: Profile officially listed on The Org"
                        
                        # Extração de Cargo (Espelho do b2b_scanner.py)
                        clean_name_esc = re.escape(name)
                        title_match = re.search(fr"content=\"{clean_name_esc}\s*-\s*([^|\"]+)\"", resp.text, re.I)
                        
                        if not title_match:
                            # Tenta com o primeiro nome do name_parts caso o original tenha acento/ponto
                            clean_name_esc_simple = re.escape(name_parts[0])
                            title_match = re.search(fr"content=\"{clean_name_esc_simple}[^\"-]*-\s*([^|\"]+)\"", resp.text, re.I)

                        if not title_match:
                            title_match = re.search(fr"<title>{re.escape(name_parts[0])}[^<]*-\s*([^|<]*)\s*\|", resp.text, re.I)
                        
                        if page_title:
                            # LÓGICA ROBUSTA: Pegamos o título e limpamos o Nome e a Empresa
                            # Ex: "Victor F. Faria - Comprador - Knorr-Bremse | The Org"
                            clean_role = page_title.split("|")[0].strip() # Remove "| The Org"
                            
                            # Remove o nome do candidato (case insensitive)
                            clean_role = re.sub(re.escape(name.lower()), "", clean_role, flags=re.I).strip()
                            # Remove partes óbvias do nome da empresa
                            for part in temp_brand.split("-") + [temp_brand]:
                                if len(part) > 2:
                                    clean_role = re.sub(re.escape(part.lower()), "", clean_role, flags=re.I).strip()
                            
                            # Remove traços e "at" que sobraram
                            clean_role = re.sub(r'^\s*[-—]\s*', '', clean_role)
                            clean_role = re.sub(r'\bat\b', '', clean_role, flags=re.I).strip()
                            clean_role = clean_role.strip(" -—|")
                            
                            if not clean_role or len(clean_role) < 3 or clean_role.lower() in temp_brand.lower():
                                theorg_role = "Confirmed Profile"
                            else:
                                theorg_role = clean_role.title()
                            
                            print(f"     [DEBUG] Cargo Limpo Final: {theorg_role}")
                        else:
                            theorg_role = "Confirmed Profile"
                        
                        print(f"  [MATCH!] Cargo Final: {theorg_role}")
                        print(f"  [MATCH!] URL Final: {theorg_url}")
                        break
                    else:
                        print(f"  [-] Falha na validação de identidade (Slug ou Title mismatch)")
                except Exception as e:
                    print(f"  [-] Erro na requisição: {e}")
                    continue

    except Exception as e:
        print(f"[ERROR] Outer exception: {e}")

if __name__ == "__main__":
    # Teste para nomes "Sujos" vindos do Google/LinkedIn
    leads = [
        ("Victor Franchescoli Faria", "Knorr-Bremse"),
        ("Ronaldo Cesar -Knorr-Bremse| LinkedIn", "Knorr-Bremse"),
        ("Gilson Caetano -Knorr-Bremse| LinkedIn", "Knorr-Bremse"),
        ("Camila Montico de Paiva", "Knorr-Bremse")
    ]
    
    for title, brand in leads:
        # Lógica ULTRA AGRESSIVA (Espelho do b2b_scanner.py)
        t_clean = title.replace(" | LinkedIn", "").replace("| LinkedIn", "").strip()
        parts = re.split(r'[\|\-\–\—•]', t_clean)
        name_guess = parts[0].strip()
        
        # Se colou com a empresa (ex: NomeKnorrBremse), removemos a marca
        clean_name = re.split(fr"\s*{re.escape(brand)}", name_guess, flags=re.I)[0].strip()
        clean_name = clean_name.split('...')[0].strip()
        
        if len(clean_name) < 3 or clean_name.lower() in brand.lower() or "linkedin" in clean_name.lower():
            print(f"[-] Ignorando lixo: {clean_name}")
            continue
            
        asyncio.run(test_system_theorg_logic(clean_name, brand))
