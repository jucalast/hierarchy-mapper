import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.abspath('backend'))

from core.infra.database import async_session
from models.conversation.conversation import CallSession, CallMessage
from sqlalchemy import select

async def main():
    async with async_session() as session:
        stmt = select(CallSession).order_by(CallSession.created_at.desc())
        result = await session.execute(stmt)
        sessions = result.scalars().all()
        print(f"Total CallSessions: {len(sessions)}")
        for idx, s in enumerate(sessions[:5]):
            print(f"--- Session {idx+1} ---")
            print(f"ID: {s.id}")
            print(f"Contact Name: {s.contact_name}")
            print(f"Phone: {s.phone}")
            print(f"Pipedrive Activity ID: {s.pipedrive_activity_id}")
            print(f"Flight Plan steps: {len(s.flight_plan.get('steps', [])) if s.flight_plan else 'None'}")
            print(f"Latest Insight steps: {len(s.latest_insight.get('updated_steps', [])) if (s.latest_insight and 'updated_steps' in s.latest_insight) else 'None'}")

if __name__ == '__main__':
    asyncio.run(main())
