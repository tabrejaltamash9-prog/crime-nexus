"""
Evidence Management API Routes.
Provides endpoints for uploading, listing, and verifying evidence integrity.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
import logging
import json
import mimetypes

logger = logging.getLogger(__name__)

from models.schemas import EvidenceResponse, EvidenceListResponse, EvidenceVerifyResponse, ReindexResponse
from services.database import get_db
from services.storage_service import store_file, compute_sha256, STORAGE_DIR
from services.ledger_service import record_event, verify_chain, get_evidence_history
from services.ocr_service import extract_text_from_document
from services.audio_service import extract_transcript_from_audio
from services.nlp_service import extract_entities_and_relations
from services.entity_resolution import resolve_entities
import services.neo4j_service as neo4j_service

from fastapi import Depends
import uuid
from services.auth_utils import get_current_user
from services import ingest_service

router = APIRouter(prefix="/evidence", tags=["Evidence"])

# Max upload size: 50 MB
MAX_UPLOAD_SIZE = 50 * 1024 * 1024


@router.post("/upload", response_model=EvidenceResponse, status_code=201)
async def upload_evidence(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    case_id: str = Form(...),
    original_filename: Optional[str] = Form(""),
    original_mime_type: Optional[str] = Form("application/octet-stream"),
    original_sha256: str = Form(...),
    source_type: Optional[str] = Form("unknown"),
    uploader: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a piece of evidence to a case.
    Computes SHA-256 hash server-side and stores metadata in SQLite.
    """
    uploader_name = current_user.get("username", "system")
    if not original_mime_type:
        original_mime_type = file.content_type or "application/octet-stream"
    if not original_filename:
        original_filename = file.filename or "uploaded_file"
    
    # Verify case exists
    db = await get_db()
    try:
        cursor = await db.execute("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")
    finally:
        await db.close()

    # Read file contents
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50 MB.")

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Store file locally and compute hash of the blob (storage hash)
    result = await store_file(
        case_id=case_id,
        file_bytes=file_bytes,
        original_filename=file.filename or "uploaded_file.bin",
        mime_type=original_mime_type,
    )

    now = datetime.now(timezone.utc).isoformat()
    evidence_id = result["evidence_id"]
    storage_sha256 = result["sha256_hash"]

    db = await get_db()
    try:
        # Save metadata to database
        await db.execute(
            """INSERT INTO evidence 
               (evidence_id, case_id, filename, original_filename, storage_path, encrypted_storage_path,
                encryption_algorithm, iv, mime_type, size, uploader, uploaded_at, original_sha256, sha256_hash, status, source_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence_id,
                case_id,
                result["filename"],
                original_filename,
                result["storage_path"],
                result["storage_path"],
                "NONE",
                "",
                original_mime_type,
                result["size"],
                uploader_name,
                now,
                original_sha256,
                storage_sha256,
                "uploaded",
                source_type,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    # Record UPLOAD event in the integrity ledger
    await record_event(
        case_id=case_id,
        evidence_id=evidence_id,
        evidence_hash=original_sha256,
        action="UPLOAD",
        actor=uploader_name,
        details=f"Uploaded {original_filename} ({result['size']} bytes)",
    )

    background_tasks.add_task(
        process_evidence_background, 
        case_id, 
        evidence_id, 
        STORAGE_DIR.parent / result["storage_path"], 
        original_mime_type
    )

    return EvidenceResponse(
        evidenceId=evidence_id,
        caseId=case_id,
        filename=result["filename"],
        originalFilename=original_filename,
        storagePath=result["storage_path"],
        mimeType=original_mime_type,
        size=result["size"],
        uploader=uploader_name,
        uploadedAt=now,
        originalSha256=original_sha256,
        storageSha256=storage_sha256,
        status="uploaded"
    )

@router.post("/person-photo-upload", response_model=Dict[str, Any], status_code=201)
async def upload_person_photo(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    case_id: str = Form(...),
    original_sha256: str = Form(...),
    metadata: str = Form(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a person photograph, extract features, and store structured metadata.
    """
    uploader_name = current_user.get("username", "system")
    meta_dict = json.loads(metadata)
    
    db = await get_db()
    try:
        # Verify case exists
        cursor = await db.execute("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")
            
        # Duplicate check within the same case
        cursor = await db.execute("SELECT person_record_id FROM person_records WHERE photo_hash = ? AND case_id = ?", (original_sha256, case_id))
        if await cursor.fetchone():
            raise HTTPException(status_code=409, detail="Exact duplicate photograph already uploaded for this case.")
    finally:
        await db.close()

    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(image_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum 50 MB.")

    from api.face import _get_face_services
    (detect_faces, get_image_dimensions, normalize_embedding, validate_embedding,
     assess_quality, qdrant_face_store, neo4j_person, entity_merge) = _get_face_services()

    # Detect faces
    try:
        detected = detect_faces(image_bytes)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    if not detected:
        raise HTTPException(status_code=400, detail="No faces detected in the image.")
        
    primary_face = max(detected, key=lambda f: f.det_score)
    img_h, img_w = get_image_dimensions(image_bytes)
    
    quality = assess_quality(
        bbox=primary_face.bbox,
        det_score=primary_face.det_score,
        landmarks=primary_face.landmarks,
        image_height=img_h,
        image_width=img_w,
    )
    
    if not quality.passed or not validate_embedding(primary_face.embedding):
        raise HTTPException(status_code=400, detail=f"Face quality too low: {quality.rejection_reason}")
        
    embedding = normalize_embedding(primary_face.embedding)
    face_id = str(uuid.uuid4())
    person_record_id = str(uuid.uuid4())
    
    # Store the photo file
    result = await store_file(
        case_id=case_id,
        file_bytes=image_bytes,
        original_filename=file.filename or "photo.jpg",
        mime_type=file.content_type or "image/jpeg",
    )
    photo_url = f"/evidence/{result['evidence_id']}/download"

    now = datetime.now(timezone.utc).isoformat()
    
    # Store in SQLite evidence table
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO evidence 
               (evidence_id, case_id, filename, original_filename, storage_path, encrypted_storage_path,
                encryption_algorithm, iv, mime_type, size, uploader, uploaded_at, original_sha256, sha256_hash, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result["evidence_id"], case_id, result["filename"], file.filename or "photo.jpg",
                result["storage_path"], result["storage_path"], "NONE", "",
                file.content_type or "image/jpeg", result["size"], uploader_name,
                now, original_sha256, result["sha256_hash"], "uploaded",
            ),
        )
        await db.commit()
    finally:
        await db.close()

    # Store in Qdrant
    try:
        await qdrant_face_store.upsert_face(
            face_id=face_id,
            embedding=embedding,
            case_id=case_id,
            evidence_id=result["evidence_id"],
            person_id=None,
            role_in_case=meta_dict.get("role_in_case", "unknown"),
            det_score=primary_face.det_score,
            source_photo_hash=original_sha256,
            officer_id=uploader_name,
        )
    except Exception as e:
        logger.error(f"Failed to store face {face_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to store face embedding")

    # Store in SQLite person_records
    now = datetime.now(timezone.utc).isoformat()
    
    age_approx = meta_dict.get("age_approx")
    try:
        age_approx = int(age_approx) if age_approx else None
    except ValueError:
        age_approx = None

    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO person_records 
               (person_record_id, face_id, case_id, full_name, aliases, age_approx, gender, id_numbers,
                height, build, complexion, distinguishing_marks, role_in_case, description, pose,
                photo_url, photo_hash, photo_quality_score, uploaded_by, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                person_record_id, face_id, case_id, meta_dict.get("full_name"), meta_dict.get("aliases"),
                age_approx, meta_dict.get("gender"), meta_dict.get("id_numbers"), meta_dict.get("height"),
                meta_dict.get("build"), meta_dict.get("complexion"), meta_dict.get("distinguishing_marks"),
                meta_dict.get("role_in_case", "Suspect"), meta_dict.get("description", ""), meta_dict.get("pose", "frontal"),
                photo_url, original_sha256, float(primary_face.det_score), uploader_name, now
            )
        )
        await db.commit()
    finally:
        await db.close()

    return {"status": "success", "person_record_id": person_record_id, "face_id": face_id}


def _build_evidence_url(evidence_id: str) -> str:
    """Build the download URL for an evidence file."""
    return f"http://localhost:8000/evidence/{evidence_id}/download"


async def _update_evidence_status(evidence_id: str, **fields):
    """Helper to update one or more fields on the evidence row."""
    if not fields:
        return
    set_clauses = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [evidence_id]
    db = await get_db()
    try:
        await db.execute(
            f"UPDATE evidence SET {set_clauses} WHERE evidence_id = ?",
            values,
        )
        await db.commit()
    finally:
        await db.close()


async def process_evidence_background(case_id: str, evidence_id: str, file_path: Path, mime_type: str):
    """
    Background task: OCR → NLP/Neo4j → RAG Indexing.
    
    Each phase updates its own granular status column:
      - ocr_status:    pending → processing → completed / failed
      - neo4j_status:  pending → processing → indexed / failed
      - qdrant_status: pending → processing → indexed / failed
    
    The overall 'status' column is set to 'processed' only when all phases complete.
    """
    logger.info(f"Starting background processing for evidence {evidence_id}...")
    extracted_text = ""
    ocr_ok = False
    
    # ── Phase 1: OCR / Text Extraction ──
    try:
        await _update_evidence_status(evidence_id, status='processing', ocr_status='processing')
        
        if mime_type.startswith("audio/") or mime_type.startswith("video/"):
            extracted_text = await extract_transcript_from_audio(file_path)
        else:
            extracted_text = await extract_text_from_document(file_path, mime_type)
        
        await _update_evidence_status(
            evidence_id,
            ocr_status='completed',
            extracted_text=extracted_text,
        )
        ocr_ok = True
        logger.info(f"OCR completed for {evidence_id}: {len(extracted_text)} chars")
        
    except Exception as e:
        logger.error(f"OCR failed for {evidence_id}: {e}")
        await _update_evidence_status(
            evidence_id,
            status='failed',
            ocr_status='failed',
            index_error=f"OCR failed: {str(e)}",
        )
        return  # Cannot proceed without text
    
    if not extracted_text:
        await _update_evidence_status(
            evidence_id,
            neo4j_status='not_applicable',
            qdrant_status='not_applicable'
        )
    
    # ── Phase 2: NLP / Neo4j Entity Graph ──
    if extracted_text:
        try:
            await _update_evidence_status(evidence_id, neo4j_status='processing')
            
            nlp_data = await extract_entities_and_relations(extracted_text)
            extracted_ents = nlp_data.get("entities", [])
            extracted_rels = nlp_data.get("relations", [])
            
            existing_nodes = neo4j_service.get_all_nodes(case_id)
            resolution = resolve_entities(extracted_ents, existing_nodes)
            
            created_nodes_map = {}
            for ext_ent in resolution["new_entities"]:
                new_node = neo4j_service.create_node(
                    case_id=case_id,
                    text=ext_ent["text"],
                    ent_type=ext_ent["type"],
                    confidence=ext_ent.get("confidence", 0.8),
                    evidence_id=evidence_id
                )
                if new_node:
                    created_nodes_map[ext_ent["text"]] = new_node["id"]
                    
            for ext_ent, existing_id in resolution["merges"]:
                created_nodes_map[ext_ent["text"]] = existing_id
                
            for review_item in resolution["review_queue"]:
                neo4j_service.add_to_review_queue(case_id, review_item)
                
            for rel in extracted_rels:
                from_id = created_nodes_map.get(rel["from"])
                to_id = created_nodes_map.get(rel["to"])
                if from_id and to_id:
                    neo4j_service.create_edge(
                        case_id=case_id,
                        from_id=from_id,
                        to_id=to_id,
                        edge_type=rel["type"],
                        confidence=rel.get("confidence", 0.8),
                        evidence_id=evidence_id
                    )
            
            await _update_evidence_status(evidence_id, neo4j_status='indexed')
            logger.info(f"Neo4j indexing completed for {evidence_id}")
            
        except Exception as e:
            logger.error(f"Neo4j indexing failed for {evidence_id}: {e}")
            await _update_evidence_status(
                evidence_id,
                neo4j_status='failed',
                index_error=f"Neo4j failed: {str(e)}",
            )
            # Continue to Qdrant — Neo4j failure shouldn't block RAG
    
    # ── Phase 3: RAG / Qdrant Vector Indexing ──
    if ocr_ok and extracted_text:
        try:
            await _update_evidence_status(evidence_id, qdrant_status='processing')
            
            # Get original filename for citation tracking
            db = await get_db()
            try:
                cursor = await db.execute(
                    "SELECT original_filename, doc_version FROM evidence WHERE evidence_id = ?",
                    (evidence_id,)
                )
                row = await cursor.fetchone()
                original_filename = row["original_filename"] if row else "unknown"
                doc_version = row["doc_version"] if row else 1
            finally:
                await db.close()
            
            file_url = _build_evidence_url(evidence_id)
            
            total_chunks = await ingest_service.process_and_index_evidence(
                document_id=evidence_id,
                case_id=case_id,
                file_name=original_filename,
                file_url=file_url,
                extracted_text=extracted_text,
                evidence_type=mime_type,
                doc_version=doc_version,
            )
            
            now = datetime.now(timezone.utc).isoformat()
            await _update_evidence_status(
                evidence_id,
                qdrant_status='indexed',
                chunk_count=total_chunks,
                last_indexed_at=now,
                index_error=None,
            )
            logger.info(f"Qdrant indexing completed for {evidence_id}: {total_chunks} chunks")
            
        except Exception as e:
            logger.error(f"Qdrant indexing failed for {evidence_id}: {e}")
            await _update_evidence_status(
                evidence_id,
                qdrant_status='failed',
                index_error=f"Qdrant indexing failed: {str(e)}",
            )
    
    # ── Phase 4: Face Recognition (images only) ──
    if mime_type.startswith("image/"):
        try:
            logger.info(f"Running face detection for image evidence {evidence_id}...")
            # Read the file bytes for face processing
            face_file_path = STORAGE_DIR.parent / str(file_path) if not file_path.is_absolute() else file_path
            with open(face_file_path, "rb") as f:
                face_image_bytes = f.read()
            
            # Get uploader info
            db = await get_db()
            try:
                cursor = await db.execute(
                    "SELECT uploader FROM evidence WHERE evidence_id = ?",
                    (evidence_id,)
                )
                row = await cursor.fetchone()
                uploader = row["uploader"] if row else "system"
            finally:
                await db.close()
            
            from api.face import process_face_background
            await process_face_background(
                case_id=case_id,
                evidence_id=evidence_id,
                image_bytes=face_image_bytes,
                officer_id=uploader,
                role_in_case="unknown",
            )
            logger.info(f"Face detection completed for {evidence_id}")
        except Exception as e:
            logger.warning(f"Face detection failed for {evidence_id} (non-blocking): {e}")
    
    # ── Finalize overall status ──
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT ocr_status, neo4j_status, qdrant_status FROM evidence WHERE evidence_id = ?",
            (evidence_id,)
        )
        row = await cursor.fetchone()
        if row:
            all_ok = (
                row["ocr_status"] == 'completed'
                and row["neo4j_status"] in ('indexed', 'pending', 'not_applicable')
                and row["qdrant_status"] in ('indexed', 'pending', 'not_applicable')
            )
            any_failed = 'failed' in (row["ocr_status"], row["neo4j_status"], row["qdrant_status"])
            
            if all_ok and not any_failed:
                final_status = 'processed'
            elif any_failed:
                final_status = 'failed'
            else:
                final_status = 'processing'
            
            await db.execute(
                "UPDATE evidence SET status = ? WHERE evidence_id = ?",
                (final_status, evidence_id)
            )
            await db.commit()
            logger.info(f"Background processing finalized for {evidence_id}: status={final_status}")
    finally:
        await db.close()

@router.post("/{evidence_id}/reprocess", response_model=ReindexResponse, status_code=202)
async def reprocess_evidence(evidence_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger full OCR + RAG pipeline for an evidence item.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT evidence_id, case_id, storage_path, mime_type, doc_version
               FROM evidence WHERE evidence_id = ?""",
            (evidence_id,),
        )
        row = await cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Evidence not found")
            
        new_version = (row["doc_version"] or 1) + 1
        
        await db.execute(
            """UPDATE evidence 
               SET doc_version = ?, ocr_status = 'pending', qdrant_status = 'pending', neo4j_status = 'pending',
                   status = 'processing', index_error = NULL
               WHERE evidence_id = ?""",
            (new_version, evidence_id),
        )
        await db.commit()
        
        case_id = row["case_id"]
        storage_path = row["storage_path"]
        mime_type = row["mime_type"]
        
    finally:
        await db.close()
    
    file_path = STORAGE_DIR.parent / storage_path
    background_tasks.add_task(
        process_evidence_background, 
        case_id, 
        evidence_id, 
        file_path, 
        mime_type
    )
    
    return ReindexResponse(
        status="accepted",
        evidence_id=evidence_id,
        doc_version=new_version,
        message=f"Reprocessing enqueued (version {new_version}). "
                f"Monitor status via GET /evidence/{evidence_id}.",
    )


@router.post("/{evidence_id}/index", response_model=ReindexResponse, status_code=202)
async def reindex_evidence(evidence_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger re-indexing for an evidence item.
    
    Use cases:
      - Recovery from a failed Qdrant/Neo4j indexing attempt
      - Re-index after OCR corrections or metadata changes
      - Re-index after embedding model changes
    
    Precondition: ocr_status must be 'completed' — we don't re-run OCR.
    Behavior:
      1. Validate OCR has completed
      2. Increment doc_version (makes old chunk IDs stale)
      3. Reset qdrant_status and neo4j_status to 'processing'
      4. Enqueue the RAG indexing worker in the background
      5. Return 202 Accepted immediately
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT evidence_id, case_id, ocr_status, extracted_text,
                      original_filename, mime_type, doc_version
               FROM evidence WHERE evidence_id = ?""",
            (evidence_id,),
        )
        row = await cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Evidence not found")
        
        if row["ocr_status"] != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot re-index: OCR status is '{row['ocr_status']}', must be 'completed'. "
                       f"Wait for OCR to finish or re-upload the evidence."
            )
        
        if not row["extracted_text"]:
            raise HTTPException(
                status_code=422,
                detail="Cannot re-index: no extracted text available."
            )
        
        # Increment version for idempotent re-indexing
        new_version = (row["doc_version"] or 1) + 1
        
        await db.execute(
            """UPDATE evidence 
               SET doc_version = ?, qdrant_status = 'processing', neo4j_status = 'processing',
                   status = 'processing', index_error = NULL
               WHERE evidence_id = ?""",
            (new_version, evidence_id),
        )
        await db.commit()
        
        case_id = row["case_id"]
        extracted_text = row["extracted_text"]
        original_filename = row["original_filename"]
        mime_type = row["mime_type"]
        
    finally:
        await db.close()
    
    # Enqueue re-indexing as a background task
    async def _reindex_worker():
        """Background worker for re-indexing (Qdrant + Neo4j)."""
        # Phase 1: Qdrant re-indexing
        try:
            await _update_evidence_status(evidence_id, qdrant_status='processing')
            
            file_url = _build_evidence_url(evidence_id)
            total_chunks = await ingest_service.process_and_index_evidence(
                document_id=evidence_id,
                case_id=case_id,
                file_name=original_filename,
                file_url=file_url,
                extracted_text=extracted_text,
                evidence_type=mime_type,
                doc_version=new_version,
            )
            
            now = datetime.now(timezone.utc).isoformat()
            await _update_evidence_status(
                evidence_id,
                qdrant_status='indexed',
                chunk_count=total_chunks,
                last_indexed_at=now,
                index_error=None,
            )
            logger.info(f"Re-index Qdrant completed for {evidence_id}: {total_chunks} chunks (v{new_version})")
            
        except Exception as e:
            logger.error(f"Re-index Qdrant failed for {evidence_id}: {e}")
            await _update_evidence_status(
                evidence_id,
                qdrant_status='failed',
                index_error=f"Re-index Qdrant failed: {str(e)}",
            )
        
        # Phase 2: Neo4j re-indexing
        try:
            await _update_evidence_status(evidence_id, neo4j_status='processing')
            
            nlp_data = await extract_entities_and_relations(extracted_text)
            extracted_ents = nlp_data.get("entities", [])
            extracted_rels = nlp_data.get("relations", [])
            
            existing_nodes = neo4j_service.get_all_nodes(case_id)
            resolution = resolve_entities(extracted_ents, existing_nodes)
            
            created_nodes_map = {}
            for ext_ent in resolution["new_entities"]:
                new_node = neo4j_service.create_node(
                    case_id=case_id,
                    text=ext_ent["text"],
                    ent_type=ext_ent["type"],
                    confidence=ext_ent.get("confidence", 0.8),
                    evidence_id=evidence_id,
                )
                if new_node:
                    created_nodes_map[ext_ent["text"]] = new_node["id"]
            
            for ext_ent, existing_id in resolution["merges"]:
                created_nodes_map[ext_ent["text"]] = existing_id
            
            for review_item in resolution["review_queue"]:
                neo4j_service.add_to_review_queue(case_id, review_item)
            
            for rel in extracted_rels:
                from_id = created_nodes_map.get(rel["from"])
                to_id = created_nodes_map.get(rel["to"])
                if from_id and to_id:
                    neo4j_service.create_edge(
                        case_id=case_id,
                        from_id=from_id,
                        to_id=to_id,
                        edge_type=rel["type"],
                        confidence=rel.get("confidence", 0.8),
                        evidence_id=evidence_id,
                    )
            
            await _update_evidence_status(evidence_id, neo4j_status='indexed')
            logger.info(f"Re-index Neo4j completed for {evidence_id}")
            
        except Exception as e:
            logger.error(f"Re-index Neo4j failed for {evidence_id}: {e}")
            await _update_evidence_status(
                evidence_id,
                neo4j_status='failed',
                index_error=f"Re-index Neo4j failed: {str(e)}",
            )
        
        # Finalize overall status
        db2 = await get_db()
        try:
            cursor2 = await db2.execute(
                "SELECT qdrant_status, neo4j_status FROM evidence WHERE evidence_id = ?",
                (evidence_id,),
            )
            row2 = await cursor2.fetchone()
            if row2:
                any_failed = 'failed' in (row2["qdrant_status"], row2["neo4j_status"])
                final = 'failed' if any_failed else 'processed'
                await db2.execute(
                    "UPDATE evidence SET status = ? WHERE evidence_id = ?",
                    (final, evidence_id),
                )
                await db2.commit()
        finally:
            await db2.close()
    
    background_tasks.add_task(_reindex_worker)
    
    logger.info(f"Re-index enqueued for {evidence_id} (version {new_version})")
    
    return ReindexResponse(
        status="accepted",
        evidence_id=evidence_id,
        doc_version=new_version,
        message=f"Re-indexing enqueued (version {new_version}). "
                f"Monitor status via GET /evidence/{evidence_id}.",
    )


@router.get("/case/{case_id}", response_model=EvidenceListResponse)
async def list_evidence(case_id: str):
    """List all evidence items for a case."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT case_id FROM cases WHERE case_id = ?", (case_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Case not found")

        cursor = await db.execute(
            """SELECT evidence_id, case_id, filename, original_filename, storage_path,
                      encryption_algorithm, iv, mime_type, size, uploader, uploaded_at,
                      original_sha256, sha256_hash, status, extracted_text,
                      ocr_status, qdrant_status, neo4j_status, doc_version, chunk_count,
                      last_indexed_at, index_error, source_type
               FROM evidence WHERE case_id = ? ORDER BY uploaded_at DESC""",
            (case_id,),
        )
        rows = await cursor.fetchall()

        evidence = [
            EvidenceResponse(
                evidenceId=r["evidence_id"],
                caseId=r["case_id"],
                filename=r["filename"],
                originalFilename=r["original_filename"],
                storagePath=r["storage_path"],
                mimeType=r["mime_type"],
                size=r["size"],
                uploader=r["uploader"],
                uploadedAt=r["uploaded_at"],
                originalSha256=r["original_sha256"] if r["original_sha256"] else r["sha256_hash"],
                storageSha256=r["sha256_hash"],
                status=r["status"],
                extractedText=r["extracted_text"],
                ocrStatus=r["ocr_status"],
                qdrantStatus=r["qdrant_status"],
                neo4jStatus=r["neo4j_status"],
                docVersion=r["doc_version"],
                chunkCount=r["chunk_count"],
                lastIndexedAt=r["last_indexed_at"],
                indexError=r["index_error"],
                sourceType=r["source_type"] if "source_type" in r.keys() else None,
            )
            for r in rows
        ]

        return EvidenceListResponse(evidence=evidence, total=len(evidence))
    finally:
        await db.close()


@router.get("/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(evidence_id: str):
    """Get a single evidence item by ID."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT evidence_id, case_id, filename, original_filename, storage_path,
                      encryption_algorithm, iv, mime_type, size, uploader, uploaded_at,
                      original_sha256, sha256_hash, status, extracted_text,
                      ocr_status, qdrant_status, neo4j_status, doc_version, chunk_count,
                      last_indexed_at, index_error, source_type
               FROM evidence WHERE evidence_id = ?""",
            (evidence_id,),
        )
        r = await cursor.fetchone()

        if not r:
            raise HTTPException(status_code=404, detail="Evidence not found")

        return EvidenceResponse(
            evidenceId=r["evidence_id"],
            caseId=r["case_id"],
            filename=r["filename"],
            originalFilename=r["original_filename"],
            storagePath=r["storage_path"],
            mimeType=r["mime_type"],
            size=r["size"],
            uploader=r["uploader"],
            uploadedAt=r["uploaded_at"],
            originalSha256=r["original_sha256"] if r["original_sha256"] else r["sha256_hash"],
            storageSha256=r["sha256_hash"],
            status=r["status"],
            extractedText=r["extracted_text"],
            ocrStatus=r["ocr_status"],
            qdrantStatus=r["qdrant_status"],
            neo4jStatus=r["neo4j_status"],
            docVersion=r["doc_version"],
            chunkCount=r["chunk_count"],
            lastIndexedAt=r["last_indexed_at"],
            indexError=r["index_error"],
            sourceType=r["source_type"] if "source_type" in r.keys() else None,
        )
    finally:
        await db.close()


@router.get("/{evidence_id}/verify", response_model=EvidenceVerifyResponse)
async def verify_evidence(evidence_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT evidence_id, storage_path, sha256_hash, original_sha256 FROM evidence WHERE evidence_id = ?",
            (evidence_id,),
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Evidence not found")

        stored_hash = row["sha256_hash"]
        original_sha256 = row["original_sha256"] or stored_hash
        file_path = STORAGE_DIR.parent / row["storage_path"]

        if not file_path.exists():
            raise HTTPException(status_code=500, detail="Evidence file missing from storage")

        file_bytes = file_path.read_bytes()
        computed_hash = compute_sha256(file_bytes)
        file_valid = (stored_hash == computed_hash)

        now = datetime.now(timezone.utc).isoformat()

        case_cursor = await db.execute("SELECT case_id FROM evidence WHERE evidence_id = ?", (evidence_id,))
        case_row = await case_cursor.fetchone()
    finally:
        await db.close()

    ledger_valid = None
    if case_row:
        chain_result = await verify_chain(case_row["case_id"])
        ledger_valid = chain_result["valid"]

    # Record VERIFY event in the ledger
    if case_row:
        await record_event(
            case_id=case_row["case_id"],
            evidence_id=evidence_id,
            evidence_hash=computed_hash,
            action="VERIFY",
            actor="system",
            details=f"File: {'PASS' if file_valid else 'FAIL'}, "
                    f"Chain: {'PASS' if ledger_valid else 'FAIL'}",
        )

    return EvidenceVerifyResponse(
        evidenceId=evidence_id,
        storedHash=stored_hash,
        computedHash=computed_hash,
        integrityValid=file_valid,
        ledgerValid=ledger_valid,
        verifiedAt=now
    )


@router.get("/{evidence_id}/download")
async def download_evidence(evidence_id: str):
    """Download an evidence file or photo by evidence_id."""
    db = await get_db()
    file_path = None
    filename = None
    mime_type = None

    try:
        # 1. First check evidence table
        cursor = await db.execute(
            "SELECT storage_path, original_filename, mime_type, case_id FROM evidence WHERE evidence_id = ?",
            (evidence_id,),
        )
        row = await cursor.fetchone()

        if row:
            storage_path_str = row["storage_path"]
            filename = row["original_filename"] or f"evidence_{evidence_id}"
            mime_type = row["mime_type"]

            candidates = [
                STORAGE_DIR.parent / storage_path_str,
                STORAGE_DIR / storage_path_str,
                Path(storage_path_str),
                STORAGE_DIR / (row["case_id"] or "") / Path(storage_path_str).name,
            ]
            for candidate in candidates:
                if candidate.is_file():
                    file_path = candidate
                    break

        # 2. If not found in evidence table or file not found on disk, check person_records
        if not file_path:
            cursor = await db.execute(
                "SELECT case_id, photo_url FROM person_records WHERE photo_url LIKE ? OR person_record_id = ? OR face_id = ?",
                (f"%{evidence_id}%", evidence_id, evidence_id)
            )
            person_row = await cursor.fetchone()
            if person_row:
                case_id = person_row["case_id"]
                for ext in ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG', '.webp']:
                    candidate = STORAGE_DIR / case_id / f"{evidence_id}{ext}"
                    if candidate.is_file():
                        file_path = candidate
                        filename = f"photo_{evidence_id}{ext}"
                        break

        # 3. Recursive search in STORAGE_DIR for any file containing evidence_id
        if not file_path:
            for candidate in STORAGE_DIR.glob(f"**/*{evidence_id}*"):
                if candidate.is_file():
                    file_path = candidate
                    filename = candidate.name
                    break

        # 4. Fallback search in backend data directory (e.g. avatars, etc.)
        if not file_path:
            data_dir = STORAGE_DIR.parent
            for candidate in data_dir.glob(f"**/*{evidence_id}*"):
                if candidate.is_file() and not candidate.name.endswith(('.db', '.wal', '.shm', '.index', '.log')):
                    file_path = candidate
                    filename = candidate.name
                    break

        if not file_path or not file_path.exists():
            raise HTTPException(status_code=404, detail="Evidence not found")

        if not mime_type or mime_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(str(file_path))
            mime_type = guessed or "image/jpeg"

        return FileResponse(
            path=str(file_path),
            filename=filename or file_path.name,
            media_type=mime_type,
        )
    finally:
        await db.close()


@router.delete("/{evidence_id}", status_code=204)
async def delete_evidence(evidence_id: str):
    """Delete an evidence item and its stored file."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT storage_path FROM evidence WHERE evidence_id = ?", (evidence_id,))
        row = await cursor.fetchone()
        if row:
            file_path = STORAGE_DIR.parent / row["storage_path"]
            if file_path.exists():
                file_path.unlink()
        await db.execute("DELETE FROM evidence WHERE evidence_id = ?", (evidence_id,))
        await db.commit()
    finally:
        await db.close()

