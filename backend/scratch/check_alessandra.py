import sqlite3

conn = sqlite3.connect('intelligence.db')
cur = conn.cursor()

# Lista tabelas
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print("Tabelas:", [t[0] for t in tables])

# Verifica call_sessions
try:
    cur.execute("SELECT id, contact_name, org_id, phone, created_at FROM call_sessions ORDER BY created_at DESC LIMIT 20")
    rows = cur.fetchall()
    print("\nCall sessions:")
    for r in rows:
        print(r)
except Exception as e:
    print(f"Erro call_sessions: {e}")

# Verifica employees com nome Alessandra
try:
    cur.execute("SELECT id, name, company_id, phone, whatsapp_number FROM employees WHERE name LIKE '%lessandra%'")
    rows = cur.fetchall()
    print("\nEmployees Alessandra:")
    for r in rows:
        print(r)
except Exception as e:
    print(f"Erro employees: {e}")

# Verifica organizations perto de Torcetex
try:
    cur.execute("SELECT id, pipedrive_id, name FROM organizations WHERE name LIKE '%orcetex%' OR pipedrive_id = 830")
    rows = cur.fetchall()
    print("\nOrgs Torcetex:")
    for r in rows:
        print(r)
except Exception as e:
    print(f"Erro organizations: {e}")

conn.close()
