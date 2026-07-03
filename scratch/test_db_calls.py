import asyncio
import sys
import os

# Ensure the backend directory is in the path
sys.path.insert(0, os.path.abspath('backend'))

from core.infra.database import async_session
from models.conversation.conversation import CallSession, CallMessage
from sqlalchemy import select

async def main():
    async with async_session() as session:
        # Check CallSession
        stmt = select(CallSession)
        result = await session.execute(stmt)
        sessions = result.scalars().all()
        print(f"--- Call Sessions ({len(sessions)}) ---")
        for s in sessions:
            print(f"ID: {s.id}")
            print(f"  Pipedrive Activity ID: {s.pipedrive_activity_id}")
            print(f"  Org ID: {s.org_id}")
            print(f"  Contact Name: {s.contact_name}")
            print(f"  Phone: {s.phone}")
            print(f"  Flight Plan Steps: {list(s.flight_plan.keys()) if s.flight_plan else None}")
            print(f"  Latest Insight: {s.latest_insight}")
            print(f"  Created At: {s.created_at}")
            
            # Fetch messages for this session
            stmt_msg = select(CallMessage).where(CallMessage.call_session_id == s.id).order_by(CallMessage.timestamp)
            res_msg = await session.execute(stmt_msg)
            messages = res_msg.scalars().all()
            print(f"  Messages ({len(messages)}):")
            for m in messages:
                print(f"    [{m.role}]: {m.text[:60]}... (latency: {m.latency_ms}ms, buffer: {m.buffer_secs}s)")
            print("-" * 40)

if __name__ == '__main__':
    asyncio.run(main())
