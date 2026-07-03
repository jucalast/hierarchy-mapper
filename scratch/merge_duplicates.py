import sqlite3
import sys
import os

# Add backend directory to path to use filters
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from modules.hierarchy.service.filters import is_same_person

def merge():
    conn = sqlite3.connect("backend/intelligence.db")
    cursor = conn.cursor()
    
    # Load all employees of org 268
    cursor.execute(
        "SELECT id, name, role, department, manager_id, seniority, linkedin_url, profile_pic, location, email, source FROM employees WHERE company_id = 268;"
    )
    emps = cursor.fetchall()
    print("Found employees count:", len(emps))
    
    merged = set()
    to_delete = []
    
    for i in range(len(emps)):
        e1 = emps[i]
        id1, name1 = e1[0], e1[1]
        if id1 in merged:
            continue
            
        for j in range(i + 1, len(emps)):
            e2 = emps[j]
            id2, name2 = e2[0], e2[1]
            if id2 in merged:
                continue
                
            if is_same_person(name1, name2):
                print(f"\nMatching duplicates found: ID {id1} ({name1}) and ID {id2} ({name2})")
                
                # We will merge e2 into e1
                # Choose the better/longer name
                better_name = name2 if len(name2) > len(name1) and "(" not in name2 else name1
                if "(" in better_name:
                    better_name = name2 if "(" not in name2 else better_name.split("(")[0].strip()
                
                better_role = e2[2] if e2[2] and e2[2] not in ["Contato no Pipedrive", "Professional", "Cargo não informado"] else e1[2]
                better_dept = e2[3] if e2[3] and e2[3] not in ["Quadro de Sócios (QSA)", "Operations"] else e1[3]
                better_manager = e2[4] if e2[4] and e2[4] != "None" else e1[4]
                better_linkedin = e2[6] if e2[6] and "pipedrive" not in str(e2[6]) and "scan" not in str(e2[6]) else e1[6]
                better_pic = e2[7] if e2[7] else e1[7]
                better_loc = e2[8] if e2[8] else e1[8]
                better_email = e2[9] if e2[9] else e1[9]
                better_source = e2[10] if e2[10] == "discovery" else e1[10]
                
                print(f"Merging into ID {id1} with name: '{better_name}', role: '{better_role}', linkedin: '{better_linkedin}'")
                
                # Clear linkedin_url of e2 to avoid UNIQUE constraint violation during update
                cursor.execute("UPDATE employees SET linkedin_url = NULL WHERE id = ?;", (id2,))
                
                # Update e1
                cursor.execute(
                    """UPDATE employees SET 
                        name = ?, 
                        role = ?, 
                        department = ?, 
                        manager_id = ?, 
                        linkedin_url = ?, 
                        profile_pic = ?, 
                        location = ?, 
                        email = ?, 
                        source = ? 
                       WHERE id = ?;""",
                    (better_name, better_role, better_dept, better_manager, better_linkedin, better_pic, better_loc, better_email, better_source, id1)
                )
                
                # Mark e2 for deletion
                to_delete.append(id2)
                merged.add(id2)
                
    # Delete the duplicates
    if to_delete:
        print("\nDeleting duplicate IDs:", to_delete)
        cursor.execute(f"DELETE FROM employees WHERE id IN ({','.join(map(str, to_delete))});")
        # Also need to check if any other employee points to the deleted employee as manager, and repoint to the kept employee
        for del_id in to_delete:
            kept_id = [e[0] for e in emps if e[0] not in to_delete][0] # Simple repoint helper
            cursor.execute("UPDATE employees SET manager_id = ? WHERE manager_id = ?;", (f"node_{kept_id}", f"node_{del_id}"))
            
    conn.commit()
    conn.close()
    print("\nDatabase merge complete.")

if __name__ == "__main__":
    merge()
