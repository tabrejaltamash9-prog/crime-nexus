"""
Multi-LLM Gateway — Intelligent routing, failover, and context validation.

This is the single entry point for all LLM calls in the application.
It handles:
  1. Provider selection based on task type and context size
  2. Context-window validation before every call
  3. Bounded retries within each provider
  4. Cross-provider failover on retryable errors
  5. Usage/latency metadata in responses
  6. Backward-compatible generate_answer() function
"""

import logging
import time
from typing import List, Dict, Any, Optional

from services.llm.base import (
    LLMProvider,
    LLMResponse,
    RetryableError,
    FatalProviderError,
)
from services.llm.config import (
    get_provider_priority,
    get_default_provider,
    is_failover_enabled,
    get_answer_token_reserve,
    get_max_context_ratio,
    get_model_config,
    get_available_providers,
)
from services.llm.token_estimator import check_context_budget

logger = logging.getLogger(__name__)

# ── Provider Registry ────────────────────────────────────────────────────────

_adapters: Dict[str, LLMProvider] = {}


def _init_adapters():
    """Lazily initialize all available provider adapters."""
    global _adapters
    if _adapters:
        return

    from services.llm.adapters.gemini import GeminiAdapter
    from services.llm.adapters.openai_adapter import OpenAIAdapter
    from services.llm.adapters.anthropic_adapter import AnthropicAdapter
    from services.llm.adapters.deepseek import DeepSeekAdapter
    from services.llm.adapters.nemotron import NemotronAdapter

    _adapters = {
        "gemini": GeminiAdapter(),
        "openai": OpenAIAdapter(),
        "anthropic": AnthropicAdapter(),
        "deepseek": DeepSeekAdapter(),
        "nemotron": NemotronAdapter(),
    }
    logger.info(
        f"LLM adapters initialized: "
        f"{[k for k, v in _adapters.items() if v.is_available()]}"
    )


def get_adapter(provider_name: str) -> Optional[LLMProvider]:
    """Get a specific provider adapter by name."""
    _init_adapters()
    return _adapters.get(provider_name)


# ── Gateway Class ────────────────────────────────────────────────────────────


class LLMGateway:
    """
    Multi-LLM Gateway with intelligent routing and failover.

    Usage:
        gateway = LLMGateway()
        response = await gateway.generate(
            query="Who are the suspects?",
            context="evidence text...",
            system_prompt="You are an investigation assistant.",
            task_type="local_analysis",
        )
    """

    def __init__(self):
        _init_adapters()

    async def generate(
        self,
        query: str,
        context: str,
        chat_history: List[Dict[str, str]] = None,
        system_prompt: str = "",
        provider: Optional[str] = None,
        task_type: str = "general",
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        require_long_context: bool = False,
    ) -> LLMResponse:
        """
        Generate a response with automatic routing and failover.

        Args:
            query: The user's question.
            context: Assembled evidence context.
            chat_history: Conversation history.
            system_prompt: System instructions.
            provider: Explicitly request a specific provider (optional).
            task_type: 'global_search' | 'local_analysis' | 'general'
            temperature: Sampling temperature.
            max_output_tokens: Max output tokens.
            require_long_context: If True, only use models with large context windows.

        Returns:
            LLMResponse with the answer and metadata.

        Raises:
            RuntimeError: If no provider can handle the request.
        """
        if chat_history is None:
            chat_history = []

        # Build the provider order
        provider_order = self._get_provider_order(
            preferred=provider,
            task_type=task_type,
            require_long_context=require_long_context,
        )

        if not provider_order:
            raise RuntimeError(
                "No LLM providers are available. Check your API key configuration."
            )

        # Track failover
        original_provider = provider_order[0]
        errors = []

        for i, provider_name in enumerate(provider_order):
            adapter = get_adapter(provider_name)
            if adapter is None or not adapter.is_available():
                continue

            # Validate context fits this provider's window
            budget = check_context_budget(
                system_prompt=system_prompt,
                query=query,
                context=context,
                chat_history=chat_history,
                context_window=adapter.context_window,
                answer_reserve=get_answer_token_reserve(),
                max_ratio=get_max_context_ratio(),
                provider=provider_name,
            )

            if not budget["fits"]:
                logger.warning(
                    f"Context too large for {provider_name} "
                    f"({budget['estimated_tokens']} tokens > "
                    f"{budget['available_tokens']} available). Trying next provider."
                )
                errors.append(
                    f"{provider_name}: context too large "
                    f"({budget['estimated_tokens']}>{budget['available_tokens']})"
                )
                continue

            try:
                logger.info(
                    f"Sending request to {provider_name} "
                    f"(context utilization: {budget['utilization']:.1%})"
                )

                response = await adapter.generate(
                    query=query,
                    context=context,
                    chat_history=chat_history,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )

                # Mark failover if we're not on the first provider
                if i > 0:
                    response.failover_occurred = True
                    response.failover_from = original_provider
                    logger.info(
                        f"Failover from {original_provider} to {provider_name}"
                    )

                return response

            except FatalProviderError as e:
                # Fatal errors: do NOT fail over
                logger.error(f"Fatal error from {provider_name}: {e}")
                raise RuntimeError(
                    f"LLM provider error ({provider_name}): {e}"
                )

            except RetryableError as e:
                logger.warning(
                    f"Retryable error from {provider_name}: {e}"
                )
                errors.append(f"{provider_name}: {e}")

                if not is_failover_enabled():
                    raise RuntimeError(
                        f"LLM provider error ({provider_name}): {e}. "
                        f"Failover is disabled."
                    )

                # Continue to next provider
                continue

            except Exception as e:
                logger.error(
                    f"Unexpected error from {provider_name}: {e}"
                )
                errors.append(f"{provider_name}: {e}")
                continue

        # All providers exhausted
        error_summary = "; ".join(errors) if errors else "No available providers"
        raise RuntimeError(
            f"All LLM providers failed or were incompatible. Errors: {error_summary}"
        )

    def _get_provider_order(
        self,
        preferred: Optional[str] = None,
        task_type: str = "general",
        require_long_context: bool = False,
    ) -> List[str]:
        """
        Determine the ordered list of providers to try.

        Logic:
          1. If a specific provider is requested and available, put it first.
          2. Otherwise, use the configured priority order.
          3. Filter out unavailable providers.
          4. If require_long_context, filter out providers with small context windows.
        """
        priority = get_provider_priority()

        # If a specific provider is requested, put it first
        if preferred and preferred in _adapters:
            if preferred in priority:
                priority.remove(preferred)
            priority.insert(0, preferred)
        else:
            # Use default provider first
            default = get_default_provider()
            if default in priority:
                priority.remove(default)
            priority.insert(0, default)

        # Filter to available adapters
        available = [
            p for p in priority
            if p in _adapters and _adapters[p].is_available()
        ]

        # Filter for long-context capability if required
        if require_long_context:
            long_ctx = []
            for p in available:
                adapter = _adapters[p]
                if adapter.context_window >= 100000:
                    long_ctx.append(p)
            if long_ctx:
                available = long_ctx

        return available

    def get_providers_info(self) -> List[Dict[str, Any]]:
        """Return safe (no-secrets) info about all configured providers."""
        _init_adapters()
        info = []
        for name, adapter in _adapters.items():
            info.append(adapter.get_info())
        return info


# ── Module-level Singleton ───────────────────────────────────────────────────

_gateway: Optional[LLMGateway] = None


def get_gateway() -> LLMGateway:
    """Get or create the singleton LLM gateway."""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
