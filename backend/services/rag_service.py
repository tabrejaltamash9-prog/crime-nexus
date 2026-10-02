"""
RAG Service — Retrieval-Augmented Generation with Nemotron/Gemini.

Handles:
  1. Query embedding using BAAI/bge-large-en-v1.5
  2. Filtered similarity search in Qdrant by case_id
  3. Graph relationship retrieval from Neo4j
  4. Evidence context assembly with citation metadata
  5. LLM prompt construction with forensic analyst system prompt
  6. Response generation with source attribution
"""

import logging
import os
from typing import List, Dict, Any, Optional

from services.embedding_service import embed_query
from services import vector_store
from services import neo4j_service
from services.llm_service import generate_answer

logger = logging.getLogger(__name__)


# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an AI investigation assistant.
Answer the investigator's question using ONLY the evidence and relationship information provided in the retrieved context.
Do not invent facts, suspects, relationships, events, locations, phone numbers, or evidence.
Clearly distinguish confirmed evidence from inference or hypothesis.
When making an important claim, provide the corresponding evidence ID/source.
If the retrieved evidence is insufficient, explicitly say that there is insufficient evidence.
Do not make a legal determination of guilt.
Do not diagnose psychological conditions.
Maintain an evidence-grounded and neutral investigative tone.
If any retrieved passage is marked as [LOW OCR CONFIDENCE], note this explicitly in your answer rather than presenting it with the same certainty as high-confidence text."""


# ── Context Assembly ─────────────────────────────────────────────────────────

def _build_evidence_context(search_results: List[Dict[str, Any]], graph_data: Dict[str, Any]) -> str:
    """
    Build the EVIDENCE CONTEXT block from Qdrant search results and Neo4j graph data.
    Each chunk is formatted with its source metadata for citation.
    """
    context_parts = []
    
    # Add Qdrant Semantic Context
    context_parts.append("### SEMANTIC EVIDENCE (Qdrant) ###\n")
    if not search_results:
        context_parts.append("No relevant semantic evidence found.\n")
    else:
        for i, result in enumerate(search_results, 1):
            file_name = result.get("file_name", "Unknown")
            chunk_index = result.get("chunk_index", 0)
            chunk_text = result.get("chunk_text", "")
            evidence_type = result.get("evidence_type", "Document")
            evidence_id = result.get("document_id", "Unknown")
            low_conf = result.get("ocr_low_confidence_flag", False)
            conf_warning = " [LOW OCR CONFIDENCE]" if low_conf else ""
            
            context_parts.append(
                f"--- Evidence Chunk {i}{conf_warning} ---\n"
                f"Source: {file_name} (Chunk #{chunk_index}) | ID: {evidence_id} | Type: {evidence_type}\n"
                f"{chunk_text}\n"
            )
            
    # Add Neo4j Graph Context
    context_parts.append("\n### RELATIONSHIP EVIDENCE (Neo4j) ###\n")
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    
    if not nodes and not edges:
        context_parts.append("No relevant relationship evidence found in the graph.\n")
    else:
        node_lookup = {node.get("id"): node.get("text") for node in nodes}
        
        context_parts.append("Entities Identified:")
        for node in nodes:
            ent_type = node.get("type", "Unknown")
            ent_text = node.get("text", "Unknown")
            context_parts.append(f"- {ent_text} (Type: {ent_type})")
            
        context_parts.append("\nRelationships Identified:")
        if not edges:
            context_parts.append("- No explicit relationships found.")
        for edge in edges:
            from_text = node_lookup.get(edge.get("from"), "Unknown")
            to_text = node_lookup.get(edge.get("to"), "Unknown")
            rel_type = edge.get("type", "UNKNOWN_RELATION")
            context_parts.append(f"- {from_text} --[{rel_type}]--> {to_text}")

    return "\n".join(context_parts)


# ── Main Query Pipeline ──────────────────────────────────────────────────────

async def query_evidence(
    query: str,
    case_id: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    top_k: int = 10,
) -> Dict[str, Any]:
    """
    Full RAG query pipeline:
      1. Embed the user query using BAAI/bge-large-en-v1.5
      2. Retrieve top-k relevant chunks from Qdrant (filtered by case_id)
      3. Retrieve graph entities and relationships from Neo4j (filtered by case_id)
      4. Build combined evidence context
      5. Generate answer via Nemotron (or fallback Gemini)
      6. Return answer with source metadata
    
    Args:
        query: The investigator's natural language question.
        case_id: Filter evidence retrieval to this case.
        chat_history: Previous conversation turns for context.
        top_k: Number of evidence chunks to retrieve.
        
    Returns:
        Dict with keys:
          - answer: str — The LLM's evidence-grounded response
          - sources: list — Source chunk metadata with relevance scores
    """
    if chat_history is None:
        chat_history = []
    
    logger.info(f"RAG query for case_id={case_id}: '{query[:100]}...'")
    
    # ── Step 1: Embed Query ──
    try:
        query_vector = await embed_query(query)
        logger.debug(f"Query embedded successfully (dim={len(query_vector)})")
    except Exception as e:
        logger.error(f"Query embedding failed: {e}")
        raise RuntimeError(f"Failed to embed query: {e}")
    
    # ── Step 2: Retrieve Relevant Chunks from Qdrant ──
    try:
        search_results = await vector_store.search_similar(
            query_vector=query_vector,
            case_id=case_id,
            top_k=top_k,
            score_threshold=0.3,
        )
        logger.info(f"Retrieved {len(search_results)} evidence chunks from Qdrant")
    except Exception as e:
        logger.error(f"Qdrant search failed: {e}")
        # Gracefully handle missing database so chat doesn't break completely
        search_results = []
        
    # ── Step 3: Retrieve Graph Data from Neo4j ──
    try:
        graph_data = neo4j_service.get_graph(case_id)
        logger.info(f"Retrieved {len(graph_data.get('nodes', []))} nodes and {len(graph_data.get('edges', []))} edges from Neo4j")
    except Exception as e:
        logger.error(f"Neo4j graph retrieval failed: {e}")
        # We can continue even if graph fails, just pass empty dict
        graph_data = {"nodes": [], "edges": []}
    
    # ── Step 4: Build Combined Evidence Context ──
    evidence_context = _build_evidence_context(search_results, graph_data)
    
    # ── Step 5: Generate Answer via LLM ──
    try:
        answer = await generate_answer(
            query=query,
            retrieved_context=evidence_context,
            chat_history=chat_history,
            system_prompt=SYSTEM_PROMPT,
        )
        logger.info(f"LLM response generated ({len(answer)} chars)")
        
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        raise RuntimeError(f"LLM generation failed. Error: {e}")
    
    # ── Step 6: Build Source Metadata ──
    sources = []
    for result in search_results:
        sources.append({
            "document_id": result.get("document_id", ""),
            "file_name": result.get("file_name", ""),
            "file_url": result.get("file_url", ""),
            "chunk_text": result.get("chunk_text", ""),
            "chunk_index": result.get("chunk_index", 0),
            "score": round(result.get("score", 0.0), 4),
        })
    
    return {
        "answer": answer,
        "sources": sources,
    }
