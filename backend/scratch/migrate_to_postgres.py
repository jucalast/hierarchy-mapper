import asyncio
import os
import sys
from pathlib import Path

# Configura codificação UTF-8 para stdout e stderr
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr:
    sys.stderr.reconfigure(encoding='utf-8')

# Corrige o loop de eventos no Windows para suportar asyncpg
if sys.platform == "win32":
    from asyncio import WindowsProactorEventLoopPolicy
    if not isinstance(asyncio.get_event_loop_policy(), WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select, text

# Ajusta o sys.path para encontrar os módulos do backend
scratch_dir = Path(__file__).resolve().parent
backend_root = scratch_dir.parent
sys.path.insert(0, str(backend_root))

from core.infra.database import Base, engine as pg_engine
from core.config import settings
import models  # Certifica que todos os modelos estão registrados na metadata do Base

SQLITE_URL = f"sqlite+aiosqlite:///{backend_root / 'intelligence.db'}"
PG_URL = settings.DATABASE_URL

print(f"Banco de Origem (SQLite): {SQLITE_URL}")
print(f"Banco de Destino (PostgreSQL): {PG_URL}")

async def reset_sequences(conn, table):
    """Reseta as sequências auto-incrementais do Postgres para evitar colisões pós-migração."""
    for col in table.primary_key.columns:
        if issubclass(col.type.python_type, int):
            try:
                seq_res = await conn.execute(text(f"SELECT pg_get_serial_sequence('{table.name}', '{col.name}')"))
                seq_name = seq_res.scalar()
                if seq_name:
                    await conn.execute(text(f"SELECT setval('{seq_name}', COALESCE((SELECT MAX({col.name}) FROM {table.name}), 1), true)"))
                    print(f"Sequência resetada para {table.name}.{col.name} -> {seq_name}")
            except Exception as e:
                try:
                    default_seq = f"{table.name}_{col.name}_seq"
                    await conn.execute(text(f"SELECT setval('{default_seq}', COALESCE((SELECT MAX({col.name}) FROM {table.name}), 1), true)"))
                    print(f"Sequência resetada (fallback) para {table.name}.{col.name} -> {default_seq}")
                except Exception as ex:
                    print(f"Não foi possível resetar a sequência para {table.name}.{col.name}: {ex}")

async def migrate():
    sqlite_engine = create_async_engine(SQLITE_URL)
    # pg_engine é importado de core.infra.database
    
    print("\nCriando tabelas no PostgreSQL (caso não existam)...")
    async with pg_engine.begin() as pg_conn:
        await pg_conn.run_sync(Base.metadata.create_all)
    print("Estrutura das tabelas no PostgreSQL criada/verificada.")
    
    async with sqlite_engine.connect() as sqlite_conn:
        async with pg_engine.connect() as pg_conn:
            # sorted_tables ordena as tabelas respeitando as dependências de chaves estrangeiras
            for table in Base.metadata.sorted_tables:
                print(f"\n--- Migrando Tabela: {table.name} ---")
                
                try:
                    stmt = select(table)
                    res = await sqlite_conn.execute(stmt)
                    rows = res.fetchall()
                except Exception as e:
                    print(f"Erro ao ler tabela SQLite {table.name}: {e}. Pulando tabela.")
                    continue
                
                if not rows:
                    print(f"Tabela {table.name} vazia no SQLite. Pulando.")
                    continue
                
                print(f"Encontrados {len(rows)} registros para migrar.")
                
                # Limpa registros antigos na tabela destino para evitar duplicidades
                try:
                    await pg_conn.execute(table.delete())
                    await pg_conn.commit()
                except Exception as e:
                    print(f"Aviso: Não foi possível limpar registros na tabela destino {table.name}: {e}")
                
                # Mapeia as linhas recuperadas para dicionários chave-valor
                insert_data = [dict(row._mapping) for row in rows]
                try:
                    # Inserção em lote (Bulk insert)
                    await pg_conn.execute(table.insert(), insert_data)
                    await pg_conn.commit()
                    print(f"Migrados {len(insert_data)} registros com sucesso para {table.name}.")
                except Exception as e:
                    print(f"Erro na inserção em lote para {table.name}: {e}")
                    await pg_conn.rollback()
                    
                    # Fallback linha a linha se a inserção em lote falhar
                    print("Iniciando inserção linha a linha (fallback)...")
                    success_count = 0
                    for item in insert_data:
                        try:
                            await pg_conn.execute(table.insert(), item)
                            await pg_conn.commit()
                            success_count += 1
                        except Exception as row_err:
                            print(f"Erro ao inserir linha na tabela {table.name} (PK={item.get('id', item.get('key'))}): {row_err}")
                            await pg_conn.rollback()
                    print(f"Fallback concluído: {success_count} / {len(insert_data)} registros inseridos.")
                
                # Atualiza os contadores de sequências auto-incrementais no Postgres
                await reset_sequences(pg_conn, table)
                await pg_conn.commit()

    print("\nMigração de banco de dados finalizada com sucesso!")
    await sqlite_engine.dispose()
    await pg_engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
