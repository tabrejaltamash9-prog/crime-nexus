"""
Token Estimator — Approximate token counting for context budget management.

Uses tiktoken for OpenAI-compatible models and character-based heuristics
for other providers. This is used to decide whether full documents fit
within a model's context window before making the API call.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded tiktoken encoding
_tiktoken_encoding = None


def _get_tiktoken_encoding():
    """Lazy-load tiktoken cl100k_base encoding (used by GPT-4, Claude, etc.)."""
    global _tiktoken_encoding
    if _tiktoken_encoding is None:
        try:
            import tiktoken
            _tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
            logger.info("tiktoken cl100k_base encoding loaded")
        except ImportError:
            logger.warning(
                "tiktoken not installed — using character-based estimation. "
                "Install tiktoken for more accurate token counting."
            )
    return _tiktoken_encoding


def estimate_tokens(text: str, provider: str = "default") -> int:
    """
    Estimate the number of tokens in the given text.

    For OpenAI and Anthropic, tries tiktoken (cl100k_base) for accuracy.
    For all providers, falls back to a character-based heuristic:
      ~4 characters per token for English text (conservative estimate).

    Args:
        text: The text to estimate tokens for.
        provider: Provider name for model-specific counting.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0

    # Try tiktoken for supported providers
    if provider in ("openai", "anthropic", "default"):
        encoding = _get_tiktoken_encoding()
        if encoding is not None:
            try:
                return len(encoding.encode(text))
            except Exception:
                pass

    # Fallback: character-based heuristic
    # English text averages ~4 chars/token; we use 3.5 to be conservative
    return max(1, int(len(text) / 3.5))


def estimate_messages_tokens(
    system_prompt: str,
    query: str,
    context: str,
    chat_history: list,
    provider: str = "default",
) -> int:
    """
    Estimate total tokens for a complete LLM request.

    Accounts for:
      - System prompt
      - Chat history
      - Evidence context
      - User query
      - Message formatting overhead (~4 tokens per message)
    """
    total = 0

    # System prompt
    total += estimate_tokens(system_prompt, provider)

    # Chat history
    for msg in chat_history:
        total += estimate_tokens(msg.get("content", ""), provider) + 4  # message overhead

    # Context + query
    total += estimate_tokens(context, provider)
    total += estimate_tokens(query, provider)

    # Formatting overhead (message boundaries, role tokens, etc.)
    total += 50  # conservative overhead for message structure

    return total


def check_context_budget(
    system_prompt: str,
    query: str,
    context: str,
    chat_history: list,
    context_window: int,
    answer_reserve: int = 4096,
    max_ratio: float = 0.85,
    provider: str = "default",
) -> dict:
    """
    Check if the assembled context fits within the model's budget.

    Returns a dict with:
      - fits: bool — whether everything fits
      - estimated_tokens: int — total estimated input tokens
      - available_tokens: int — usable context budget
      - context_window: int — full model limit
      - overflow_tokens: int — how many tokens over budget (0 if fits)
      - utilization: float — fraction of context used (0.0 to 1.0+)
    """
    usable_window = int(context_window * max_ratio) - answer_reserve
    estimated = estimate_messages_tokens(
        system_prompt, query, context, chat_history, provider
    )

    overflow = max(0, estimated - usable_window)
    utilization = estimated / usable_window if usable_window > 0 else 999.0

    return {
        "fits": estimated <= usable_window,
        "estimated_tokens": estimated,
        "available_tokens": usable_window,
        "context_window": context_window,
        "overflow_tokens": overflow,
        "utilization": round(utilization, 3),
    }
