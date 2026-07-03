import sqlite3

def print_data():
    conn = sqlite3.connect("backend/intelligence.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, description, evidence, education, headline, source FROM employees WHERE company_id = 268;"
    )
    rows = cursor.fetchall()
    print("Employees data for org 268:")
    for row in rows:
        print(f"ID: {row[0]}, Name: {row[1]}")
        print(f"  Description (Bio): {row[2]}")
        print(f"  Evidence (IA):     {row[3]}")
        print(f"  Education:         {row[4]}")
        print(f"  Headline:          {row[5]}")
        print(f"  Source:            {row[6]}")
        print("-" * 50)
    conn.close()

if __name__ == "__main__":
    print_data()
