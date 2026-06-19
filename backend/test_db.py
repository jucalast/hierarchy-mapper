import asyncio, os
from dotenv import load_dotenv
load_dotenv()
import asyncpg
async def run():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    print(await conn.fetchrow('SELECT id, name, prospecting_context FROM organizations WHERE pipedrive_id = 1077'))
    await conn.close()
asyncio.run(run())
