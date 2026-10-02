import asyncio
import os
import sqlite3
from pathlib import Path

DATABASE_DIR = Path(__file__).resolve().parent / "data"
DATABASE_PATH = DATABASE_DIR / "crime_nexus.db"

async def alter_db():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check if source_type column exists
        cursor.execute("PRAGMA table_info(evidence)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "source_type" not in columns:
            print("Adding source_type column to evidence table...")
            cursor.execute("ALTER TABLE evidence ADD COLUMN source_type TEXT DEFAULT 'unknown'")
            conn.commit()
            print("Column added successfully.")
        else:
            print("Column source_type already exists.")
            
        conn.close()
    except Exception as e:
        print(f"Error altering database: {e}")

if __name__ == "__main__":
    asyncio.run(alter_db())
