"""
Nemotron Adapter — NVIDIA Nemotron API provider.

Refactored from the original NemotronProvider in llm_service.py
to implement the standardized LLMProvider interface.
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


class NemotronAdapter(LLMProvider):
    """NVIDIA Nemotron API adapter (OpenAI-compatible)."""

    def __init__(self):
        self.api_key = os.environ.get("NVIDIA_API_KEY")
        self.base_url = os.environ.get(
            "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
        self._model = os.environ.get(
            "NVIDIA_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"
        )
        self._client = None
        self._config = get_model_config("nemotron", self._model)

    @property
    def provider_name(self) -> str:
        return "nemotron"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return self._config.get("context_window", 32768)

    def is_available(self) -> bool:
        return bool(self.api_key) and self.api_key not in (
            "",
            "your_nvidia_api_key_here",
        )

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text, "nemotron")

    def _get_client(self):
        if self._client is None:
            if not self.is_available():
                raise FatalProviderError(
                    "NVIDIA_API_KEY is not configured", "nemotron"
                )
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=60.0,
            )
            logger.info(f"Initialized Nemotron client with model: {self._model}")
        return self._client

    async def generate(
        self,
        query: str,
        context: str,
        chat_history: List[Dict[str, str]],
        system_prompt: str,
        temperature: float = 0.3,
        max_output_tokens: int = 4096,
    ) -> LLMResponse:
        try:
            client = self._get_client()
            import openai

            messages = [{"role": "system", "content": system_prompt}]

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
            )
            messages.append({"role": "user", "content": user_content})

            max_retries = 3
            base_delay = 2.0

            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    logger.info(
                        f"Nemotron request (attempt {attempt + 1}/{max_retries})"
                    )

                    response = await client.chat.completions.create(
                        model=self._model,
                        messages=messages,
                        temperature=temperature,
                        top_p=0.95,
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
                        f"Nemotron response received. Latency: {latency:.2f}s"
                    )

                    answer = response.choices[0].message.content
                    if not answer:
                        answer = "I was unable to generate a response. Please try rephrasing your question."

                    return LLMResponse(
                        text=answer,
                        provider="nemotron",
                        model=self._model,
                        latency_seconds=latency,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    )

                except openai.RateLimitError as e:
                    if attempt == max_retries - 1:
                        raise RetryableError(
                            f"Nemotron rate limit: {e}", "nemotron", 429
                        )
                    await asyncio.sleep(base_delay * (2**attempt))

                except (openai.APIConnectionError, openai.APITimeoutError) as e:
                    if attempt == max_retries - 1:
                        raise RetryableError(
                            f"Nemotron connection error: {e}", "nemotron"
                        )
                    await asyncio.sleep(base_delay * (2**attempt))

                except openai.AuthenticationError as e:
                    raise FatalProviderError(
                        f"Nemotron auth error: {e}", "nemotron", 401
                    )

        except (RetryableError, FatalProviderError):
            raise
        except Exception as e:
            logger.error(f"Unexpected Nemotron error: {e}")
            raise RetryableError(f"Nemotron unexpected error: {e}", "nemotron")
