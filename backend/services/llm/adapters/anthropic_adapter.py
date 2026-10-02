"""
Anthropic Adapter — Anthropic Claude API provider.

Implements the LLMProvider interface using the Anthropic Python SDK.
Supports Claude Sonnet, Haiku, and other models.
"""

import asyncio
import logging
import os
import time
from typing import List, Dict, Any

from services.llm.base import LLMProvider, LLMResponse, RetryableError, FatalProviderError
from services.llm.config import get_model_config
from services.llm.token_estimator import estimate_tokens

logger = logging.getLogger(__name__)


class AnthropicAdapter(LLMProvider):
    """Anthropic Claude API adapter."""

    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._client = None
        self._config = get_model_config("anthropic", self._model)

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return self._config.get("context_window", 200000)

    def is_available(self) -> bool:
        return bool(self.api_key) and self.api_key not in ("", "your_api_key_here")

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text, "anthropic")

    def _get_client(self):
        if self._client is None:
            if not self.is_available():
                raise FatalProviderError(
                    "ANTHROPIC_API_KEY is not configured", "anthropic"
                )
            try:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(
                    api_key=self.api_key,
                    timeout=120.0,
                )
                logger.info(f"Initialized Anthropic client with model: {self._model}")
            except ImportError:
                raise FatalProviderError(
                    "anthropic package is not installed. Run: pip install anthropic",
                    "anthropic",
                )
        return self._client

    async def generate(
        self,
        query: str,
        context: str,
        chat_history: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
    ) -> LLMResponse:
        try:
            client = self._get_client()

            messages = []

            # Chat history (last 10 turns)
            recent_history = chat_history[-10:] if chat_history else []
            for msg in recent_history:
                role = msg.get("role", "user")
                # Claude uses "assistant" not "model"
                if role == "model":
                    role = "assistant"
                messages.append({
                    "role": role,
                    "content": msg.get("content", ""),
                })

            # Context + query
            user_content = (
                f"EVIDENCE CONTEXT:\n"
                f"{'='*60}\n"
                f"{context}\n"
                f"{'='*60}\n\n"
                f"INVESTIGATOR QUESTION:\n{query}\n\n"
                f"Provide a comprehensive, evidence-grounded response with:\n"
                f"1. Executive Summary\n"
                f"2. Detailed Analysis with citations [Doc: filename, Chunk: N]\n"
                f"3. Investigative Notes (patterns, gaps, follow-ups)\n"
                f"Bold all names, dates, locations, phone numbers, and vehicles."
            )
            messages.append({"role": "user", "content": user_content})

            max_retries = 3
            base_delay = 2.0

            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    logger.info(
                        f"Anthropic request (attempt {attempt + 1}/{max_retries})"
                    )

                    response = await client.messages.create(
                        model=self._model,
                        max_tokens=max_output_tokens,
                        system=system_prompt,
                        messages=messages,
                        temperature=temperature,
                    )

                    latency = time.time() - start_time
                    usage = response.usage

                    prompt_tokens = completion_tokens = total_tokens = None
                    if usage:
                        prompt_tokens = usage.input_tokens
                        completion_tokens = usage.output_tokens
                        total_tokens = (usage.input_tokens or 0) + (usage.output_tokens or 0)

                    logger.info(
                        f"Anthropic response received. Latency: {latency:.2f}s"
                    )

                    # Extract text from content blocks
                    answer = ""
                    for block in response.content:
                        if hasattr(block, "text"):
                            answer += block.text

                    if not answer:
                        answer = "I was unable to generate a response. Please try rephrasing your question."

                    return LLMResponse(
                        text=answer,
                        provider="anthropic",
                        model=self._model,
                        latency_seconds=latency,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    )

                except Exception as e:
                    error_str = str(e)
                    error_type = type(e).__name__

                    # Check for retryable errors
                    if "rate_limit" in error_type.lower() or "429" in error_str:
                        if attempt == max_retries - 1:
                            raise RetryableError(
                                f"Anthropic rate limit: {e}", "anthropic", 429
                            )
                        await asyncio.sleep(base_delay * (2**attempt))

                    elif "overloaded" in error_str.lower() or "529" in error_str:
                        if attempt == max_retries - 1:
                            raise RetryableError(
                                f"Anthropic overloaded: {e}", "anthropic", 529
                            )
                        await asyncio.sleep(base_delay * (2**attempt))

                    elif "timeout" in error_type.lower() or "connection" in error_type.lower():
                        if attempt == max_retries - 1:
                            raise RetryableError(
                                f"Anthropic connection error: {e}", "anthropic"
                            )
                        await asyncio.sleep(base_delay * (2**attempt))

                    elif "authentication" in error_type.lower() or "401" in error_str:
                        raise FatalProviderError(
                            f"Anthropic auth error: {e}", "anthropic", 401
                        )

                    elif "invalid_request" in error_type.lower() or "400" in error_str:
                        raise FatalProviderError(
                            f"Anthropic bad request: {e}", "anthropic", 400
                        )

                    else:
                        if attempt == max_retries - 1:
                            raise RetryableError(
                                f"Anthropic error: {e}", "anthropic"
                            )
                        await asyncio.sleep(base_delay * (2**attempt))

        except (RetryableError, FatalProviderError):
            raise
        except Exception as e:
            logger.error(f"Unexpected Anthropic error: {e}")
            raise RetryableError(f"Anthropic unexpected error: {e}", "anthropic")
