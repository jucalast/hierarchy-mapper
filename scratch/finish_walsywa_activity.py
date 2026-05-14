import asyncio
import os
import sys

# Adiciona o diretório backend ao path para que os imports funcionem
backend_path = os.path.abspath('backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

from services.pipedrive.pipedrive_service import pipedrive_service

async def main():
    # Atualiza a atividade 8000 para concluída
    success = await pipedrive_service.update_activity(8000, {"done": 1})
    print(f"Update success: {success}")

if __name__ == "__main__":
    asyncio.run(main())
