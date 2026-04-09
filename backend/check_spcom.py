import sqlite3
conn = sqlite3.connect('intelligence.db')
cursor = conn.cursor()
cursor.execute('SELECT id, name, cnpj, pipedrive_id FROM organizations WHERE lower(name) LIKE "%spcom%"')
rows = cursor.fetchall()
print("--- EMPRESAS SPCOM NO BANCO ---")
for r in rows:
    print(f"ID: {r[0]} | Nome: {r[1]} | CNPJ: {r[2]} | Pipedrive ID: {r[3]}")
conn.close()
