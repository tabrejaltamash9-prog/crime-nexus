"""
Face Recognition API Routes.

Provides endpoints for:
  - Mode A: Evidence photo upload with face matching (POST /face/evidence-upload)
  - Mode B: Standalone face lookup (POST /face/lookup)
  - Human review queue (GET /face/review-queue, POST /face/review/{id}/decide)
"""

import asyncio
import hashlib
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends

from models.schemas import (
    PhotoUploadResponse,
    FaceLookupResponse,
    FaceDetectionResult,
    FaceMatch,
    ReviewDecision,
    ReviewQueueItem,
    ReviewQueueResponse,
)
from services.auth_utils import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)

async def _enrich_linked_cases(linked_cases: list):
    if not linked_cases:
        return
    db = await get_db()
    try:
        for case in linked_cases:
            c_id = case.get("case_id")
            if c_id:
                row = await db.execute("SELECT title, status FROM cases WHERE case_id = ?", (c_id,))
                case_row = await row.fetchone()
                if case_row:
                    case["title"] = case_row["title"]
                    case["status"] = case_row["status"]
                else:
                    case["title"] = "Unknown Case"
                    case["status"] = "unknown"
    finally:
        await db.close()

router = APIRouter(prefix="/face", tags=["Face Recognition"])

# ── Thresholds from env ──────────────────────────────────────────────────────

MODE_A_THRESHOLD = float(os.environ.get("FACE_MATCH_THRESHOLD_MODE_A", "0.55"))
MODE_B_THRESHOLD = float(os.environ.get("FACE_MATCH_THRESHOLD_MODE_B", "0.65"))


# ── Lazy imports to avoid loading InsightFace at module level ────────────────

def _get_face_services():
    """Lazy-import face recognition services."""
    from services.face_recognition.detection import detect_faces, get_image_dimensions
    from services.face_recognition.embedding import normalize_embedding, validate_embedding
    from services.face_recognition.quality import assess_quality
    from services.face_recognition import qdrant_face_store
    from services.face_recognition import neo4j_person
    from services.face_recognition import entity_merge
    return detect_faces, get_image_dimensions, normalize_embedding, validate_embedding, assess_quality, qdrant_face_store, neo4j_person, entity_merge


# ── Mode A: Evidence Photo Upload ────────────────────────────────────────────

@router.post("/evidence-upload", response_model=PhotoUploadResponse, status_code=201)
async def face_evidence_upload(
    file: UploadFile = File(...),
    case_id: str = Form(...),
    role_in_case: str = Form("unknown"),
    current_user: dict = Depends(get_current_user),
):
    """
    Mode A: Upload a photo as evidence and run face detection + matching.
    
    Detects faces, extracts embeddings, searches for matches across other cases,
    and creates/updates Person nodes in the identity graph.
    """
    officer_id = current_user.get("username", "system")
    
    (detect_faces, get_image_dimensions, normalize_embedding, validate_embedding,
     assess_quality, qdrant_face_store, neo4j_person, entity_merge) = _get_face_services()
    
    # Read file
    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(image_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum 50 MB.")
    
    # Compute SHA-256 of source photo
    photo_hash = hashlib.sha256(image_bytes).hexdigest()
    
    # Check for duplicate
    try:
        existing = await qdrant_face_store.check_duplicate(photo_hash)
        if existing:
            return PhotoUploadResponse(
                faces_detected=0,
                faces=[],
                matches=[],
                merge_actions=[{"action": "duplicate", "existing_face_id": existing.get("face_id")}],
            )
    except Exception as e:
        logger.warning(f"Duplicate check failed (continuing): {e}")
    
    # Detect faces
    try:
        detected = detect_faces(image_bytes)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not detected:
        raise HTTPException(status_code=400, detail="No faces detected in the image.")
    
    # Get image dimensions for quality check
    img_h, img_w = get_image_dimensions(image_bytes)
    
    face_results = []
    all_matches = []
    merge_actions = []
    
    for face in detected:
        face_id = str(uuid.uuid4())
        
        # Quality check
        quality = assess_quality(
            bbox=face.bbox,
            det_score=face.det_score,
            landmarks=face.landmarks,
            image_height=img_h,
            image_width=img_w,
        )
        
        face_result = FaceDetectionResult(
            face_id=face_id,
            det_score=face.det_score,
            quality_passed=quality.passed,
            rejection_reason=quality.rejection_reason,
            bbox=face.bbox,
            face_area_ratio=quality.face_area_ratio,
        )
        face_results.append(face_result)
        
        # Skip storage for low-quality faces
        if not quality.passed or not validate_embedding(face.embedding):
            continue
        
        # Normalize and store embedding
        embedding = normalize_embedding(face.embedding)
        
        try:
            await qdrant_face_store.upsert_face(
                face_id=face_id,
                embedding=embedding,
                case_id=case_id,
                evidence_id=None,  # Evidence ID assigned separately by evidence upload flow
                person_id=None,
                role_in_case=role_in_case,
                det_score=face.det_score,
                source_photo_hash=photo_hash,
                officer_id=officer_id,
            )
        except Exception as e:
            logger.error(f"Failed to store face {face_id}: {e}")
            continue
        
        # Search for matches excluding same case
        try:
            matches = await qdrant_face_store.search_faces(
                query_embedding=embedding,
                limit=10,
                score_threshold=MODE_A_THRESHOLD,
                exclude_case_id=case_id,
            )
        except Exception as e:
            logger.error(f"Face search failed for {face_id}: {e}")
            matches = []
        
        # Process matches — create/update Person nodes
        for match in matches:
            matched_person_id = match.get("person_id")
            matched_case_id = match.get("case_id")
            
            # Build match response
            person_data = None
            linked_cases = []
            
            if matched_person_id:
                person_data = neo4j_person.get_person_with_cases(matched_person_id)
                if person_data:
                    linked_cases = person_data.get("linked_cases", [])
                    await _enrich_linked_cases(linked_cases)
            
            face_match = FaceMatch(
                person_id=matched_person_id,
                confidence=match.get("score", 0.0),
                canonical_name=person_data.get("canonical_name") if person_data else None,
                linked_cases=linked_cases,
                evidence_refs=[{"evidence_id": match.get("evidence_id"), "case_id": matched_case_id}],
            )
            all_matches.append(face_match)
            
            # Create Person node if none exists for this face
            if not matched_person_id:
                new_person_id = str(uuid.uuid4())
                neo4j_person.create_person_node(
                    person_id=new_person_id,
                    face_ids=[face_id, match.get("face_id", "")],
                )
                neo4j_person.add_appears_in(new_person_id, case_id, role_in_case, "", match.get("score", 0.0))
                if matched_case_id:
                    neo4j_person.add_appears_in(new_person_id, matched_case_id, match.get("role_in_case", "unknown"), match.get("evidence_id", ""), match.get("score", 0.0))
                
                # Update face records with person_id
                try:
                    await qdrant_face_store.update_person_id(face_id, new_person_id)
                    if match.get("face_id"):
                        await qdrant_face_store.update_person_id(match["face_id"], new_person_id)
                except Exception as e:
                    logger.warning(f"Failed to update person_id: {e}")
                
                merge_actions.append({"action": "person_created", "person_id": new_person_id})
            else:
                # Person exists — add APPEARS_IN for current case
                neo4j_person.add_appears_in(matched_person_id, case_id, role_in_case, "", match.get("score", 0.0))
                try:
                    await qdrant_face_store.update_person_id(face_id, matched_person_id)
                except Exception as e:
                    logger.warning(f"Failed to update person_id: {e}")
                
                # Run entity merge scoring
                current_person = {"face_ids": [face_id], "canonical_name": None, "aliases": [], "id_numbers": [], "phone_numbers": []}
                if person_data:
                    score_result = entity_merge.score_merge_candidates(
                        face_cosine_sim=match.get("score", 0.0),
                        person_a=current_person,
                        person_b=person_data,
                        shared_case_ids=[case_id] if matched_case_id == case_id else [],
                    )
                    action = entity_merge.decide_merge_action(score_result)
                    merge_actions.append({
                        "action": action,
                        "person_id": matched_person_id,
                        "score": score_result,
                    })
        
        # If no matches found, create a standalone Person node for this face
        if not matches:
            new_person_id = str(uuid.uuid4())
            neo4j_person.create_person_node(
                person_id=new_person_id,
                face_ids=[face_id],
            )
            neo4j_person.add_appears_in(new_person_id, case_id, role_in_case, "", face.det_score)
            try:
                await qdrant_face_store.update_person_id(face_id, new_person_id)
            except Exception as e:
                logger.warning(f"Failed to update person_id: {e}")
            merge_actions.append({"action": "new_person", "person_id": new_person_id})
    
    return PhotoUploadResponse(
        faces_detected=len(face_results),
        faces=face_results,
        matches=all_matches,
        merge_actions=merge_actions,
    )


# ── Mode B: Standalone Lookup ────────────────────────────────────────────────

@router.post("/lookup", response_model=FaceLookupResponse)
async def face_lookup(
    file: UploadFile = File(...),
    include_low_confidence: bool = Form(False),
    current_user: dict = Depends(get_current_user),
):
    """
    Mode B: Standalone face lookup — search for matches without storing the query photo.
    
    The query photo is transient and NOT stored as evidence.
    Results include confidence scores and linked case information.
    """
    officer_id = current_user.get("username", "system")
    
    (detect_faces, get_image_dimensions, normalize_embedding, validate_embedding,
     assess_quality, qdrant_face_store, neo4j_person, entity_merge) = _get_face_services()
    
    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    
    photo_hash = hashlib.sha256(image_bytes).hexdigest()
    
    # Detect faces
    try:
        detected = detect_faces(image_bytes)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    if not detected:
        raise HTTPException(status_code=400, detail="No faces detected in the image.")
    
    # Use the first / highest-confidence face for the query
    primary_face = max(detected, key=lambda f: f.det_score)
    
    img_h, img_w = get_image_dimensions(image_bytes)
    quality = assess_quality(
        bbox=primary_face.bbox,
        det_score=primary_face.det_score,
        landmarks=primary_face.landmarks,
        image_height=img_h,
        image_width=img_w,
    )
    
    if not validate_embedding(primary_face.embedding):
        raise HTTPException(status_code=400, detail="Could not extract face embedding from the image.")
    
    embedding = normalize_embedding(primary_face.embedding)
    
    # Use stricter threshold for Mode B
    threshold = MODE_B_THRESHOLD if not include_low_confidence else 0.45
    
    try:
        matches = await qdrant_face_store.search_faces(
            query_embedding=embedding,
            limit=10,
            score_threshold=threshold,
        )
    except Exception as e:
        logger.error(f"Face lookup search failed: {e}")
        raise HTTPException(status_code=503, detail="Face search service unavailable.")
    
    # Build response with person details
    results = []
    for match in matches:
        person_id = match.get("person_id")
        person_data = None
        linked_cases = []
        evidence_refs = []
        
        if person_id:
            person_data = neo4j_person.get_person_with_cases(person_id)
            if person_data:
                linked_cases = person_data.get("linked_cases", [])
                await _enrich_linked_cases(linked_cases)
        
        if match.get("evidence_id"):
            evidence_refs.append({
                "evidence_id": match["evidence_id"],
                "case_id": match.get("case_id"),
            })
        
        results.append(FaceMatch(
            person_id=person_id,
            confidence=match.get("score", 0.0),
            canonical_name=person_data.get("canonical_name") if person_data else None,
            linked_cases=linked_cases,
            evidence_refs=evidence_refs,
        ))
    
    # Log the search (for audit trail)
    logger.info(
        f"Face lookup by {officer_id}: photo_hash={photo_hash[:16]}..., "
        f"quality={quality.det_score:.2f}, matches={len(results)}"
    )
    
    message = None
    if not results:
        message = "No confident match found."
    
    return FaceLookupResponse(
        query_face_quality=quality.det_score,
        results=results,
        message=message,
    )


from models.schemas import FaceSearchQueryResponse, FaceSearchResult

@router.post("/search-query", response_model=FaceSearchQueryResponse)
async def face_search_query(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Search Qdrant for faces, deduplicate by case_id, and join with person_records.
    """
    (detect_faces, get_image_dimensions, normalize_embedding, validate_embedding,
     assess_quality, qdrant_face_store, neo4j_person, entity_merge) = _get_face_services()
    
    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    
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
    
    if not validate_embedding(primary_face.embedding):
        raise HTTPException(status_code=400, detail="Could not extract face embedding from the image.")
    
    embedding = normalize_embedding(primary_face.embedding)
    
    try:
        # Search Qdrant
        matches = await qdrant_face_store.search_faces(
            query_embedding=embedding,
            limit=20,
            score_threshold=0.45,
        )
    except Exception as e:
        logger.error(f"Face lookup search failed: {e}")
        raise HTTPException(status_code=503, detail="Face search service unavailable.")

    # Deduplicate by case_id, keeping the one with the highest score
    best_match_by_case = {}
    for match in matches:
        cid = match.get("case_id")
        if not cid:
            continue
        score = match.get("score", 0.0)
        if cid not in best_match_by_case or score > best_match_by_case[cid]["score"]:
            best_match_by_case[cid] = match

    results = []
    db = await get_db()
    try:
        for cid, match in best_match_by_case.items():
            face_id = match.get("face_id")
            score = match.get("score", 0.0)
            
            # Fetch specific person_record for this face_id
            cursor = await db.execute("SELECT * FROM person_records WHERE face_id = ?", (face_id,))
            person_record = await cursor.fetchone()
            
            if not person_record:
                # Fallback: maybe just get a person_record for this case?
                cursor = await db.execute("SELECT * FROM person_records WHERE case_id = ? LIMIT 1", (cid,))
                person_record = await cursor.fetchone()
                
            # Fetch case details
            case_cursor = await db.execute("SELECT title, status FROM cases WHERE case_id = ?", (cid,))
            case_row = await case_cursor.fetchone()
            
            results.append(FaceSearchResult(
                case_id=cid,
                case_title=case_row["title"] if case_row else "Unknown Case",
                case_status=case_row["status"] if case_row else "unknown",
                confidence=score,
                person_record=dict(person_record) if person_record else None,
                evidence_id=match.get("evidence_id")
            ))
    finally:
        await db.close()

    results.sort(key=lambda x: x.confidence, reverse=True)

    message = None
    if not results:
        message = "No matches found."

    return FaceSearchQueryResponse(
        query_face_quality=quality.det_score,
        results=results,
        message=message,
    )

# ── Review Queue ─────────────────────────────────────────────────────────────

@router.get("/review-queue", response_model=ReviewQueueResponse)
async def get_review_queue(
    case_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Get pending SAME_AS candidate links for human review."""
    from services.face_recognition import neo4j_person
    
    pending = neo4j_person.get_pending_reviews(case_id=case_id)
    
    items = [
        ReviewQueueItem(
            review_id=r["review_id"],
            person_a_id=r["person_a_id"],
            person_b_id=r["person_b_id"],
            confidence=r["confidence"],
            status=r.get("status", "pending"),
            created_at=r.get("resolved_at"),
        )
        for r in pending
    ]
    
    return ReviewQueueResponse(items=items, total=len(items))


@router.post("/review/{review_id}/decide")
async def decide_review(
    review_id: str,
    decision: ReviewDecision,
    current_user: dict = Depends(get_current_user),
):
    """Resolve a pending SAME_AS review — confirm merge or reject."""
    from services.face_recognition import neo4j_person
    
    result = neo4j_person.resolve_review(
        review_id=review_id,
        action=decision.action,
        officer_id=decision.officer_id or current_user.get("username", "system"),
    )
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


# ── Background face processing (called from evidence upload pipeline) ────────

async def process_face_background(
    case_id: str,
    evidence_id: str,
    image_bytes: bytes,
    officer_id: str,
    role_in_case: str = "unknown",
):
    """
    Background task: detect faces in evidence photo and run matching.
    
    Called from the evidence upload pipeline when an image file is uploaded.
    This is the Mode A auto-trigger — runs asynchronously after evidence storage.
    """
    logger.info(f"Starting background face processing for evidence {evidence_id}...")
    
    try:
        (detect_faces, get_image_dimensions, normalize_embedding, validate_embedding,
         assess_quality, qdrant_face_store, neo4j_person, entity_merge) = _get_face_services()
    except Exception as e:
        logger.warning(f"Face recognition services not available: {e}")
        return
    
    photo_hash = hashlib.sha256(image_bytes).hexdigest()
    
    # Detect faces
    try:
        detected = detect_faces(image_bytes)
    except Exception as e:
        logger.error(f"Face detection failed for evidence {evidence_id}: {e}")
        return
    
    if not detected:
        logger.info(f"No faces detected in evidence {evidence_id}")
        return
    
    img_h, img_w = get_image_dimensions(image_bytes)
    
    faces_stored = 0
    matches_found = 0
    
    for face in detected:
        face_id = str(uuid.uuid4())
        
        # Quality check
        quality = assess_quality(
            bbox=face.bbox,
            det_score=face.det_score,
            landmarks=face.landmarks,
            image_height=img_h,
            image_width=img_w,
        )
        
        if not quality.passed or not validate_embedding(face.embedding):
            logger.info(f"Skipping low-quality face in evidence {evidence_id}: {quality.rejection_reason}")
            continue
        
        embedding = normalize_embedding(face.embedding)
        
        # Store in Qdrant
        try:
            await qdrant_face_store.upsert_face(
                face_id=face_id,
                embedding=embedding,
                case_id=case_id,
                evidence_id=evidence_id,
                person_id=None,
                role_in_case=role_in_case,
                det_score=face.det_score,
                source_photo_hash=photo_hash,
                officer_id=officer_id,
            )
            faces_stored += 1
        except Exception as e:
            logger.error(f"Failed to store face {face_id}: {e}")
            continue
        
        # Search for matches
        try:
            matches = await qdrant_face_store.search_faces(
                query_embedding=embedding,
                limit=5,
                score_threshold=MODE_A_THRESHOLD,
                exclude_case_id=case_id,
            )
        except Exception as e:
            logger.warning(f"Face search failed: {e}")
            matches = []
        
        for match in matches:
            matches_found += 1
            matched_person_id = match.get("person_id")
            
            if matched_person_id:
                # Add this face to existing person
                neo4j_person.add_appears_in(
                    matched_person_id, case_id, role_in_case, evidence_id, match.get("score", 0.0)
                )
                try:
                    await qdrant_face_store.update_person_id(face_id, matched_person_id)
                except Exception:
                    pass
            else:
                # Create new person linking both faces
                new_person_id = str(uuid.uuid4())
                neo4j_person.create_person_node(
                    person_id=new_person_id,
                    face_ids=[face_id, match.get("face_id", "")],
                )
                neo4j_person.add_appears_in(new_person_id, case_id, role_in_case, evidence_id, match.get("score", 0.0))
                if match.get("case_id"):
                    neo4j_person.add_appears_in(
                        new_person_id, match["case_id"],
                        match.get("role_in_case", "unknown"),
                        match.get("evidence_id", ""),
                        match.get("score", 0.0),
                    )
                try:
                    await qdrant_face_store.update_person_id(face_id, new_person_id)
                    if match.get("face_id"):
                        await qdrant_face_store.update_person_id(match["face_id"], new_person_id)
                except Exception:
                    pass
        
        # No matches — create standalone person
        if not matches:
            new_person_id = str(uuid.uuid4())
            neo4j_person.create_person_node(person_id=new_person_id, face_ids=[face_id])
            neo4j_person.add_appears_in(new_person_id, case_id, role_in_case, evidence_id, face.det_score)
            try:
                await qdrant_face_store.update_person_id(face_id, new_person_id)
            except Exception:
                pass
    
    logger.info(
        f"Background face processing complete for evidence {evidence_id}: "
        f"{faces_stored} faces stored, {matches_found} matches found"
    )
