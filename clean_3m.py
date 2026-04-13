import sqlite3
from pathlib import Path

# Detectar o banco de dados
db_path = Path('backend/intelligence.db')
if not db_path.exists():
    print(f"❌ Banco de dados não encontrado em {db_path}")
    exit(1)

try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 1. Encontrar a empresa 3M
    print("🔍 Procurando pela empresa 3M...")
    cursor.execute("SELECT id, name, pipedrive_id FROM organizations WHERE LOWER(name) LIKE '%3m%'")
    results = cursor.fetchall()
    
    if not results:
        print("❌ Empresa 3M não encontrada no banco de dados")
        conn.close()
        exit(1)
    
    for org_id, name, pipedrive_id in results:
        print(f"\n📋 Encontrado: '{name}' (ID: {org_id}, Pipedrive ID: {pipedrive_id})")
        
        if pipedrive_id:
            # Se tem pipedrive_id, limpar apenas campos extras
            print(f"   ✏️  Limpando campos extras (mantendo dados do Pipedrive)...")
            cursor.execute("""
                UPDATE organizations 
                SET cnpj = NULL,
                    description = NULL,
                    category = NULL,
                    product_focus = NULL,
                    linkedin_url = NULL,
                    logo_url = NULL
                WHERE id = ?
            """, (org_id,))
            print(f"   ✅ Campos extras removidos")
        else:
            # Se não tem pipedrive_id, deletar completamente
            print(f"   🗑️  Deletando registro (não veio do Pipedrive)...")
            cursor.execute("DELETE FROM organizations WHERE id = ?", (org_id,))
            
            # Também deletar funcionários associados
            cursor.execute("DELETE FROM employees WHERE company_id = ?", (org_id,))
            print(f"   ✅ Registro e funcionários deletados")
    
    # 2. Confirmar as mudanças
    conn.commit()
    print("\n✨ Limpeza concluída com sucesso!")
    
except Exception as e:
    print(f"❌ Erro ao limpar banco: {e}")
    conn.rollback()
finally:
    if conn:
        conn.close()
