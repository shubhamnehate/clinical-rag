"""
LLM client supporting Anthropic Claude API.
Includes retry logic and mock mode for testing.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    answer: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    raw_response: Optional[object] = None


class LLMClient:
    """
    Anthropic Claude client with retry logic.
    Falls back to MockLLM if ANTHROPIC_API_KEY not set or in test mode.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 2000,
        temperature: float = 0.1,
        max_retries: int = 3,
        mock: bool = False,
    ):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.mock = mock or not self.api_key
        self._client = None

        if not self.mock:
            self._init_client()

    def _init_client(self):
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            self.mock = True

    def generate(self, system_prompt: str, user_message: str) -> LLMResponse:
        if self.mock:
            return self._mock_generate(user_message)

        start = time.time()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                latency = (time.time() - start) * 1000
                return LLMResponse(
                    answer=response.content[0].text,
                    model=self.model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    latency_ms=latency,
                    raw_response=response,
                )
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # exponential backoff

        # All retries failed
        return LLMResponse(
            answer=f"[LLM Error after {self.max_retries} attempts: {last_error}]",
            model=self.model,
            input_tokens=0,
            output_tokens=0,
            latency_ms=(time.time() - start) * 1000,
        )

    def _mock_generate(self, user_message: str) -> LLMResponse:
        """Mock response for testing without API key."""
        # Extract question from message
        question_start = user_message.find("QUESTION:")
        if question_start >= 0:
            question = user_message[question_start + 9:].strip().split("\n")[0]
        else:
            question = user_message[:100]

        context_start = user_message.find("--- Context")
        has_context = context_start >= 0

        if not has_context:
            answer = "The information is not available in the provided records."
        else:
            # Simulate extracting an answer from context
            context_section = user_message[context_start:question_start] if question_start > 0 else user_message[context_start:]
            # Take first 200 chars of context as "answer basis"
            snippet = context_section[:300].strip()
            answer = (
                f"Based on the clinical records: {snippet[:200]}...\n\n"
                f"[Mock response - set ANTHROPIC_API_KEY for real answers]"
            )

        return LLMResponse(
            answer=answer,
            model="mock",
            input_tokens=len(user_message) // 4,
            output_tokens=len(answer) // 4,
            latency_ms=50.0,
        )
