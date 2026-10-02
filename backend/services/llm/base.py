"""
LLM Base — Abstract provider interface and common response model.

All provider adapters implement this interface so the gateway and
the rest of the application can use any provider interchangeably.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    text: str
    provider: str
    model: str
    latency_seconds: float = 0.0
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    context_strategy: str = "chunk_rag"  # full_document | chunk_rag | summarized
    failover_occurred: bool = False
    failover_from: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base class for LLM provider adapters."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short identifier for this provider (e.g., 'gemini', 'openai')."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model name being used (e.g., 'gpt-4o')."""
        ...

    @property
    @abstractmethod
    def context_window(self) -> int:
        """Maximum context window in tokens for the configured model."""
        ...

    @abstractmethod
    async def generate(
        self,
        query: str,
        context: str,
        chat_history: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
    ) -> LLMResponse:
        """
        Generate a response given query, evidence context, and history.

        Args:
            query: The user's question.
            context: Assembled evidence context string.
            chat_history: Previous conversation turns.
            system_prompt: System-level instructions.
            temperature: Sampling temperature.
            max_output_tokens: Maximum tokens in the response.

        Returns:
            LLMResponse with the generated text and metadata.

        Raises:
            RetryableError: For rate limits, timeouts, temporary failures.
            FatalProviderError: For auth errors, invalid requests, safety blocks.
        """
        ...

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in the given text.
        Used for context budget calculations.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and ready to use."""
        ...

    def get_info(self) -> Dict[str, Any]:
        """Return safe, non-secret provider info for the frontend."""
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "context_window": self.context_window,
            "available": self.is_available(),
        }


class RetryableError(Exception):
    """
    Error that indicates the request can be retried or failed over.
    Includes rate limits (429), temporary server errors (503),
    timeouts, and confirmed quota exhaustion.
    """

    def __init__(self, message: str, provider: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class FatalProviderError(Exception):
    """
    Error that should NOT trigger failover.
    Includes invalid credentials, malformed requests,
    permission failures, and safety rejections.
    """

    def __init__(self, message: str, provider: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
