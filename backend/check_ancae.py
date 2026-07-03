import asyncio
import asyncpg

DATABASE_URL = "postgres://neondb_owner:npg_CfaM2lIAs1xY@ep-cold-dream-ahqfuczb-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require"

async def check_db():
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        table_names = [t['table_name'] for t in tables]
        
        for t in ['organizations', 'companies']:
            if t in table_names:
                rows = await conn.fetch(f"SELECT * FROM {t} WHERE name ILIKE '%ANCAE TECNOLOGIA%'")
                if rows:
                    for row in rows:
                        print(dict(row))
                else:
                    print(f"Not found in {t}")
        await conn.close()
    except Exception as e:
        print("Error:", e)

asyncio.run(check_db())
