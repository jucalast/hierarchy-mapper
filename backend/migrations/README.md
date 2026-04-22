# Alembic — Migrations

Setup já configurado em `alembic.ini` e `migrations/env.py`. URL é lida do
`settings.DATABASE_URL` (suporta SQLite + Postgres async/sync).

## Comandos

```bash
# Gerar nova migração (autogenerate)
alembic revision --autogenerate -m "add_org_indices"

# Aplicar migrações pendentes
alembic upgrade head

# Reverter última migração
alembic downgrade -1

# Ver histórico
alembic history --verbose
```

## Notas

- O `init_db()` (em `core/database.py`) ainda cria as tabelas no startup como
  fallback amigável. Em produção, prefira:
  1. Rodar `alembic upgrade head` no deploy.
  2. Desativar `init_db()` ou torná-lo idempotente (`create_all` é idempotente).
- Para Postgres, certifique-se de que o driver `asyncpg` está instalado
  (já está em `requirements.txt`).
