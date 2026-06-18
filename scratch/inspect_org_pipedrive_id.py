import sqlite3

def inspect():
    conn = sqlite3.connect("backend/intelligence.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, cnpj, domain, pipedrive_id FROM organizations WHERE id = 268;")
    print(cursor.fetchone())
    conn.close()

if __name__ == "__main__":
    inspect()
