"""
Context Manager — Token estimation, context budget, and assembly strategies.

Handles the decision of whether to use full document text or fallback
to chunk-based retrieval. Builds the final context string for the LLM
with proper document boundaries and source metadata.
"""

import json
import logging
from typing import List, Dict, Any, Tuple

from services.llm.token_estimator import estimate_tokens, check_context_budget
from services.llm.config import get_answer_token_reserve, get_max_context_ratio

logger = logging.getLogger(__name__)


def build_full_document_context(
    documents: List[Dict[str, Any]],
    graph_data: Dict[str, Any] = None,
) -> str:
    """
    Build context from complete document texts (long-context mode).

    Each document is clearly delimited with its identity, type, and page boundaries
    where available. This is used when the total document set fits within the
    model's context budget.

    Args:
        documents: List of dicts with document_id, file_name, extracted_text, etc.
        graph_data: Optional graph entities/relationships to include.

    Returns:
        Assembled context string.
    """
    parts = []
    parts.append("### FULL DOCUMENT EVIDENCE ###\n")
    parts.append(
        "The following documents are provided IN FULL. "
        "Analyze the complete content, not just excerpts.\n"
    )

    for i, doc in enumerate(documents, 1):
        file_name = doc.get("file_name", "Unknown")
        doc_id = doc.get("document_id", "Unknown")
        doc_type = doc.get("source_type", doc.get("mime_type", "Document"))
        text = doc.get("extracted_text", "")

        # Try to parse JSON OCR format to plain text
        plain_text = _extract_plain_text(text)

        parts.append(
            f"\n{'='*60}\n"
            f"DOCUMENT {i}: {file_name}\n"
            f"ID: {doc_id} | Type: {doc_type}\n"
            f"{'='*60}\n"
            f"{plain_text}\n"
        )

    # Add graph context if available
    if graph_data:
        parts.append(_build_graph_context(graph_data))

    return "\n".join(parts)


def build_chunk_context(
    search_results: List[Dict[str, Any]],
    graph_data: Dict[str, Any] = None,
) -> str:
    """
    Build context from retrieved chunks (standard RAG mode).

    Used when full documents don't fit in the context window.
    Each chunk includes its source metadata for citation.

    Args:
        search_results: Qdrant search result chunks.
        graph_data: Optional graph entities/relationships.

    Returns:
        Assembled context string.
    """
    parts = []
    parts.append("### SEMANTIC EVIDENCE (Retrieved Chunks) ###\n")

    if not search_results:
        parts.append("No relevant semantic evidence found.\n")
    else:
        for i, result in enumerate(search_results, 1):
            file_name = result.get("file_name", "Unknown")
            chunk_index = result.get("chunk_index", 0)
            chunk_text = result.get("chunk_text", "")
            evidence_type = result.get("evidence_type", "Document")
            evidence_id = result.get("document_id", "Unknown")
            case_id = result.get("case_id", "Unknown")
            low_conf = result.get("ocr_low_confidence_flag", False)
            conf_warning = " [LOW OCR CONFIDENCE]" if low_conf else ""
            page_num = result.get("page_number")
            page_info = f" | Page: {page_num}" if page_num else ""

            parts.append(
                f"--- Evidence Chunk {i}{conf_warning} ---\n"
                f"Source: {file_name} (Chunk #{chunk_index}){page_info} | "
                f"ID: {evidence_id} | Type: {evidence_type} | Case: {case_id}\n"
                f"{chunk_text}\n"
            )

    # Add graph context
    if graph_data:
        parts.append(_build_graph_context(graph_data))

    return "\n".join(parts)


def determine_context_strategy(
    documents: List[Dict[str, Any]],
    search_results: List[Dict[str, Any]],
    system_prompt: str,
    query: str,
    chat_history: List[Dict[str, str]],
    context_window: int,
    provider: str = "default",
) -> Tuple[str, str]:
    """
    Determine the optimal context strategy and build the context.

    Decision logic:
      1. Try full-document context if selected documents fit.
      2. If not, try removing duplicate/low-relevance material.
      3. Fallback to chunk-based RAG context.

    Args:
        documents: Full document texts (from evidence_selector.fetch_documents_text).
        search_results: Qdrant chunk search results.
        system_prompt: System instructions.
        query: The user's question.
        chat_history: Conversation history.
        context_window: The target model's context window.
        provider: Provider name for token estimation.

    Returns:
        Tuple of (context_string, strategy_name).
        strategy_name is one of: "full_document", "chunk_rag", "summarized"
    """
    answer_reserve = get_answer_token_reserve()
    max_ratio = get_max_context_ratio()

    # Strategy 1: Try full documents
    if documents:
        full_context = build_full_document_context(documents)
        budget = check_context_budget(
            system_prompt=system_prompt,
            query=query,
            context=full_context,
            chat_history=chat_history,
            context_window=context_window,
            answer_reserve=answer_reserve,
            max_ratio=max_ratio,
            provider=provider,
        )

        if budget["fits"]:
            logger.info(
                f"Using full-document context ({len(documents)} docs, "
                f"{budget['utilization']:.1%} utilization)"
            )
            return full_context, "full_document"

        logger.info(
            f"Full documents don't fit ({budget['estimated_tokens']} tokens > "
            f"{budget['available_tokens']} available). Falling back to chunks."
        )

    # Strategy 2: Chunk-based RAG
    if search_results:
        chunk_context = build_chunk_context(search_results)
        budget = check_context_budget(
            system_prompt=system_prompt,
            query=query,
            context=chunk_context,
            chat_history=chat_history,
            context_window=context_window,
            answer_reserve=answer_reserve,
            max_ratio=max_ratio,
            provider=provider,
        )

        if budget["fits"]:
            logger.info(
                f"Using chunk-based RAG context ({len(search_results)} chunks, "
                f"{budget['utilization']:.1%} utilization)"
            )
            return chunk_context, "chunk_rag"

        # If even chunks don't fit, trim to top results
        logger.warning(
            f"Chunk context too large. Trimming from {len(search_results)} chunks."
        )
        trimmed = search_results[:max(5, len(search_results) // 2)]
        trimmed_context = build_chunk_context(trimmed)
        return trimmed_context, "chunk_rag"

    # Strategy 3: No evidence found
    return "No relevant evidence was found for this query.", "chunk_rag"


def _extract_plain_text(text: str) -> str:
    """
    Extract plain text from raw extracted_text field.
    Handles both plain text and Surya OCR JSON format.
    """
    if not text:
        return ""

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "blocks" in data:
            blocks = data["blocks"]
            return "\n".join(b.get("text", "") for b in blocks if b.get("text"))
    except (json.JSONDecodeError, TypeError):
        pass

    return text


def _build_graph_context(graph_data: Dict[str, Any]) -> str:
    """Build graph relationship context string."""
    parts = ["\n### RELATIONSHIP EVIDENCE (Knowledge Graph) ###\n"]

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    if not nodes and not edges:
        parts.append("No relevant relationship evidence found in the graph.\n")
        return "\n".join(parts)

    node_lookup = {node.get("id"): node.get("text") for node in nodes}

    parts.append("Entities Identified:")
    for node in nodes[:50]:  # Cap for context size
        ent_type = node.get("type", "Unknown")
        ent_text = node.get("text", "Unknown")
        case_id = node.get("case_id", "")
        case_info = f" [Case: {case_id}]" if case_id else ""
        parts.append(f"- {ent_text} (Type: {ent_type}){case_info}")

    parts.append("\nRelationships Identified:")
    if not edges:
        parts.append("- No explicit relationships found.")
    for edge in edges[:50]:  # Cap for context size
        from_text = node_lookup.get(edge.get("from"), "Unknown")
        to_text = node_lookup.get(edge.get("to"), "Unknown")
        rel_type = edge.get("type", "UNKNOWN_RELATION")
        parts.append(f"- {from_text} --[{rel_type}]--> {to_text}")

    return "\n".join(parts)
