import sqlite3
import pandas as pd

conn = sqlite3.connect('c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/backend/intelligence.db')

# Find Metasil organizations
orgs = pd.read_sql_query("SELECT id, name FROM organizations WHERE name LIKE '%metasil%'", conn)
print("Metasil organizations:")
print(orgs)

# If any found, find deals
if not orgs.empty:
    org_ids = ','.join(orgs['id'].astype(str))
    
    # Deals
    # Let's check table schema for deals first
    tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)
    
    if 'deals' in tables['name'].values:
        deals = pd.read_sql_query(f"SELECT * FROM deals WHERE org_id IN ({org_ids})", conn)
        print(f"\nDeals found: {len(deals)}")
    else:
        print("\nTable 'deals' not found in database.")
        
    if 'employees' in tables['name'].values:
        employees = pd.read_sql_query(f"SELECT * FROM employees WHERE org_id IN ({org_ids})", conn)
        print(f"\nEmployees found: {len(employees)}")
    else:
        # Check if contacts/persons table exists
        if 'persons' in tables['name'].values:
            persons = pd.read_sql_query(f"SELECT * FROM persons WHERE org_id IN ({org_ids})", conn)
            print(f"\nPersons found: {len(persons)}")
        elif 'contacts' in tables['name'].values:
            contacts = pd.read_sql_query(f"SELECT * FROM contacts WHERE org_id IN ({org_ids})", conn)
            print(f"\nContacts found: {len(contacts)}")
        else:
            print("\nNo employee/person/contact table found.")
            print("Tables:", tables['name'].tolist())
