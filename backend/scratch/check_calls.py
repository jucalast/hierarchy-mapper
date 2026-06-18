import asyncio
import os
import sys

backend_path = r"c:\Users\João Luccas\Desktop\LINKB2B\hierarchy-mapper\backend"
sys.path.append(backend_path)
os.chdir(backend_path)

from core.infra.database import async_session
from models.conversation.conversation import CallSession, CallMessage
from models.organization.organization import Organization
from sqlalchemy import select

async def run():
    async with async_session() as session:
        # Get all CallSessions
        res = await session.execute(select(CallSession))
        sessions = res.scalars().all()
        print(f"Total Call Sessions in DB: {len(sessions)}")
        print("-" * 60)
        for s in sessions:
            # count messages
            res_msg = await session.execute(select(CallMessage).where(CallMessage.call_session_id == s.id))
            msg_count = len(res_msg.scalars().all())
            
            # get org name
            org_name = "None"
            if s.org_id:
                org_res = await session.execute(select(Organization).where(Organization.id == s.org_id))
                org = org_res.scalar_one_or_none()
                if org:
                    org_name = f"{org.name} (Pipedrive ID: {org.pipedrive_id}, Local ID: {org.id})"
            
            print(f"Session ID: {s.id}")
            print(f"  Contact Name: {s.contact_name}")
            print(f"  Phone: {s.phone}")
            print(f"  Org ID: {s.org_id} (Resolved Org: {org_name})")
            print(f"  Activity ID: {s.pipedrive_activity_id}")
            print(f"  Msg Count: {msg_count}")
            print("-" * 60)

if __name__ == "__main__":
    asyncio.run(run())
