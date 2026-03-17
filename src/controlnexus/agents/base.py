"""Base agent abstraction for ControlNexus.

Provides AgentContext (shared runtime context), BaseAgent (ABC with
async call_llm helper), and @register_agent decorator for the
global agent registry.
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from controlnexus.core.transport import AsyncTransportClient
from controlnexus.exceptions import ExternalServiceException, ValidationException

logger = logging.getLogger(__name__)

# -- Agent Registry ------------------------------------------------------------

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}


def register_agent(cls: type[BaseAgent]) -> type[BaseAgent]:
    """Class decorator that registers an agent in the global registry."""
    AGENT_REGISTRY[cls.__name__] = cls
    return cls


# -- Agent Context -------------------------------------------------------------


@dataclass
class AgentContext:
    """Shared runtime context passed to every agent."""

    client: AsyncTransportClient | None = None
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 1400
    timeout_seconds: int = 120


# -- Base Agent ----------------------------------------------------------------


class BaseAgent(ABC):
    """Abstract base class for all ControlNexus agents.

    Subclasses must implement ``async execute(**kwargs) -> dict[str, Any]``.
    """

    def __init__(self, context: AgentContext, name: str | None = None) -> None:
        self.context = context
        self.name = name or self.__class__.__name__
        self.call_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    @property
    def client(self) -> AsyncTransportClient | None:
        return self.context.client

    @property
    def model(self) -> str:
        return self.context.model

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Run the agent's core logic."""
        ...

    def _extract_text_from_openai_style(self, payload: dict[str, Any]) -> str:
        """Extract text content from an OpenAI-style chat completion response."""
        choices = payload.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if "text" in block:
                            parts.append(str(block.get("text", "")))
                        elif block.get("type") == "output_text":
                            parts.append(str(block.get("text", "")))
                        elif "content" in block:
                            parts.append(str(block.get("content", "")))
                    else:
                        parts.append(str(block))
                return "\n".join(p for p in parts if p).strip()
        return str(payload)

    async def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a system + user prompt to the LLM and return the text response."""
        if self.client is None:
            raise ExternalServiceException("No LLM client configured")

        self.call_count += 1
        call_number = self.call_count
        effective_temp = temperature if temperature is not None else self.context.temperature
        effective_max = max_tokens if max_tokens is not None else self.context.max_tokens

        logger.info("LLM call #%d started (%s)", call_number, self.name)
        t0 = time.monotonic()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response_json = await self.client.chat_completion(
            messages=messages,
            temperature=effective_temp,
            max_tokens=effective_max,
        )

        usage = response_json.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        self.total_input_tokens += prompt_tokens
        self.total_output_tokens += completion_tokens

        elapsed = time.monotonic() - t0
        logger.info(
            "LLM call #%d completed (%s, %.3fs, %d+%d tokens)",
            call_number, self.name, elapsed, prompt_tokens, completion_tokens,
        )
        return self._extract_text_from_openai_style(response_json)

    @staticmethod
    def parse_json(text: str) -> dict[str, Any]:
        """Parse JSON from LLM output, stripping markdown code fences if present."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            candidate = text.strip()
            candidate = re.sub(r"^```(?:json)?", "", candidate).strip()
            candidate = re.sub(r"```$", "", candidate).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as exc:
                logger.error("JSON parse failure: %s", candidate[:300])
                raise ValidationException(
                    f"Failed to parse JSON from LLM response: {candidate[:200]}"
                ) from exc
