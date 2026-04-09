import sqlite3

def list_employees():
    conn = sqlite3.connect('backend/intelligence.db')
    cursor = conn.cursor()
    query = """
        SELECT e.name, e.role 
        FROM employees e 
        JOIN organizations o ON e.company_id = o.id 
        WHERE o.name LIKE '%Knorr%Bremse%'
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    
    if not rows:
        print("Nenhuma pessoa encontrada para Knorr-Bremse.")
    else:
        for row in rows:
            print(f"{row[0]} | {row[1]}")
    
    conn.close()

if __name__ == "__main__":
    list_employees()
