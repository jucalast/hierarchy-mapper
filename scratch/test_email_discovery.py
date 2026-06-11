import asyncio
import os
import sys

# Adiciona o diretório backend ao PYTHONPATH para os imports funcionarem
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, backend_dir)

from core.external.email_service import verify_email_via_abstract_api
from core.config import settings

async def main():
    print("=== TESTE DIRETO DA ABSTRACT API ===")
    print(f"API Key: {settings.EMAIL_API_KEY}")
    
    test_emails = [
        "suporte@github.com",
        "email_invalido_que_nao_deve_existir_123456@gmail.com",
        "andre.ribeiro@rochaautopecas.com.br"
    ]
    
    for email in test_emails:
        print(f"\nVerificando email: {email}")
        res = await verify_email_via_abstract_api(email, settings.EMAIL_API_KEY)
        print(f"Resultado: {res}")

if __name__ == "__main__":
    asyncio.run(main())
