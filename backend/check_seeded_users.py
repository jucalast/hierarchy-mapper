import asyncio
from sqlalchemy import select
from core.database import async_session, init_db, seed_tenant_data
from models import User
from core.security import verify_password

async def test_auth_seeding():
    print("[Test] Inicializando tabelas...")
    await init_db()
    
    print("[Test] Executando seeder de tenant...")
    async with async_session() as session:
        await seed_tenant_data(session)
    
    print("[Test] Consultando usuários no banco de dados...")
    async with async_session() as session:
        res = await session.execute(select(User))
        users = res.scalars().all()
        
        if not users:
            print("❌ Nenhum usuário cadastrado!")
            return
            
        for user in users:
            print(f"\nUser: {user.name} ({user.email})")
            print(f"Role: {user.role} | System Role: {user.user_role}")
            print(f"Hashed Password: {user.hashed_password}")
            
            # Testa a verificação da senha padrão
            correct = verify_password("admin123", user.hashed_password)
            print(f"Test login with 'admin123': {'SUCCESS' if correct else 'FAILED'}")

if __name__ == "__main__":
    asyncio.run(test_auth_seeding())
