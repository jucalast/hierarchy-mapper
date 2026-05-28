# -*- coding: utf-8 -*-
import asyncio
from core.infra.database import async_session
from modules.hierarchy.service.hierarchy_loader import get_stored_hierarchy

async def run():
    async with async_session() as db:
        data = await get_stored_hierarchy(230, db)
        print([n for n in data['nodes'] if n['role'] == 'Análise Humana'])

asyncio.run(run())
