import sqlite3

def inspect():
    conn = sqlite3.connect("backend/intelligence.db")
    cursor = conn.cursor()
    
    # Find organization for Torcetex
    cursor.execute("SELECT id, name, cnpj, domain FROM organizations WHERE name LIKE '%Torcetex%';")
    orgs = cursor.fetchall()
    print("\nOrganizations matching Torcetex:")
    for org in orgs:
        print(org)
        org_id = org[0]
        
        # Get employees for this organization
        cursor.execute(
            "SELECT id, name, role, department, manager_id, seniority FROM employees WHERE company_id = ?;", 
            (org_id,)
        )
        emps = cursor.fetchall()
        print(f"\nEmployees for org_id {org_id}:")
        for emp in emps:
            print(emp)
            
    conn.close()

if __name__ == "__main__":
    inspect()
