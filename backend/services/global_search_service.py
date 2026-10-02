"""
Global Search Service — Cross-case hybrid Graph-RAG pipeline.

Handles the global search workflow:
  1. Embed the query
  2. Search Qdrant across all authorized cases
  3. Search Neo4j for relevant entities and cross-case connections
  4. Combine, deduplicate, and rank results
  5. Build combined evidence context
  6. Send to LLM Gateway
  7. Return answer with citations and cross-case connections
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from services.embedding_service import embed_query
from services import vector_store, neo4j_service
from services.evidence_selector import select_evidence
from services.context_manager import build_chunk_context
from services.llm.gateway import get_gateway
from services.database import get_db

logger = logging.getLogger(__name__)

# ── System Prompt ────────────────────────────────────────────────────────────

GLOBAL_SYSTEM_PROMPT = """You are an AI investigation assistant performing a cross-case analysis.
You are searching across multiple authorized cases to find connections and relevant evidence.

Answer the investigator's question using ONLY the evidence and relationship information provided.
Do not invent facts, suspects, relationships, events, locations, phone numbers, or evidence.
Clearly distinguish confirmed evidence from inference or hypothesis.

When making a claim, cite the source: [Doc: filename, Case: case_id].
Group findings by case when relevant.
Highlight any cross-case connections (same person, phone number, vehicle, location, etc.).
If the retrieved evidence is insufficient, explicitly say so.
Do not make legal determinations of guilt.
Maintain an evidence-grounded and neutral investigative tone.
If any passage is marked as [LOW OCR CONFIDENCE], note this in your answer."""


async def global_search(
    query: str,
    authorized_case_ids: List[str],
    user_id: str,
    username: str,
    provider: Optional[str] = None,
    top_k: int = 15,
    score_threshold: float = 0.3,
) -> Dict[str, Any]:
    """
    Full global search pipeline.

    Args:
        query: The investigator's natural language question.
        authorized_case_ids: Cases the user is allowed to access (from auth service).
        user_id: For audit logging.
        username: For audit logging.
        provider: Optional specific LLM provider to use.
        top_k: Number of evidence chunks to retrieve.
        score_threshold: Minimum relevance score.

    Returns:
        Dict with: answer, sources, cross_case_connections, provider_used,
                   model_used, context_strategy, failover_occurred
    """
    if not authorized_case_ids:
        return {
            "answer": "You do not have access to any cases. Contact your supervisor for case assignments.",
            "sources": [],
            "cross_case_connections": [],
            "provider_used": "none",
            "model_used": "none",
            "context_strategy": "none",
            "failover_occurred": False,
        }

    logger.info(
        f"Global search: '{query[:80]}...' across {len(authorized_case_ids)} cases"
    )

    # ── Step 1: Embed Query ──
    try:
        query_vector = await embed_query(query)
    except Exception as e:
        logger.error(f"Query embedding failed: {e}")
        raise RuntimeError(f"Failed to embed query: {e}")

    # ── Step 2: Qdrant Multi-Case Search ──
    try:
        search_results = await vector_store.search_similar_multi_case(
            query_vector=query_vector,
            case_ids=authorized_case_ids,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        logger.info(f"Qdrant returned {len(search_results)} chunks across cases")
    except Exception as e:
        logger.error(f"Qdrant multi-case search failed: {e}")
        search_results = []

    # ── Step 3: Neo4j Cross-Case Entity Search ──
    graph_data = {"nodes": [], "edges": []}
    cross_case_connections = []

    try:
        # Search for entities related to the query
        entities = neo4j_service.search_entities(query, authorized_case_ids)
        if entities:
            graph_data["nodes"] = entities

            # Find cross-case connections for found entities
            for entity in entities[:5]:  # Limit to top 5 entities
                connections = neo4j_service.find_cross_case_connections(
                    entity.get("text", ""), authorized_case_ids
                )
                for conn in connections:
                    if len(conn.get("cases", [])) > 1:
                        cross_case_connections.append({
                            "entity": conn.get("entity_name", ""),
                            "type": conn.get("entity_type", ""),
                            "cases": conn.get("cases", []),
                            "occurrences": conn.get("occurrences", 0),
                        })

            # Get relationships for found entities
            for entity in entities[:3]:
                rel_data = neo4j_service.get_entity_relationships(
                    entity.get("text", ""), authorized_case_ids
                )
                graph_data["edges"].extend(rel_data.get("edges", []))
                for node in rel_data.get("nodes", []):
                    if node not in graph_data["nodes"]:
                        graph_data["nodes"].append(node)

    except Exception as e:
        logger.error(f"Neo4j cross-case search failed: {e}")

    # ── Step 4: Select and Rank Evidence ──
    selected_docs, source_chunks = select_evidence(
        search_results, max_documents=10, min_relevance_score=0.25
    )

    # ── Step 5: Build Context ──
    evidence_context = build_chunk_context(source_chunks, graph_data)

    # ── Step 6: Generate Answer via Gateway ──
    gateway = get_gateway()

    try:
        response = await gateway.generate(
            query=query,
            context=evidence_context,
            chat_history=[],
            system_prompt=GLOBAL_SYSTEM_PROMPT,
            provider=provider,
            task_type="global_search",
        )
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        # Log the failed query
        await _log_query(
            user_id=user_id,
            username=username,
            query_type="global_search",
            case_id=None,
            query_text=query,
            error=str(e),
        )
        raise RuntimeError(f"LLM generation failed: {e}")

    # ── Step 7: Build Source Citations ──
    sources = []
    for chunk in source_chunks:
        sources.append({
            "document_id": chunk.get("document_id", ""),
            "file_name": chunk.get("file_name", ""),
            "file_url": chunk.get("file_url", ""),
            "chunk_text": chunk.get("chunk_text", ""),
            "chunk_index": chunk.get("chunk_index", 0),
            "score": round(chunk.get("score", 0.0), 4),
            "case_id": chunk.get("case_id", ""),
            "page_number": chunk.get("page_number"),
        })

    # Deduplicate cross-case connections
    seen = set()
    unique_connections = []
    for conn in cross_case_connections:
        key = conn.get("entity", "")
        if key not in seen:
            seen.add(key)
            unique_connections.append(conn)

    # ── Step 8: Audit Log ──
    await _log_query(
        user_id=user_id,
        username=username,
        query_type="global_search",
        case_id=None,
        query_text=query,
        provider_used=response.provider,
        model_used=response.model,
        context_strategy="chunk_rag",
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
        "cross_case_connections": unique_connections,
        "provider_used": response.provider,
        "model_used": response.model,
        "context_strategy": "chunk_rag",
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
                    query_text[:500],  # Truncate for storage
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
