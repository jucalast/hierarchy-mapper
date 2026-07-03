import sqlite3

def inspect():
    conn = sqlite3.connect("backend/intelligence.db")
    cursor = conn.cursor()
    
    # Get columns of employees
    cursor.execute("PRAGMA table_info(employees);")
    cols = cursor.fetchall()
    print("Employees schema:")
    for col in cols:
        print(f"  {col[1]} ({col[2]})")
        
    print("\nEmployees matching Torcetex:")
    cursor.execute("SELECT id, name, company_id, role, department, manager_id FROM employees WHERE name LIKE '%Torcetex%';")
    for row in cursor.fetchall():
        print(row)
        
    print("\nAll organizations:")
    cursor.execute("SELECT id, name, cnpj, domain FROM organizations;")
    for row in cursor.fetchall():
        print(row)
        
    conn.close()

if __name__ == "__main__":
    inspect()
