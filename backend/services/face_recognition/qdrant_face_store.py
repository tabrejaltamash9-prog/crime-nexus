"""
Qdrant Face Store — Manages the `face_embeddings` collection.

Separate from the existing `criminal_evidence_collection` used for text RAG.
This collection stores 512-dim ArcFace embeddings with identity metadata.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType,
)

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
FACE_COLLECTION = os.environ.get("QDRANT_FACE_COLLECTION", "face_embeddings")
FACE_VECTOR_SIZE = 512  # ArcFace output dimension

# ── Singleton Client ─────────────────────────────────────────────────────────

_client: Optional[AsyncQdrantClient] = None


def _get_client() -> AsyncQdrantClient:
    """Get or create the singleton async Qdrant client."""
    global _client
    if _client is None:
        logger.info(f"Connecting to Qdrant at {QDRANT_URL} for face_embeddings")
        _client = AsyncQdrantClient(url=QDRANT_URL, timeout=30)
    return _client


# ── Collection Management ────────────────────────────────────────────────────

async def ensure_face_collection():
    """
    Create the face_embeddings collection if it doesn't exist.
    512-dim vectors with Cosine distance. Idempotent — safe to call on startup.
    """
    client = _get_client()
    
    try:
        collections = await client.get_collections()
        existing = [c.name for c in collections.collections]
        
        if FACE_COLLECTION not in existing:
            logger.info(f"Creating Qdrant collection: {FACE_COLLECTION} "
                       f"(vector_size={FACE_VECTOR_SIZE}, distance=Cosine)")
            
            await client.create_collection(
                collection_name=FACE_COLLECTION,
                vectors_config=VectorParams(
                    size=FACE_VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            
            # Create payload indexes for filtered search
            for field in ["person_id", "case_id", "role_in_case", "source_photo_hash"]:
                await client.create_payload_index(
                    collection_name=FACE_COLLECTION,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            
            logger.info(f"Collection '{FACE_COLLECTION}' created with payload indexes")
        else:
            logger.info(f"Collection '{FACE_COLLECTION}' already exists")
            
    except Exception as e:
        logger.error(f"Failed to ensure face collection: {e}")
        raise


# ── Face Operations ──────────────────────────────────────────────────────────

async def upsert_face(
    face_id: str,
    embedding: List[float],
    case_id: Optional[str],
    evidence_id: Optional[str],
    person_id: Optional[str],
    role_in_case: str,
    det_score: float,
    source_photo_hash: str,
    officer_id: str,
) -> str:
    """
    Store a face embedding in Qdrant.
    
    Args:
        face_id: Unique ID for this face detection.
        embedding: 512-dim L2-normalized ArcFace embedding.
        case_id: Case ID (None for Mode B transient queries).
        evidence_id: Evidence ID (None for Mode B).
        person_id: Person ID if already resolved (None if unresolved).
        role_in_case: "victim", "suspect", "witness", or "unknown".
        det_score: Detection confidence score.
        source_photo_hash: SHA-256 of the source photo.
        officer_id: Officer who uploaded/queried.
        
    Returns:
        The face_id.
    """
    client = _get_client()
    
    now = datetime.now(timezone.utc).isoformat()
    
    point = PointStruct(
        id=face_id,
        vector=embedding,
        payload={
            "face_id": face_id,
            "person_id": person_id,
            "case_id": case_id,
            "evidence_id": evidence_id,
            "role_in_case": role_in_case,
            "det_score": det_score,
            "source_photo_hash": source_photo_hash,
            "ingested_at": now,
            "ingested_by": officer_id,
        },
    )
    
    await client.upsert(
        collection_name=FACE_COLLECTION,
        points=[point],
        wait=True,
    )
    
    logger.info(f"Upserted face {face_id} to Qdrant (case={case_id}, score={det_score:.2f})")
    return face_id


async def search_faces(
    query_embedding: List[float],
    limit: int = 10,
    score_threshold: float = 0.55,
    exclude_case_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search for similar faces in the Qdrant index.
    
    Args:
        query_embedding: 512-dim L2-normalized query vector.
        limit: Maximum results to return.
        score_threshold: Minimum cosine similarity.
        exclude_case_id: Optionally exclude faces from this case (Mode A).
        
    Returns:
        List of match dicts with score and payload.
    """
    client = _get_client()
    
    # Build filter — exclude same case if specified
    query_filter = None
    if exclude_case_id:
        query_filter = Filter(
            must_not=[
                FieldCondition(
                    key="case_id",
                    match=MatchValue(value=exclude_case_id),
                )
            ]
        )
    
    try:
        results = await client.query_points(
            collection_name=FACE_COLLECTION,
            query=query_embedding,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )
        
        hits = []
        for point in results.points:
            hit = {
                "id": point.id,
                "score": point.score,
            }
            if point.payload:
                hit.update(point.payload)
            hits.append(hit)
        
        logger.info(f"Face search returned {len(hits)} results "
                    f"(threshold={score_threshold}, exclude_case={exclude_case_id})")
        return hits
        
    except Exception as e:
        logger.error(f"Qdrant face search failed: {e}")
        raise


async def check_duplicate(source_photo_hash: str) -> Optional[Dict[str, Any]]:
    """
    Check if a photo with this SHA-256 hash has already been processed.
    
    Returns:
        The existing face record's payload if found, None otherwise.
    """
    client = _get_client()
    
    try:
        results = await client.scroll(
            collection_name=FACE_COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="source_photo_hash",
                        match=MatchValue(value=source_photo_hash),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
        )
        
        points = results[0]  # scroll returns (points, next_page_offset)
        if points:
            logger.info(f"Duplicate photo found: hash={source_photo_hash[:16]}...")
            return dict(points[0].payload) if points[0].payload else {}
        
        return None
        
    except Exception as e:
        logger.warning(f"Duplicate check failed: {e}")
        return None


async def update_person_id(face_id: str, person_id: str):
    """Update the person_id on an existing face record after identity resolution."""
    client = _get_client()
    
    try:
        await client.set_payload(
            collection_name=FACE_COLLECTION,
            payload={"person_id": person_id},
            points=[face_id],
        )
        logger.info(f"Updated face {face_id} with person_id={person_id}")
    except Exception as e:
        logger.error(f"Failed to update person_id for face {face_id}: {e}")
        raise
