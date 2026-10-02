"""
Gemini Adapter — Google Gemini API provider.

Refactored from the original GeminiProvider in llm_service.py
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


class GeminiAdapter(LLMProvider):
    """Google Gemini API adapter."""

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self._model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
        self._client = None
        self._config = get_model_config("gemini", self._model)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return self._config.get("context_window", 1048576)

    def is_available(self) -> bool:
        return bool(self.api_key) and self.api_key not in ("", "your_api_key_here")

    def estimate_tokens(self, text: str) -> int:
        return estimate_tokens(text, "gemini")

    def _get_client(self):
        if self._client is None:
            if not self.is_available():
                raise FatalProviderError(
                    "GEMINI_API_KEY is not configured", "gemini"
                )
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            logger.info(f"Initialized Gemini client with model: {self._model}")
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
            from google.genai import types
            from google.genai.errors import APIError

            contents = []

            # Add chat history (cap at last 10 turns)
            recent_history = chat_history[-10:] if chat_history else []
            for msg in recent_history:
                role = "user" if msg.get("role") == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg.get("content", ""))],
                    )
                )

            # Context priming
            context_message = (
                f"I am providing you with evidence documents from an active criminal investigation. "
                f"Review them carefully, then answer my investigator question that follows.\n\n"
                f"EVIDENCE CONTEXT:\n"
                f"{'='*60}\n"
                f"{context}\n"
                f"{'='*60}\n\n"
                f"When I ask my question, respond with:\n"
                f"1. **## Executive Summary** — A 3-5 sentence overview of key findings\n"
                f"2. **## Detailed Analysis** — Thorough walkthrough with inline citations "
                f"[Doc: filename, Chunk: N] for every factual claim. "
                f"Bold all names, dates, locations, phone numbers, and vehicles.\n"
                f"3. **## Investigative Notes** — Patterns, connections, gaps, contradictions, "
                f"and recommended follow-up actions.\n\n"
                f"Your response MUST be at least 300 words. Write as if preparing an intelligence briefing."
            )
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=context_message)],
                )
            )

            contents.append(
                types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(
                            text="Understood. I have reviewed all the evidence documents. "
                            "I will provide a comprehensive, multi-section intelligence briefing "
                            "with Executive Summary, Detailed Analysis with full citations, and "
                            "Investigative Notes. Please proceed with your question."
                        )
                    ],
                )
            )

            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text=f"INVESTIGATOR QUESTION:\n{query}\n\n"
                            f"Remember: Provide the full multi-section briefing as instructed. "
                            f"Be thorough and detailed."
                        )
                    ],
                )
            )

            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )

            max_retries = 3
            base_delay = 2.0

            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    logger.info(
                        f"Gemini request (attempt {attempt + 1}/{max_retries})"
                    )

                    response = await client.aio.models.generate_content(
                        model=self._model,
                        contents=contents,
                        config=config,
                    )

                    latency = time.time() - start_time
                    logger.info(f"Gemini response received. Latency: {latency:.2f}s")

                    answer = response.text
                    if not answer:
                        answer = "I was unable to generate a response. Please try rephrasing your question."

                    return LLMResponse(
                        text=answer,
                        provider="gemini",
                        model=self._model,
                        latency_seconds=latency,
                    )

                except APIError as e:
                    if e.code in (503, 429) or "503" in str(e) or "429" in str(e):
                        if attempt == max_retries - 1:
                            raise RetryableError(
                                f"Gemini API error after {max_retries} attempts: {e}",
                                "gemini",
                                e.code,
                            )
                        await asyncio.sleep(base_delay * (2**attempt))
                    else:
                        raise FatalProviderError(
                            f"Gemini API error: {e}", "gemini", e.code
                        )

        except (RetryableError, FatalProviderError):
            raise
        except Exception as e:
            logger.error(f"Unexpected Gemini error: {e}")
            raise RetryableError(f"Gemini unexpected error: {e}", "gemini")
