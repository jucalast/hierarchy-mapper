from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))

with engine.connect() as conn:
    # Primeiro encontrar o ID da organização Metasil
    org_result = conn.execute(text("SELECT id, name FROM organizations WHERE name ILIKE '%metasil%'"))
    orgs = org_result.fetchall()
    
    if orgs:
        print(f"Organizações encontradas com 'metasil':")
        for org in orgs:
            print(f"  ID: {org[0]}, Nome: {org[1]}")
            
            # Contar funcionários para cada organização
            emp_result = conn.execute(text(f"SELECT COUNT(*) FROM employees WHERE org_id = {org[0]}"))
            emp_count = emp_result.scalar()
            print(f"  Funcionários: {emp_count}")
    else:
        print("Nenhuma organização encontrada com 'metasil' no nome")
