import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, r'c:\Users\ALTAMASH TABREJ\Desktop\sih26\sih-investigation-platform\backend')

from api.evidence import process_evidence_background
from services.database import get_db
from services.storage_service import STORAGE_DIR

async def retry_failed():
    db = await get_db()
    cursor = await db.execute('SELECT evidence_id, case_id, storage_path, mime_type FROM evidence WHERE status = "failed"')
    rows = await cursor.fetchall()
    await db.close()
    
    print(f'Found {len(rows)} failed records.')
    
    for row in rows:
        file_path = STORAGE_DIR.parent / row['storage_path']
        print(f'Reprocessing {row["evidence_id"]} at {file_path}')
        await process_evidence_background(row['case_id'], row['evidence_id'], file_path, row['mime_type'])
    
    print('Done reprocessing.')

if __name__ == '__main__':
    asyncio.run(retry_failed())
