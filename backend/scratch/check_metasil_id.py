import sqlite3

conn = sqlite3.connect('intelligence.db')
cur = conn.cursor()
cur.execute("SELECT id, pipedrive_id, name FROM organizations WHERE name LIKE '%metasil%'")
for row in cur.fetchall():
    print(f"Local ID: {row[0]}, Pipedrive ID: {row[1]}, Name: {row[2]}")
