import os
import json
import asyncio
from google.cloud import bigquery
from google.oauth2 import service_account
from typing import List, Dict, Optional

class BigQueryService:
    def __init__(self):
        self.key_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "google-cloud-key.json")
        self.project_id = "pesquisa-cnpj-app"
        self.client = None
        
        if os.path.exists(self.key_path):
            try:
                credentials = service_account.Credentials.from_service_account_file(self.key_path)
                self.client = bigquery.Client(credentials=credentials, project=self.project_id)
                print(f"[BigQuery] 🚀 Cliente iniciado com sucesso (Projeto: {self.project_id})")
            except Exception as e:
                print(f"[BigQuery] ❌ Erro ao inicializar cliente: {e}")
        else:
            print(f"[BigQuery] ⚠️ Arquivo de chave não encontrado em: {self.key_path}")

    async def search_company_by_name(self, name: str, limit: int = 5) -> List[Dict]:
        """
        Busca empresas pelo nome na base pública da Receita Federal (BigQuery).
        """
        if not self.client:
            print("[BigQuery] ⚠️ Cliente não disponível.")
            return []

        # A query usa a base 'estabelecimentos' e 'empresas' da base-dos-dados
        query = """
            SELECT 
                t1.cnpj, 
                t2.razao_social, 
                t1.nome_fantasia, 
                t1.sigla_uf as uf, 
                t1.logradouro,
                t1.numero,
                t1.bairro,
                t1.email,
                t1.id_municipio
            FROM `basedosdados.br_me_cnpj.estabelecimentos` AS t1
            JOIN `basedosdados.br_me_cnpj.empresas` AS t2 ON t1.cnpj_basico = t2.cnpj_basico
            WHERE (LOWER(t2.razao_social) LIKE LOWER(@nome) 
               OR LOWER(t1.nome_fantasia) LIKE LOWER(@nome))
               AND t1.situacao_cadastral = '2' -- 2 = ATIVA
            ORDER BY t1.ano DESC, t1.mes DESC
            LIMIT @limit
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("nome", "STRING", f"%{name}%"),
                bigquery.ScalarQueryParameter("limit", "INT64", limit)
            ]
        )

        try:
            print(f"[BigQuery] 🕵️‍♂️ Buscando: '{name}'...")
            
            # Executa em um thread pool para não bloquear o loop async
            loop = asyncio.get_event_loop()
            query_job = await loop.run_in_executor(None, lambda: self.client.query(query, job_config=job_config))
            results = await loop.run_in_executor(None, lambda: list(query_job.result()))

            companies = []
            for row in results:
                # Monta endereço amigável
                address = f"{row.get('logradouro')}, {row.get('numero')} - {row.get('bairro')}, {row.get('id_municipio')} - {row.get('uf')}"
                
                companies.append({
                    "cnpj": row.get("cnpj"),
                    "razao_social": row.get("razao_social"),
                    "nome_fantasia": row.get("nome_fantasia"),
                    "uf": row.get("uf"),
                    "municipio": row.get("id_municipio"),
                    "address": address,
                    "email": row.get("email"),
                    "domain": row.get("email").split("@")[1] if row.get("email") and "@" in row.get("email") else None
                })
            
            print(f"[BigQuery] ✅ {len(companies)} resultados encontrados.")
            return companies

        except Exception as e:
            print(f"[BigQuery] ❌ Erro na consulta: {e}")
            return []

# Singleton
bigquery_service = BigQueryService()
