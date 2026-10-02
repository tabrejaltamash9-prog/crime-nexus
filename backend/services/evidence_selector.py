"""
Evidence Selector — Groups, ranks, and selects relevant documents from retrieval results.

Responsibilities:
  1. Group Qdrant chunk results by document_id
  2. Compute per-document relevance scores (aggregate of chunk scores)
  3. Rank documents by relevance
  4. Select top documents based on question context
  5. Support both "chunks only" and "full document" selection modes
  6. Fetch full document text from SQLite when needed
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from services.database import get_db

logger = logging.getLogger(__name__)


def group_chunks_by_document(
    search_results: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Group search result chunks by their document_id.

    Returns a dict keyed by document_id with:
      - document_id, file_name, file_url, evidence_type, case_id
      - chunks: list of chunk dicts sorted by chunk_index
      - max_score: highest chunk score
      - avg_score: average chunk score
      - chunk_count: number of matching chunks
    """
    groups: Dict[str, Dict[str, Any]] = {}

    for result in search_results:
        doc_id = result.get("document_id", "unknown")

        if doc_id not in groups:
            groups[doc_id] = {
                "document_id": doc_id,
                "file_name": result.get("file_name", "Unknown"),
                "file_url": result.get("file_url", ""),
                "evidence_type": result.get("evidence_type", "Document"),
                "case_id": result.get("case_id", ""),
                "source_type": result.get("source_type", "unknown"),
                "chunks": [],
                "max_score": 0.0,
                "total_score": 0.0,
                "chunk_count": 0,
            }

        chunk = {
            "chunk_text": result.get("chunk_text", ""),
            "chunk_index": result.get("chunk_index", 0),
            "score": result.get("score", 0.0),
            "page_number": result.get("page_number"),
            "ocr_low_confidence_flag": result.get("ocr_low_confidence_flag", False),
        }

        groups[doc_id]["chunks"].append(chunk)
        groups[doc_id]["max_score"] = max(
            groups[doc_id]["max_score"], chunk["score"]
        )
        groups[doc_id]["total_score"] += chunk["score"]
        groups[doc_id]["chunk_count"] += 1

    # Compute average scores and sort chunks
    for doc in groups.values():
        doc["avg_score"] = (
            doc["total_score"] / doc["chunk_count"] if doc["chunk_count"] > 0 else 0.0
        )
        doc["chunks"].sort(key=lambda c: c["chunk_index"])

    return groups


def rank_documents(
    document_groups: Dict[str, Dict[str, Any]],
    max_documents: int = 10,
) -> List[Dict[str, Any]]:
    """
    Rank documents by relevance.

    Scoring: 60% max_score + 30% avg_score + 10% chunk_count_bonus
    The chunk_count_bonus rewards documents with multiple matching chunks
    (capped at 5 chunks for normalization).

    Returns sorted list of document dicts, limited to max_documents.
    """
    for doc in document_groups.values():
        chunk_bonus = min(doc["chunk_count"] / 5.0, 1.0)
        doc["relevance_score"] = (
            0.6 * doc["max_score"]
            + 0.3 * doc["avg_score"]
            + 0.1 * chunk_bonus
        )

    ranked = sorted(
        document_groups.values(),
        key=lambda d: d["relevance_score"],
        reverse=True,
    )

    return ranked[:max_documents]


async def fetch_full_document_text(
    document_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch the full extracted text and metadata for a single document from SQLite.

    Returns dict with:
      - document_id, file_name, extracted_text, source_type, mime_type,
        case_id, doc_version, original_filename
    Or None if not found or no text available.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT evidence_id, case_id, original_filename, mime_type,
                      extracted_text, source_type, doc_version
               FROM evidence WHERE evidence_id = ?""",
            (document_id,),
        )
        row = await cursor.fetchone()

        if not row or not row["extracted_text"]:
            return None

        return {
            "document_id": row["evidence_id"],
            "case_id": row["case_id"],
            "file_name": row["original_filename"],
            "mime_type": row["mime_type"],
            "extracted_text": row["extracted_text"],
            "source_type": row["source_type"] or "unknown",
            "doc_version": row["doc_version"] or 1,
        }
    finally:
        await db.close()


async def fetch_documents_text(
    document_ids: List[str],
) -> List[Dict[str, Any]]:
    """
    Fetch full extracted text for multiple documents.
    Returns list of document dicts (only those with available text).
    """
    results = []
    for doc_id in document_ids:
        doc = await fetch_full_document_text(doc_id)
        if doc:
            results.append(doc)
    return results


def select_evidence(
    search_results: List[Dict[str, Any]],
    max_documents: int = 10,
    min_relevance_score: float = 0.25,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Main evidence selection pipeline.

    1. Group chunks by document
    2. Rank documents
    3. Filter by minimum relevance
    4. Return (ranked_documents, all_source_chunks)

    Args:
        search_results: Raw Qdrant search results
        max_documents: Maximum number of documents to select
        min_relevance_score: Minimum relevance score threshold

    Returns:
        Tuple of:
          - ranked_documents: List of document group dicts
          - source_chunks: Flat list of all chunks from selected documents
    """
    if not search_results:
        return [], []

    groups = group_chunks_by_document(search_results)
    ranked = rank_documents(groups, max_documents)

    # Filter by relevance threshold
    selected = [
        doc for doc in ranked if doc["relevance_score"] >= min_relevance_score
    ]

    # Collect all chunks from selected documents
    source_chunks = []
    for doc in selected:
        for chunk in doc["chunks"]:
            source_chunks.append({
                "document_id": doc["document_id"],
                "file_name": doc["file_name"],
                "file_url": doc["file_url"],
                "evidence_type": doc["evidence_type"],
                "case_id": doc["case_id"],
                **chunk,
            })

    logger.info(
        f"Evidence selection: {len(search_results)} chunks → "
        f"{len(groups)} documents → {len(selected)} selected "
        f"(threshold={min_relevance_score})"
    )

    return selected, source_chunks
