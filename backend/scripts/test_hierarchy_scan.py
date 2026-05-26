"""
scripts/test_hierarchy_scan.py
==============================
Script de teste para validar o HierarchyScanService (LinkedIn People Scraper).

Uso:
    python backend/scripts/test_hierarchy_scan.py [url_da_empresa]
"""

import sys
import os
import asyncio
import json

# Ajusta o sys.path para garantir que o diretório backend possa ser importado corretemente
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from core.observability.logging_config import get_logger
from modules.hierarchy.service.hierarchy_scan import HierarchyScanService

log = get_logger(__name__)

async def run_test():
    # URL Padrão conforme solicitado pelo usuário
    target_url = "https://www.linkedin.com/company/grupobrasa/people/"
    output_file = None
    
    if len(sys.argv) > 1:
        target_url = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
        
    # Se estiver rodando no Windows, altera o título do console para maior clareza
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW("LINKB2B - HierarchyScan Executando...")
        except Exception:
            pass
        
    print("=" * 70)
    print("       INICIANDO VARREDURA DE PESSOAS (HierarchyScan)")
    print("=" * 70)
    print(f"Alvo: {target_url}")
    print(f"Cookie 'li_at' configurado: {'SIM (Usando headless/automático)' if settings.LINKEDIN_LI_AT else 'NÃO (Usando manual/headful)'}")
    print("=" * 70)
    
    if not settings.LINKEDIN_LI_AT:
        print("💡 DICA: Você pode configurar o cookie 'li_at' em seu arquivo backend/.env")
        print("   Exemplo: LINKEDIN_LI_AT=AQEDASg...")
        print("   Desta forma, o script executará em segundo plano (headless) automaticamente.")
        print("   Caso contrário, uma janela de navegador abrirá para você realizar o login.")
        print("-" * 70)

    # Instancia o serviço
    scraper = HierarchyScanService()
    
    # Roda a extração
    print("🚀 Iniciando navegador e processo de extração...")
    people = await scraper.scrape_company_people(target_url)
    
    print("\n" + "=" * 70)
    print(f"📊 EXTRAÇÃO CONCLUÍDA! Total de pessoas encontradas: {len(people)}")
    print("=" * 70)
    
    # Imprime uma amostragem/lista
    for idx, p in enumerate(people):
        print(f"[{idx+1:02d}] Nome: {p['name']}")
        print(f"     Cargo: {p['role']}")
        print(f"     URL: {p['linkedin_url']}")
        if p.get('location'):
            print(f"     Localização: {p['location']}")
        print("-" * 50)
        
    # Salva os resultados em arquivo JSON para inspeção do usuário
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
    os.makedirs(output_dir, exist_ok=True)
    if not output_file:
        output_file = os.path.join(output_dir, "linkedin_scrape_results.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(people, f, indent=4, ensure_ascii=False)
        
    print(f"\n✅ Resultados salvos com sucesso em: {output_file}")
    print("=" * 70)
    
    # Adiciona uma pausa elegante para que o usuário possa visualizar os logs e a listagem final no terminal aberto
    print("\n⏳ Este terminal fechará automaticamente em 10 segundos...")
    for remaining in range(10, 0, -1):
        sys.stdout.write(f"\rFechando em {remaining} segundos...")
        sys.stdout.flush()
        await asyncio.sleep(1)
    print("\n[INFO] Concluído!")

if __name__ == "__main__":
    # Garante suporte a UTF-8 no terminal Windows para evitar erros de encode com emojis e acentos
    import sys
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
    if sys.stderr.encoding != 'utf-8':
        try:
            sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
    asyncio.run(run_test())
