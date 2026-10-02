import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'crime_nexus.db')
conn = sqlite3.connect(db_path)
try:
    conn.execute('ALTER TABLE evidence ADD COLUMN extracted_text TEXT DEFAULT ""')
    print('Added extracted_text column')
except sqlite3.OperationalError as e:
    print('Column already exists or error:', e)
conn.close()
