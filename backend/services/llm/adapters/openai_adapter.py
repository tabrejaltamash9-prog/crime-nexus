"""
OpenAI Adapter — OpenAI GPT API provider.

Implements the LLMProvider interface using the OpenAI Python SDK.
Supports GPT-4o, GPT-4o-mini, and other chat completion models.
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


class OpenAIAdapter(LLMProvider):
    """OpenAI GPT API adapter."""

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._client = None
        self._config = get_model_config("openai", self._model)

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return self._config.get("context_window", 128000)

    def is_available(self) -> bool:
        return bool(self.api_key) and self.api_key not in ("", "your_api_key_here")

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text, "openai")

    def _get_client(self):
        if self._client is None:
            if not self.is_available():
                raise FatalProviderError(
                    "OPENAI_API_KEY is not configured", "openai"
                )
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                timeout=120.0,
            )
            logger.info(f"Initialized OpenAI client with model: {self._model}")
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
            import openai

            messages = [{"role": "system", "content": system_prompt}]

            # Chat history (last 10 turns)
            recent_history = chat_history[-10:] if chat_history else []
            for msg in recent_history:
                messages.append({
                    "role": msg.get("role", "user"),
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
                        f"OpenAI request (attempt {attempt + 1}/{max_retries})"
                    )

                    response = await client.chat.completions.create(
                        model=self._model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_output_tokens,
                    )

                    latency = time.time() - start_time
                    usage = response.usage

                    token_info = ""
                    prompt_tokens = completion_tokens = total_tokens = None
                    if usage:
                        prompt_tokens = usage.prompt_tokens
                        completion_tokens = usage.completion_tokens
                        total_tokens = usage.total_tokens
                        token_info = f", Tokens: {total_tokens}"

                    logger.info(
                        f"OpenAI response received. Latency: {latency:.2f}s{token_info}"
                    )

                    answer = response.choices[0].message.content
                    if not answer:
                        answer = "I was unable to generate a response. Please try rephrasing your question."

                    return LLMResponse(
                        text=answer,
                        provider="openai",
                        model=self._model,
                        latency_seconds=latency,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    )

                except openai.RateLimitError as e:
                    if attempt == max_retries - 1:
                        raise RetryableError(
                            f"OpenAI rate limit after {max_retries} attempts: {e}",
                            "openai",
                            429,
                        )
                    await asyncio.sleep(base_delay * (2**attempt))

                except (openai.APIConnectionError, openai.APITimeoutError) as e:
                    if attempt == max_retries - 1:
                        raise RetryableError(
                            f"OpenAI connection/timeout error: {e}", "openai"
                        )
                    await asyncio.sleep(base_delay * (2**attempt))

                except openai.AuthenticationError as e:
                    raise FatalProviderError(
                        f"OpenAI authentication error: {e}", "openai", 401
                    )

                except openai.BadRequestError as e:
                    raise FatalProviderError(
                        f"OpenAI bad request: {e}", "openai", 400
                    )

        except (RetryableError, FatalProviderError):
            raise
        except Exception as e:
            logger.error(f"Unexpected OpenAI error: {e}")
            raise RetryableError(f"OpenAI unexpected error: {e}", "openai")
