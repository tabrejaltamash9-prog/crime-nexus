"""
Local Search Service — Case-level evidence RAG + long-context reasoning.

Handles the local (single-case) search workflow:
  1. Verify case access (already done by API layer)
  2. Embed the query
  3. Search Qdrant filtered to the selected case
  4. Select and rank relevant documents
  5. Fetch full document text for selected evidence
  6. Determine context strategy (full doc vs chunk fallback)
  7. Send to LLM Gateway with long-context model if needed
  8. Return answer with citations and context metadata
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from services.embedding_service import embed_query
from services import vector_store, neo4j_service
from services.evidence_selector import select_evidence, fetch_documents_text
from services.context_manager import determine_context_strategy, build_chunk_context
from services.llm.gateway import get_gateway
from services.database import get_db

logger = logging.getLogger(__name__)

# ── System Prompt ────────────────────────────────────────────────────────────

LOCAL_SYSTEM_PROMPT = """You are an AI investigation assistant analyzing evidence within a single case.
Answer the investigator's question using ONLY the evidence provided in the context.
Do not invent facts, suspects, relationships, events, locations, phone numbers, or evidence.
Clearly distinguish confirmed evidence from inference or hypothesis.

When making an important claim, provide the corresponding source citation:
  [Doc: filename, Chunk: N] for chunk-based evidence
  [Doc: filename] for full-document evidence

If the evidence is provided as full documents, analyze them comprehensively.
If provided as retrieved excerpts, note that you are working from selected portions.

Respond with:
1. **## Executive Summary** — A 3-5 sentence overview of key findings
2. **## Detailed Analysis** — Thorough walkthrough with inline citations for every factual claim.
   Bold all names, dates, locations, phone numbers, and vehicles.
3. **## Investigative Notes** — Patterns, connections, gaps, contradictions, and recommended follow-up actions.

If the retrieved evidence is insufficient, explicitly say so.
Do not make legal determinations of guilt. Do not diagnose psychological conditions.
Maintain an evidence-grounded and neutral investigative tone.
If any passage is marked as [LOW OCR CONFIDENCE], note this explicitly."""


async def local_case_chat(
    query: str,
    case_id: str,
    user_id: str,
    username: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    provider: Optional[str] = None,
    top_k: int = 10,
    score_threshold: float = 0.3,
) -> Dict[str, Any]:
    """
    Case-level evidence analysis pipeline with long-context support.

    Steps:
      A. Search Qdrant for relevant chunks (filtered by case_id)
      B. Select and rank documents by relevance
      C. Fetch full document text for selected evidence
      D. Determine context strategy (full doc vs chunks)
      E. Generate answer through the LLM Gateway

    Args:
        query: The investigator's question.
        case_id: The case to search within (already authorized by API layer).
        user_id: For audit logging.
        username: For audit logging.
        chat_history: Previous conversation turns.
        provider: Optional specific LLM provider.
        top_k: Number of evidence chunks to retrieve.
        score_threshold: Minimum relevance score.

    Returns:
        Dict with: answer, sources, documents_used, context_strategy,
                   provider_used, model_used, failover_occurred
    """
    if chat_history is None:
        chat_history = []

    logger.info(f"Local case chat for case_id={case_id}: '{query[:80]}...'")

    # ── Step A: Embed and Search ──
    try:
        query_vector = await embed_query(query)
    except Exception as e:
        logger.error(f"Query embedding failed: {e}")
        raise RuntimeError(f"Failed to embed query: {e}")

    try:
        search_results = await vector_store.search_similar(
            query_vector=query_vector,
            case_id=case_id,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        logger.info(f"Retrieved {len(search_results)} chunks from Qdrant")
    except Exception as e:
        logger.error(f"Qdrant search failed: {e}")
        search_results = []

    # Get graph data for the case
    try:
        graph_data = neo4j_service.get_graph(case_id)
    except Exception as e:
        logger.error(f"Neo4j graph retrieval failed: {e}")
        graph_data = {"nodes": [], "edges": []}

    # ── Step B: Select and Rank Documents ──
    selected_docs, source_chunks = select_evidence(
        search_results, max_documents=10, min_relevance_score=0.25
    )

    # ── Step C: Fetch Full Document Texts ──
    document_ids = [doc["document_id"] for doc in selected_docs]
    full_documents = await fetch_documents_text(document_ids)

    # ── Step D: Determine Context Strategy ──
    gateway = get_gateway()

    # Determine which adapter we'll use for context budget
    adapter = None
    if provider:
        from services.llm.gateway import get_adapter
        adapter = get_adapter(provider)
    if adapter is None:
        # Use default provider's context window
        from services.llm.config import get_default_provider
        from services.llm.gateway import get_adapter
        adapter = get_adapter(get_default_provider())

    context_window = adapter.context_window if adapter else 128000

    context_str, context_strategy = determine_context_strategy(
        documents=full_documents,
        search_results=source_chunks,
        system_prompt=LOCAL_SYSTEM_PROMPT,
        query=query,
        chat_history=chat_history,
        context_window=context_window,
        provider=adapter.provider_name if adapter else "default",
    )

    # ── Step E: Generate Answer ──
    require_long_context = context_strategy == "full_document"

    try:
        response = await gateway.generate(
            query=query,
            context=context_str,
            chat_history=chat_history,
            system_prompt=LOCAL_SYSTEM_PROMPT,
            provider=provider,
            task_type="local_analysis",
            require_long_context=require_long_context,
        )
        response.context_strategy = context_strategy
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        await _log_query(
            user_id=user_id,
            username=username,
            query_type="local_chat",
            case_id=case_id,
            query_text=query,
            error=str(e),
        )
        raise RuntimeError(f"LLM generation failed: {e}")

    # ── Build Source Citations ──
    sources = []
    for chunk in source_chunks:
        sources.append({
            "document_id": chunk.get("document_id", ""),
            "file_name": chunk.get("file_name", ""),
            "file_url": chunk.get("file_url", ""),
            "chunk_text": chunk.get("chunk_text", ""),
            "chunk_index": chunk.get("chunk_index", 0),
            "score": round(chunk.get("score", 0.0), 4),
            "page_number": chunk.get("page_number"),
        })

    # Build documents_used list for the frontend
    documents_used = []
    for doc in selected_docs:
        documents_used.append({
            "document_id": doc["document_id"],
            "file_name": doc["file_name"],
            "relevance_score": round(doc.get("relevance_score", 0.0), 4),
            "chunk_count": doc.get("chunk_count", 0),
            "full_text_used": context_strategy == "full_document"
                and doc["document_id"] in [d["document_id"] for d in full_documents],
        })

    # ── Audit Log ──
    await _log_query(
        user_id=user_id,
        username=username,
        query_type="local_chat",
        case_id=case_id,
        query_text=query,
        provider_used=response.provider,
        model_used=response.model,
        context_strategy=context_strategy,
        failover_occurred=response.failover_occurred,
        failover_from=response.failover_from,
        documents_used=len(selected_docs),
        chunks_retrieved=len(search_results),
        response_length=len(response.text),
        latency_ms=int(response.latency_seconds * 1000),
    )

    return {
        "answer": response.text,
        "sources": sources,
        "documents_used": documents_used,
        "context_strategy": context_strategy,
        "provider_used": response.provider,
        "model_used": response.model,
        "failover_occurred": response.failover_occurred,
    }


async def _log_query(
    user_id: str,
    username: str,
    query_type: str,
    case_id: Optional[str],
    query_text: str,
    provider_used: str = None,
    model_used: str = None,
    context_strategy: str = None,
    failover_occurred: bool = False,
    failover_from: str = None,
    documents_used: int = 0,
    chunks_retrieved: int = 0,
    response_length: int = 0,
    latency_ms: int = None,
    error: str = None,
):
    """Record the AI query in the audit log."""
    try:
        db = await get_db()
        try:
            query_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """INSERT INTO ai_query_log
                   (query_id, user_id, username, query_type, case_id, query_text,
                    provider_used, model_used, context_strategy, failover_occurred,
                    failover_from, documents_used, chunks_retrieved, response_length,
                    latency_ms, error, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    query_id, user_id, username, query_type, case_id,
                    query_text[:500],
                    provider_used, model_used, context_strategy,
                    1 if failover_occurred else 0, failover_from,
                    documents_used, chunks_retrieved, response_length,
                    latency_ms, error, now,
                ),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception as e:
        logger.warning(f"Failed to log AI query: {e}")
