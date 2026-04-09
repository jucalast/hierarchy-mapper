import sqlite3
import os

db_path = 'intelligence.db'
if not os.path.exists(db_path):
    print("Banco não encontrado!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Apaga TUDO que cheire a SPCOM
cursor.execute("DELETE FROM organizations WHERE lower(name) LIKE '%spcom%' OR cnpj = '01123152000144' OR cnpj = '01.123.152/0001-44'")
rows_deleted = cursor.rowcount

# 2. Insere o registro mestre
cursor.execute("INSERT INTO organizations (id, name, cnpj, pipedrive_id, domain) VALUES (27, 'SPCom Global', '01123152000144', 805, 'spcomglobal.com.br')")

conn.commit()
conn.close()

print(f"Limpeza concluída! Registros antigos removidos: {rows_deleted}")
print("Registro Mestre (ID 27) inserido com sucesso.")
