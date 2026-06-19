"""
Alembic env — usa Base + URL do projeto (settings).
Suporta async engine; funciona com SQLite + Postgres (Neon).
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importa Base + models para autogenerate
from core.config import settings
from core.infra.database import Base
from models import AutomatedAction, Employee, Organization  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Sobrescreve URL com a do projeto (suporta async drivers)
from core.infra.database import DATABASE_URL as db_url
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Roda migrações no modo 'offline' (gera SQL sem conectar)."""
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online_async() -> None:
    """Roda migrações com engine async (aiosqlite/asyncpg)."""
    connect_args = {}
    if "postgresql" in db_url.lower():
        connect_args = {"ssl": True}

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online_sync() -> None:
    """Fallback síncrono (caso URL não seja async)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    if "+aiosqlite" in db_url or "+asyncpg" in db_url:
        asyncio.run(run_migrations_online_async())
    else:
        run_migrations_online_sync()
