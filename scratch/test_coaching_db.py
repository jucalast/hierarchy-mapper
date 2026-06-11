import asyncio
import sys
import os

# Ensure the backend directory is in the path
sys.path.insert(0, os.path.abspath('backend'))

from core.infra.database import async_session, init_db
from models.conversation.conversation import CallSession, CallMessage
from sqlalchemy import select

async def run_test():
    print("Initializing database (ensuring tables exist)...")
    await init_db()

    async with async_session() as session:
        # Create a new test CallSession
        test_session = CallSession(
            pipedrive_activity_id="test_activity_12345",
            org_id=1,
            contact_name="Pedro C. Andrade Junior Test",
            phone="11999999999",
            flight_plan={"steps": [{"label": "RAPPORT", "content": "Olá, tudo bem?"}]},
            latest_insight={"current_step": "RAPPORT", "suggestion": "Faça perguntas abertas"}
        )
        session.add(test_session)
        await session.commit()
        session_id = test_session.id
        print(f"Created CallSession with ID: {session_id}")

    async with async_session() as session:
        # Add CallMessages linked to this CallSession
        msg_vendor = CallMessage(
            call_session_id=session_id,
            role="Vendedor",
            text="Olá Pedro, sou o João da J.Ferres.",
            latency_ms=100,
            buffer_secs=2
        )
        msg_client = CallMessage(
            call_session_id=session_id,
            role="Cliente",
            text="Olá João, tudo bem? Em que posso ajudar?",
            latency_ms=150,
            buffer_secs=3
        )
        session.add(msg_vendor)
        session.add(msg_client)
        await session.commit()
        print("Added test CallMessages.")

    async with async_session() as session:
        # Verify by selecting the session and its messages
        stmt = select(CallSession).where(CallSession.id == session_id)
        res = await session.execute(stmt)
        db_sess = res.scalar_one_or_none()
        
        assert db_sess is not None, "CallSession was not found!"
        assert db_sess.pipedrive_activity_id == "test_activity_12345"
        assert db_sess.contact_name == "Pedro C. Andrade Junior Test"
        assert db_sess.flight_plan["steps"][0]["label"] == "RAPPORT"
        assert db_sess.latest_insight["current_step"] == "RAPPORT"

        # Check messages via relationship
        stmt_msg = select(CallMessage).where(CallMessage.call_session_id == session_id).order_by(CallMessage.timestamp)
        res_msg = await session.execute(stmt_msg)
        msgs = res_msg.scalars().all()
        
        assert len(msgs) == 2, f"Expected 2 messages, got {len(msgs)}"
        assert msgs[0].role == "Vendedor"
        assert msgs[0].text == "Olá Pedro, sou o João da J.Ferres."
        assert msgs[1].role == "Cliente"
        assert msgs[1].text == "Olá João, tudo bem? Em que posso ajudar?"
        
        print("Database verification assertions passed successfully!")

        # Cleanup test data so we keep the DB clean
        await session.delete(msgs[0])
        await session.delete(msgs[1])
        await session.delete(db_sess)
        await session.commit()
        print("Cleanup completed successfully.")

if __name__ == '__main__':
    asyncio.run(run_test())
