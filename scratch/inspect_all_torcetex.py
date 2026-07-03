import sqlite3

def inspect():
    conn = sqlite3.connect("backend/intelligence.db")
    cursor = conn.cursor()
    
    org_ids = [267, 268, 269]
    for org_id in org_ids:
        cursor.execute("SELECT id, name, cnpj, domain FROM organizations WHERE id = ?;", (org_id,))
        org = cursor.fetchone()
        print(f"\n=================== ORGANIZATION {org_id} ===================")
        print("Org:", org)
        
        cursor.execute(
            "SELECT id, name, role, department, manager_id, seniority, linkedin_url FROM employees WHERE company_id = ?;", 
            (org_id,)
        )
        emps = cursor.fetchall()
        print(f"Employees count: {len(emps)}")
        for emp in emps:
            print(f"  {emp}")
            
    conn.close()

if __name__ == "__main__":
    inspect()
