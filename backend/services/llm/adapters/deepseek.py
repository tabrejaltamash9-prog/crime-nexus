"""
DeepSeek Adapter — DeepSeek API provider.

Implements the LLMProvider interface using the OpenAI-compatible API.
DeepSeek uses the same chat completions format as OpenAI.
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


class DeepSeekAdapter(LLMProvider):
    """DeepSeek API adapter (OpenAI-compatible)."""

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.base_url = os.environ.get(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
        )
        self._model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self._client = None
        self._config = get_model_config("deepseek", self._model)

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return self._config.get("context_window", 65536)

    def is_available(self) -> bool:
        return bool(self.api_key) and self.api_key not in ("", "your_api_key_here")

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text, "deepseek")

    def _get_client(self):
        if self._client is None:
            if not self.is_available():
                raise FatalProviderError(
                    "DEEPSEEK_API_KEY is not configured", "deepseek"
                )
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=120.0,
            )
            logger.info(f"Initialized DeepSeek client with model: {self._model}")
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

            # Chat history
            recent_history = chat_history[-10:] if chat_history else []
            for msg in recent_history:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })

            user_content = (
                f"EVIDENCE CONTEXT:\n"
                f"{'='*60}\n"
                f"{context}\n"
                f"{'='*60}\n\n"
                f"INVESTIGATOR QUESTION:\n{query}\n\n"
                f"Provide a comprehensive, evidence-grounded response with:\n"
                f"1. Executive Summary\n"
                f"2. Detailed Analysis with citations [Doc: filename, Chunk: N]\n"
                f"3. Investigative Notes (patterns, gaps, follow-ups)"
            )
            messages.append({"role": "user", "content": user_content})

            max_retries = 3
            base_delay = 2.0

            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    logger.info(
                        f"DeepSeek request (attempt {attempt + 1}/{max_retries})"
                    )

                    response = await client.chat.completions.create(
                        model=self._model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_output_tokens,
                    )

                    latency = time.time() - start_time
                    usage = response.usage

                    prompt_tokens = completion_tokens = total_tokens = None
                    if usage:
                        prompt_tokens = usage.prompt_tokens
                        completion_tokens = usage.completion_tokens
                        total_tokens = usage.total_tokens

                    logger.info(
                        f"DeepSeek response received. Latency: {latency:.2f}s"
                    )

                    answer = response.choices[0].message.content
                    if not answer:
                        answer = "I was unable to generate a response. Please try rephrasing your question."

                    return LLMResponse(
                        text=answer,
                        provider="deepseek",
                        model=self._model,
                        latency_seconds=latency,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    )

                except openai.RateLimitError as e:
                    if attempt == max_retries - 1:
                        raise RetryableError(
                            f"DeepSeek rate limit: {e}", "deepseek", 429
                        )
                    await asyncio.sleep(base_delay * (2**attempt))

                except (openai.APIConnectionError, openai.APITimeoutError) as e:
                    if attempt == max_retries - 1:
                        raise RetryableError(
                            f"DeepSeek connection error: {e}", "deepseek"
                        )
                    await asyncio.sleep(base_delay * (2**attempt))

                except openai.AuthenticationError as e:
                    raise FatalProviderError(
                        f"DeepSeek auth error: {e}", "deepseek", 401
                    )

                except openai.BadRequestError as e:
                    raise FatalProviderError(
                        f"DeepSeek bad request: {e}", "deepseek", 400
                    )

        except (RetryableError, FatalProviderError):
            raise
        except Exception as e:
            logger.error(f"Unexpected DeepSeek error: {e}")
            raise RetryableError(f"DeepSeek unexpected error: {e}", "deepseek")
