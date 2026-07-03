"""
migrate_to_sqlite.py
====================
Migra todos os dados do banco PostgreSQL (Neon) para um banco SQLite local.

Uso:
    cd backend
    python scratch/migrate_to_sqlite.py

O arquivo de destino é sempre: backend/intelligence.db
O .env é atualizado automaticamente ao final para apontar para SQLite.
"""
import asyncio
import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr:
    sys.stderr.reconfigure(encoding="utf-8")

# Windows: asyncpg precisa do ProactorEventLoop
if sys.platform == "win32":
    from asyncio import WindowsProactorEventLoopPolicy
    if not isinstance(asyncio.get_event_loop_policy(), WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())

scratch_dir = Path(__file__).resolve().parent
backend_root = scratch_dir.parent
sys.path.insert(0, str(backend_root))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select, text, inspect
import models  # registra todos os models na metadata do Base

from core.infra.database import Base
from core.config import settings

# ── Configuração ──────────────────────────────────────────────────────────────

# Conexão direta (sem pooler) — evita bloqueio de cota de egress do Neon
PG_URL = "postgresql+asyncpg://neondb_owner:npg_CfaM2lIAs1xY@ep-cold-dream-ahqfuczb.c-3.us-east-1.aws.neon.tech/neondb"

SQLITE_PATH = backend_root / "intelligence.db"
SQLITE_URL = f"sqlite+aiosqlite:///{SQLITE_PATH}"

ENV_FILE = backend_root / ".env"

print(f"Fonte  (PostgreSQL): {PG_URL}")
print(f"Destino (SQLite)   : {SQLITE_PATH}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_value(v):
    """Converte tipos que SQLite não aceita diretamente (dicts/lists → JSON string)."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v

def _prepare_row(row_mapping, table):
    """Normaliza uma linha do Postgres para inserção no SQLite."""
    row = dict(row_mapping)
    for col in table.columns:
        if col.name in row and row[col.name] is not None:
            row[col.name] = _serialize_value(row[col.name])
    return row

# ── Migração ──────────────────────────────────────────────────────────────────

async def migrate():
    # Backup do SQLite existente, se houver
    if SQLITE_PATH.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = SQLITE_PATH.with_suffix(f".backup_{ts}.db")
        shutil.copy2(SQLITE_PATH, backup)
        print(f"\nBackup do SQLite existente salvo em: {backup.name}")

    pg_engine = create_async_engine(
        PG_URL,
        echo=False,
        connect_args={"ssl": True},
    )
    sqlite_engine = create_async_engine(
        SQLITE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Habilita WAL e busy_timeout no SQLite
    from sqlalchemy import event as sa_event
    @sa_event.listens_for(sqlite_engine.sync_engine, "connect")
    def set_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=OFF")  # desliga FKs durante carga
        cur.close()

    print("\nCriando estrutura de tabelas no SQLite...")
    async with sqlite_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Estrutura criada.")

    # Roda as mesmas migrações manuais do init_db() para adicionar colunas
    # que existem no Postgres mas não estão definidas no modelo SQLAlchemy
    print("Aplicando migrações manuais no SQLite...")
    manual_migrations = [
        "ALTER TABLE employees ADD COLUMN email VARCHAR",
        "ALTER TABLE organizations ADD COLUMN description TEXT",
        "ALTER TABLE employees ADD COLUMN description TEXT",
        "ALTER TABLE employees ADD COLUMN location VARCHAR",
        "ALTER TABLE employees ADD COLUMN manager_id VARCHAR",
        "ALTER TABLE organizations ADD COLUMN category VARCHAR",
        "ALTER TABLE organizations ADD COLUMN product_focus VARCHAR",
        "ALTER TABLE employees ADD COLUMN department VARCHAR",
        "ALTER TABLE organizations ADD COLUMN linkedin_url VARCHAR",
        "ALTER TABLE organizations ADD COLUMN logo_url VARCHAR",
        "ALTER TABLE organizations ADD COLUMN is_excluded INTEGER DEFAULT 0",
        "ALTER TABLE employees ADD COLUMN temperature VARCHAR",
        "ALTER TABLE employees ADD COLUMN phone VARCHAR",
        "ALTER TABLE employees ADD COLUMN whatsapp_number VARCHAR",
        "ALTER TABLE organizations ADD COLUMN source VARCHAR DEFAULT 'pipedrive'",
        "ALTER TABLE employees ADD COLUMN source VARCHAR DEFAULT 'pipedrive'",
        "ALTER TABLE employees ADD COLUMN is_discovery INTEGER DEFAULT 0",
        "ALTER TABLE prospect_leads ADD COLUMN pipedrive_deal_id INTEGER",
        "ALTER TABLE business_profiles ADD COLUMN value_propositions JSON",
        "ALTER TABLE icp_configs ADD COLUMN pain_points JSON",
        "ALTER TABLE users ADD COLUMN hashed_password VARCHAR",
        "ALTER TABLE business_profiles ADD COLUMN presentation_path VARCHAR",
        "ALTER TABLE business_profiles ADD COLUMN signature_path VARCHAR",
        "ALTER TABLE contact_conversation_cache ADD COLUMN has_unread INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE contact_conversation_cache ADD COLUMN is_key_contact INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE organizations ADD COLUMN photo_url TEXT",
        "ALTER TABLE organizations ADD COLUMN email_pattern VARCHAR",
    ]
    async with sqlite_engine.connect() as conn:
        for sql in manual_migrations:
            try:
                await conn.execute(text(sql))
                await conn.commit()
            except Exception:
                await conn.rollback()
    print("Migrações manuais aplicadas.")

    tabelas = Base.metadata.sorted_tables  # ordem respeita FK
    total_tabelas = len(tabelas)

    async with pg_engine.connect() as pg_conn:
        async with sqlite_engine.connect() as sqlite_conn:
            for i, table in enumerate(tabelas, 1):
                print(f"\n[{i}/{total_tabelas}] Tabela: {table.name}")

                # Lê do Postgres
                try:
                    res = await pg_conn.execute(select(table))
                    rows = res.fetchall()
                except Exception as e:
                    print(f"  ERRO ao ler do Postgres: {e}. Pulando.")
                    continue

                if not rows:
                    print("  Vazia. Pulando.")
                    continue

                print(f"  {len(rows)} registros encontrados.")

                # Limpa tabela destino
                try:
                    await sqlite_conn.execute(table.delete())
                    await sqlite_conn.commit()
                except Exception as e:
                    print(f"  Aviso ao limpar destino: {e}")
                    await sqlite_conn.rollback()

                # Prepara dados
                insert_data = [_prepare_row(row._mapping, table) for row in rows]

                # Tentativa em lote
                try:
                    await sqlite_conn.execute(table.insert(), insert_data)
                    await sqlite_conn.commit()
                    print(f"  OK — {len(insert_data)} registros inseridos.")
                except Exception as e:
                    print(f"  Falha em lote: {e}")
                    await sqlite_conn.rollback()

                    # Fallback linha a linha
                    print("  Tentando linha a linha...")
                    ok = 0
                    for item in insert_data:
                        try:
                            await sqlite_conn.execute(table.insert(), item)
                            await sqlite_conn.commit()
                            ok += 1
                        except Exception as row_err:
                            pk = item.get("id", item.get("key", "?"))
                            print(f"    ERRO linha PK={pk}: {row_err}")
                            await sqlite_conn.rollback()
                    print(f"  Fallback: {ok}/{len(insert_data)} inseridos.")

    await pg_engine.dispose()
    await sqlite_engine.dispose()
    print("\n=== Migração concluída! ===")

    # Atualiza o .env para apontar para SQLite
    _update_env_to_sqlite()


def _update_env_to_sqlite():
    """Substitui DATABASE_URL no .env pelo endereço SQLite."""
    if not ENV_FILE.exists():
        print(f"\nAviso: {ENV_FILE} não encontrado. Atualize DATABASE_URL manualmente.")
        return

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
    nova_url = "sqlite+aiosqlite:///./intelligence.db"
    updated = False
    new_lines = []

    for line in lines:
        if line.startswith("DATABASE_URL="):
            new_lines.append(f"DATABASE_URL={nova_url}\n")
            updated = True
            print(f"\n.env atualizado: DATABASE_URL={nova_url}")
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"\nDATABASE_URL={nova_url}\n")
        print(f"\n.env: DATABASE_URL={nova_url} adicionada.")

    ENV_FILE.write_text("".join(new_lines), encoding="utf-8")
    print("Reinicie o backend para aplicar a mudança.")


if __name__ == "__main__":
    asyncio.run(migrate())
