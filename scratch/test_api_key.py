import sys
import os
import asyncio

# Add backend directory to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

# Load settings
from core.config import settings
from core.external.email_service import discover_and_validate_email

async def main():
    print("=== TESTE DE VALIDAÇÃO VIA ABSTRACT API ===")
    
    # Verify key loading
    key = getattr(settings, "ABSTRACT_API_EMAIL_KEY", None) or os.environ.get("ABSTRACT_API_EMAIL_KEY")
    if not key:
        print("Erro: Chave ABSTRACT_API_EMAIL_KEY não encontrada em backend/.env")
        return
        
    masked_key = key[:4] + "*" * (len(key) - 4) if len(key) > 4 else "***"
    print("Abstract API Key Carregada com Sucesso:", masked_key)
    
    # Process email discovery & validation via API
    args = {
        "first": "andre",
        "last": "ribeiro",
        "domain": "rochaautopecas.com.br"
    }
    
    print(f"\nConsultando deliverability via API para: {args['first']}.{args['last']}@{args['domain']}...")
    try:
        res = await discover_and_validate_email(
            first=args["first"],
            last=args["last"],
            domain=args["domain"],
            do_smtp=True
        )
        print("\n=== RESULTADO DO PIPELINE ===")
        import pprint
        pprint.pprint(res, width=120)
    except Exception as e:
        print("Erro ao executar pipeline:", e)
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
