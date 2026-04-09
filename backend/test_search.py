from ddgs import DDGS
import time

def test_duck(brand, target):
    query = f'"{brand}" {target} linkedin'
    print(f"[DuckDuckGo] 🦆 Testando query humana (Pura): {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, region="br-pt", max_results=10))
            if results:
                print(f"[DuckDuckGo] ✅ SUCESSO! Encontrados {len(results)} perfis.")
                for r in results[:3]:
                    print(f"   - {r.get('title')} -> {r.get('href')}")
                return True
            else:
                print(f"[DuckDuckGo] ❌ Sem resultados.")
    except Exception as e:
        print(f"[DuckDuckGo] ⚠️ Erro/Bloqueio: {e}")
    return False

if __name__ == "__main__":
    brand = "Spcom"
    targets = ["Comprador", "Gerente Compras", "Logística"]
    
    print("\n" + "="*50)
    print(f"🧪 LABORATÓRIO DUCKDUCKGO: {brand.upper()}")
    print("="*50 + "\n")
    
    for t in targets:
        success = test_duck(brand, t)
        if success:
            print(f"\n🎉 SUCESSO COLETIVO! A query simplificada com DuckDuckGo funciona.")
        time.sleep(3) # Pausa humana
