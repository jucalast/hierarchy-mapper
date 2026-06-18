import sqlite3

conn = sqlite3.connect('intelligence.db')
cur = conn.cursor()

# Mostra os dois registros antes
cur.execute(
    "SELECT id, contact_identifier, contact_name, fetched_at FROM contact_conversation_cache "
    "WHERE contact_name = 'Giovanna De Domenico'"
)
rows = cur.fetchall()
print("Antes:")
for r in rows:
    print(r)

# Mantém o mais recente (maior id = fetched_at mais recente), apaga o mais antigo
# id=11 tem '5519971492452', id=12 tem '19971492452'
# O correto (com DDI completo) é o 11; o 12 é o duplicado sem 55
cur.execute("DELETE FROM contact_conversation_cache WHERE id = 12")
conn.commit()

# Confirma
cur.execute(
    "SELECT id, contact_identifier, contact_name, fetched_at FROM contact_conversation_cache "
    "WHERE contact_name = 'Giovanna De Domenico'"
)
rows = cur.fetchall()
print("\nApós limpeza:")
for r in rows:
    print(r)

conn.close()
print("\nOK — duplicata removida.")
