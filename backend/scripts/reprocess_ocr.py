import asyncio
import logging
import os
import sys
from pathlib import Path

# Add backend dir to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.database import get_db
from services.storage_service import STORAGE_DIR
from services.ocr_service import extract_text_from_document
from services import ingest_service
from services import vector_store
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reprocess_ocr():
    db = await get_db()
    try:
        # Get all evidence that have a local storage path and aren't audio/video
        cursor = await db.execute(
            """SELECT evidence_id, case_id, filename, original_filename, storage_path, mime_type, doc_version, ocr_status, extracted_text
               FROM evidence
               WHERE mime_type NOT LIKE 'audio/%' AND mime_type NOT LIKE 'video/%'"""
        )
        rows = await cursor.fetchall()
        
        if not rows:
            logger.info("No documents found for reprocessing.")
            return

        logger.info(f"Found {len(rows)} documents for reprocessing.")
        
        for row in rows:
            evidence_id = row["evidence_id"]
            case_id = row["case_id"]
            storage_path = row["storage_path"]
            mime_type = row["mime_type"]
            original_filename = row["original_filename"]
            old_version = row["doc_version"]
            new_version = (old_version or 1) + 1
            
            file_path = STORAGE_DIR.parent / storage_path
            if not file_path.exists():
                logger.warning(f"File not found for {evidence_id}: {file_path}, skipping.")
                continue

            logger.info(f"\n--- Reprocessing {evidence_id} ({original_filename}) ---")
            
            try:
                # 1. Run new OCR (Surya via ocr_service)
                logger.info("Running new OCR extraction...")
                extracted_text = await extract_text_from_document(file_path, mime_type)
                
                # 2. Update DB with new text and version
                await db.execute(
                    """UPDATE evidence 
                       SET extracted_text = ?, doc_version = ?, ocr_status = 'completed', qdrant_status = 'processing'
                       WHERE evidence_id = ?""",
                    (extracted_text, new_version, evidence_id)
                )
                await db.commit()
                
                # 3. Re-index into Qdrant using ingest_service
                logger.info("Re-indexing layout-aware chunks...")
                # process_and_index_evidence automatically handles deleting the old vectors by doc_id
                file_url = f"http://localhost:8000/evidence/{evidence_id}/download"
                
                total_chunks = await ingest_service.process_and_index_evidence(
                    document_id=evidence_id,
                    case_id=case_id,
                    file_name=original_filename,
                    file_url=file_url,
                    extracted_text=extracted_text,
                    evidence_type=mime_type,
                    doc_version=new_version
                )
                
                now = datetime.now(timezone.utc).isoformat()
                await db.execute(
                    """UPDATE evidence 
                       SET qdrant_status = 'indexed', chunk_count = ?, last_indexed_at = ?, index_error = NULL
                       WHERE evidence_id = ?""",
                    (total_chunks, now, evidence_id)
                )
                await db.commit()
                logger.info(f"Successfully reprocessed {evidence_id}: {total_chunks} new chunks inserted.")
                
            except Exception as e:
                logger.error(f"Failed to reprocess {evidence_id}: {e}")
                await db.execute(
                    """UPDATE evidence 
                       SET index_error = ?, qdrant_status = 'failed'
                       WHERE evidence_id = ?""",
                    (str(e), evidence_id)
                )
                await db.commit()
                
    finally:
        await db.close()

if __name__ == "__main__":
    os.environ["OCR_ENGINE"] = "surya"  # Force Surya
    asyncio.run(reprocess_ocr())
