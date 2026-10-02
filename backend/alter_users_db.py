import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'crime_nexus.db')
conn = sqlite3.connect(db_path)

def add_column(conn, table, col_name, col_type):
    try:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type}')
        print(f'Added {col_name} column to {table}')
    except sqlite3.OperationalError as e:
        print(f'Column {col_name} already exists or error:', e)

add_column(conn, 'users', 'name', 'TEXT')
add_column(conn, 'users', 'phone', 'TEXT')
add_column(conn, 'users', 'profile_picture_url', 'TEXT')

conn.close()
