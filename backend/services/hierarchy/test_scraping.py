import asyncio
import httpx
import re

async def test_scraping(url: str):
    headers_list = [
        # 1. Desktop Comum
        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"},
        # 2. LinkedIn Crawler (Twitterbot trick)
        {"User-Agent": "Twitterbot/1.1"},
        # 3. Googlebot
        {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"},
        # 4. Mobile
        {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"}
    ]
    
    for i, headers in enumerate(headers_list):
        ua_safe = headers['User-Agent'].encode('ascii', errors='replace').decode('ascii')
        print(f"\nTentativa {i+1} com UA: {ua_safe}")
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                print(f"Status: {resp.status_code}")
                
                content = resp.text
                size = len(content)
                print(f"Tamanho do conteúdo: {size} bytes")
                
                # Check for "Auxiliar de Compras" in any casing/form
                role_found = "Auxiliar de Compras" in content or "Auxiliar de compras" in content or "auxiliar de compras" in content
                
                if role_found:
                    print("SUCCESS! 'Auxiliar de Compras' found in HTML content.")
                    idx = content.lower().find("auxiliar de compras")
                    context = content[max(0, idx-50):idx+150]
                    print(f"Context: ...{context.encode('ascii', errors='replace').decode('ascii')}...")
                else:
                    print("FAILURE: 'Auxiliar de Compras' NOT found in HTML.")
                    if "Grow Qu" in content: # Grow Química or Quimica
                        print("Grow Química was found, but not the role.")
                    else:
                        print("NO company found (Likely login wall).")
                
                # Extract meta tags
                og_title = re.search(r'<meta property="og:title" content="(.*?)"', content)
                og_desc = re.search(r'<meta property="og:description" content="(.*?)"', content)
                if og_title: print(f"OG:TITLE: {og_title.group(1).encode('ascii', errors='replace').decode('ascii')}")
                if og_desc: print(f"OG:DESC: {og_desc.group(1).encode('ascii', errors='replace').decode('ascii')}")
                
        except Exception as e:
            print(f"Error in attempt {i+1}: {e}")

if __name__ == "__main__":
    url = "https://br.linkedin.com/in/verônica-lima-4430a313a"
    # Escapar o acento na URL se necessário? O httpx costuma lidar bem.
    asyncio.run(test_scraping(url))
