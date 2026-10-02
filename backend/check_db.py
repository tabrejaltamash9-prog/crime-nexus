import sqlite3

def check_db():
    conn = sqlite3.connect('data/crime_nexus.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    for table_name, schema in tables:
        print(f"Table: {table_name}")
        print(schema)
        print("-" * 20)

if __name__ == '__main__':
    check_db()
