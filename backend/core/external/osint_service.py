"""
core.external.osint_service
===========================
Enriquecimento de leads via toolkit OSINT externo (Node.js subprocess).

Executa scripts/osint-toolkit de forma assincrona via create_subprocess_exec,
passando nome+empresa e recebendo JSON com email provavel, WhatsApp e PABX.

Singleton: osint_service
Funcao publica: enrich_lead(name, company, domain, cnpj) -> dict
"""
import subprocess
import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class OSINTService:
    """Serviço para chamar o Kit de Enriquecimento OSINT (Node.js)."""
    
    @staticmethod
    async def enrich_lead(name: str, company: str, domain: Optional[str] = None, cnpj: Optional[str] = None) -> Dict[Any, Any]:
        """
        Chama o script Node.js para identificar contatos do lead.
        """
        # Caminho absoluto para o script CLI
        current_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.abspath(os.path.join(current_dir, "../../scripts/osint-toolkit/cli_enrich.js"))
        
        if not os.path.exists(script_path):
            logger.error(f"Script OSINT não encontrado em: {script_path}")
            return {"error": f"Toolkit OSINT não encontrado."}

        try:
            # Executa o comando via subprocess
            cmd = ["node", script_path, name, company]
            
            # Garante que os argumentos opcionais sejam passados na ordem correta
            # CLI espera: [name, company, domain, cnpj]
            cmd.append(domain or "")
            if cnpj:
                cmd.append(cnpj)
            
            # Execução síncrona embrulhada em executor para não travar o loop async
            import asyncio
            from functools import partial
            
            # Função para rodar o subprocess
            def run_cmd():
                env = os.environ.copy()
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    env=env,
                    encoding='utf-8' # Força UTF-8 para evitar problemas com caracteres brasileiros
                )
                return result

            # Roda no pool de threads padrão
            loop = asyncio.get_event_loop()
            process_result = await loop.run_in_executor(None, run_cmd)

            if process_result.returncode != 0:
                logger.error(f"Erro ao rodar OSINT: {process_result.stderr}")
                try:
                    return json.loads(process_result.stderr)
                except:
                    return {"error": "Falha na execução do toolkit OSINT.", "detail": process_result.stderr}

            # Parse do JSON retornado pelo script
            stdout = process_result.stdout.strip()
            if not stdout:
                return {"error": "Script OSINT não retornou dados."}
                
            try:
                # Tenta localizar o JSON na saída caso haja logs misturados
                json_start = stdout.find('{')
                json_end = stdout.rfind('}') + 1
                if json_start != -1 and json_end != -1:
                    json_str = stdout[json_start:json_end]
                    return json.loads(json_str)
                
                return json.loads(stdout)
            except json.JSONDecodeError as je:
                logger.error(f"Erro ao decodificar JSON do OSINT: {str(je)}")
                logger.error(f"Saída bruta: {stdout}")
                return {"error": "Resposta do toolkit OSINT em formato inválido.", "raw": stdout[:200]}

        except Exception as e:
            logger.error(f"Exceção ao chamar OSINTService: {str(e)}")
            return {"error": f"Erro interno ao processar OSINT: {str(e)}"}

# Singleton
osint_service = OSINTService()
