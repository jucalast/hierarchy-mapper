import sqlite3
conn = sqlite3.connect('intelligence.db')
cursor = conn.cursor()
cursor.execute('SELECT id, name FROM organizations WHERE lower(name) LIKE "%spcom%"')
rows = cursor.fetchall()
if len(rows) > 1:
    target_id = rows[0][0]
    cursor.execute(f'DELETE FROM organizations WHERE id = {target_id}')
    conn.commit()
    print(f"Sucesso! ID {target_id} ('{rows[0][1]}') removido.")
else:
    print("Apenas uma empresa encontrada ou nenhuma. Nada para apagar.")
conn.close()
