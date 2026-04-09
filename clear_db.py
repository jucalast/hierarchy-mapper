import sqlite3

def clear_database():
    try:
        conn = sqlite3.connect('backend/intelligence.db')
        cursor = conn.cursor()
        
        print("Limpando tabela 'employees'...")
        cursor.execute("DELETE FROM employees")
        
        print("Limpando tabela 'organizations'...")
        cursor.execute("DELETE FROM organizations")
        
        conn.commit()
        print("Banco de dados zerado com sucesso!")
        
    except Exception as e:
        print(f"Erro ao limpar banco de dados: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    clear_database()
