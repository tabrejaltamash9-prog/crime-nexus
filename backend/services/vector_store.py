"""
Qdrant Vector Store Manager — Async client for the criminal evidence collection.

Handles collection lifecycle, batch upserts, filtered similarity search,
and document-level deletion for idempotent re-indexing.
All operations are async for FastAPI compatibility.
"""

import asyncio
import logging
import os
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

from services.embedding_service import get_embedding_dimension

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "criminal_evidence_collection")
VECTOR_SIZE = get_embedding_dimension()  # 1024
UPSERT_BATCH_SIZE = 100

# ── Singleton Client ─────────────────────────────────────────────────────────

_client: Optional[AsyncQdrantClient] = None


def get_qdrant_client() -> AsyncQdrantClient:
    """Get or create the singleton async Qdrant client."""
    global _client
    if _client is None:
        logger.info(f"Connecting to Qdrant at {QDRANT_URL}")
        _client = AsyncQdrantClient(url=QDRANT_URL, timeout=30)
    return _client


# ── Collection Management ────────────────────────────────────────────────────

async def ensure_collection():
    """
    Create the evidence collection if it doesn't already exist.
    Configures vector size 1024 (bge-large-en-v1.5) with Cosine distance.
    Creates payload indexes on case_id, document_id, evidence_type for filtered search.
    
    This is idempotent — safe to call on every application startup.
    """
    client = get_qdrant_client()
    
    try:
        collections = await client.get_collections()
        existing_names = [c.name for c in collections.collections]
        
        if COLLECTION_NAME not in existing_names:
            logger.info(f"Creating Qdrant collection: {COLLECTION_NAME} "
                       f"(vector_size={VECTOR_SIZE}, distance=Cosine)")
            await client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            
            # Create payload indexes for efficient filtered queries
            for field_name in ["case_id", "document_id", "evidence_type"]:
                await client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name=field_name,
                    field_schema=PayloadSchemaType.KEYWORD,
                )
            
            logger.info(f"Collection '{COLLECTION_NAME}' created with payload indexes")
        else:
            logger.info(f"Collection '{COLLECTION_NAME}' already exists")
            
    except Exception as e:
        logger.error(f"Failed to ensure Qdrant collection: {e}")
        raise


async def get_collection_info() -> Dict[str, Any]:
    """Get collection stats for health checks and monitoring."""
    client = get_qdrant_client()
    try:
        info = await client.get_collection(COLLECTION_NAME)
        return {
            "name": COLLECTION_NAME,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value if info.status else "unknown",
        }
    except Exception as e:
        logger.error(f"Failed to get collection info: {e}")
        return {"name": COLLECTION_NAME, "status": "error", "error": str(e)}


# ── Vector Operations ────────────────────────────────────────────────────────

async def upsert_chunks(points: List[PointStruct], max_retries: int = 3):
    """
    Batch upsert points into the collection.
    Splits into batches of UPSERT_BATCH_SIZE to avoid oversized requests.
    Retries on transient network errors with exponential backoff.
    
    Args:
        points: List of PointStruct with id, vector, and payload.
        max_retries: Number of retries per batch on failure.
    """
    client = get_qdrant_client()
    total = len(points)
    
    if total == 0:
        logger.warning("upsert_chunks called with empty points list")
        return
    
    logger.info(f"Upserting {total} points to '{COLLECTION_NAME}' "
               f"in batches of {UPSERT_BATCH_SIZE}")
    
    for batch_start in range(0, total, UPSERT_BATCH_SIZE):
        batch = points[batch_start:batch_start + UPSERT_BATCH_SIZE]
        batch_num = (batch_start // UPSERT_BATCH_SIZE) + 1
        
        for attempt in range(1, max_retries + 1):
            try:
                await client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=batch,
                    wait=True,
                )
                logger.debug(f"Batch {batch_num}: upserted {len(batch)} points")
                break  # Success, move to next batch
                
            except Exception as e:
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                    logger.warning(
                        f"Batch {batch_num} upsert failed (attempt {attempt}/{max_retries}): "
                        f"{e}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Batch {batch_num} upsert failed after {max_retries} attempts: {e}"
                    )
                    raise
    
    logger.info(f"Successfully upserted all {total} points")


async def search_similar(
    query_vector: List[float],
    case_id: str,
    top_k: int = 5,
    score_threshold: float = 0.3,
) -> List[Dict[str, Any]]:
    """
    Perform filtered similarity search within a specific case.
    
    Args:
        query_vector: The embedded query vector (1024-dim).
        case_id: Filter results to this case only.
        top_k: Maximum number of results to return.
        score_threshold: Minimum relevance score (Cosine similarity).
        
    Returns:
        List of dicts with keys: id, score, and all payload fields.
    """
    client = get_qdrant_client()
    
    try:
        results = await client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="case_id",
                        match=MatchValue(value=case_id),
                    )
                ]
            ),
            limit=top_k,
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
        
        logger.info(f"Search returned {len(hits)} results for case_id={case_id}")
        return hits
        
    except Exception as e:
        logger.error(f"Qdrant search failed for case_id={case_id}: {e}")
        raise


async def search_similar_multi_case(
    query_vector: List[float],
    case_ids: List[str],
    top_k: int = 15,
    score_threshold: float = 0.3,
) -> List[Dict[str, Any]]:
    """
    Perform filtered similarity search across multiple authorized cases.
    
    Used by the global search pipeline. The case_ids list comes from
    the authorization service and is NEVER supplied by the frontend.
    
    Args:
        query_vector: The embedded query vector (1024-dim).
        case_ids: List of authorized case IDs to search across.
        top_k: Maximum number of results to return.
        score_threshold: Minimum relevance score (Cosine similarity).
        
    Returns:
        List of dicts with keys: id, score, and all payload fields.
    """
    if not case_ids:
        logger.warning("search_similar_multi_case called with empty case_ids list")
        return []
    
    client = get_qdrant_client()
    
    try:
        from qdrant_client.models import MatchAny
        
        results = await client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="case_id",
                        match=MatchAny(any=case_ids),
                    )
                ]
            ),
            limit=top_k,
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
        
        logger.info(
            f"Multi-case search returned {len(hits)} results "
            f"across {len(case_ids)} cases"
        )
        return hits
        
    except Exception as e:
        logger.error(f"Qdrant multi-case search failed: {e}")
        raise


async def delete_by_document(document_id: str):
    """
    Delete all vectors associated with a specific document.
    Used before re-indexing to ensure idempotency — no duplicate chunks remain.
    
    Args:
        document_id: The evidence_id / document_id whose chunks should be removed.
    """
    client = get_qdrant_client()
    
    try:
        result = await client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
            wait=True,
        )
        logger.info(f"Deleted vectors for document_id={document_id}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to delete vectors for document_id={document_id}: {e}")
        raise
