import sqlite3
conn = sqlite3.connect('c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/intelligence.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", cur.fetchall())
