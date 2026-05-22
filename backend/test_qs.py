import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.infra.database import async_session
from sqlalchemy import select, or_
from models.people.employee import Employee
from models.communication.contact_cache import ContactConversationCache

async def main():
    async with async_session() as db:
        identifiers = ["19998218650"]
        employees_stmt = select(Employee.email, Employee.phone, Employee.whatsapp_number, Employee.profile_pic).where(
            or_(
                Employee.email.in_(identifiers),
                Employee.phone.in_(identifiers),
                Employee.whatsapp_number.in_(identifiers)
            )
        )
        emp_result = await db.execute(employees_stmt)
        for row in emp_result.all():
            print("ROW:", row)
        print("Done")

if __name__ == "__main__":
    asyncio.run(main())