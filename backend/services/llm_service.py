"""
LLM Service — Backward-compatible wrapper for the Multi-LLM Gateway.

This module preserves the original generate_answer() function signature
so that existing code (rag_service.py, api/rag.py) continues to work
without modification.

All actual LLM logic is now in services.llm.gateway.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


async def generate_answer(
    query: str,
    retrieved_context: str,
    chat_history: List[Dict[str, str]],
    system_prompt: str,
) -> str:
    """
    Backward-compatible wrapper: generates an answer via the Multi-LLM Gateway.

    This function is called by the existing rag_service.query_evidence()
    and api/rag.py endpoints. It delegates to the new LLM gateway which
    handles provider selection, routing, and failover.

    Args:
        query: The investigator's question.
        retrieved_context: Assembled evidence context string.
        chat_history: Previous conversation turns.
        system_prompt: System instructions.

    Returns:
        The LLM-generated answer string.
    """
    from services.llm.gateway import get_gateway

    gateway = get_gateway()

    response = await gateway.generate(
        query=query,
        context=retrieved_context,
        chat_history=chat_history,
        system_prompt=system_prompt,
        task_type="general",
    )

    return response.text
