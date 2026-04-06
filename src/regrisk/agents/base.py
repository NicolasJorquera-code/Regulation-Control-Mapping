"""
Base agent infrastructure — the contract every agent implements.

Copied from the skeleton project. Provides BaseAgent ABC, AgentContext,
register_agent decorator, call_llm, call_llm_with_tools, parse_json.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from regrisk.core.transport import AsyncTransportClient


# ---------------------------------------------------------------------------
# Agent registry (populated by @register_agent)
# ---------------------------------------------------------------------------

AGENT_REGISTRY: dict[str, type["BaseAgent"]] = {}


def register_agent(cls: type["BaseAgent"]) -> type["BaseAgent"]:
    """Class decorator — registers an agent subclass by its class name."""
    AGENT_REGISTRY[cls.__name__] = cls
    return cls


# ---------------------------------------------------------------------------
# Runtime context (injected into every agent)
# ---------------------------------------------------------------------------

@dataclass
class AgentContext:
    """Runtime context injected into every agent instance."""

    client: AsyncTransportClient | None
    model: str = "gpt-4o"
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout_seconds: int = 120


# ---------------------------------------------------------------------------
# Abstract base agent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """Abstract base for all agents in the pipeline."""

    def __init__(self, context: AgentContext, name: str | None = None) -> None:
        self.context = context
        self.name = name or self.__class__.__name__
        self.call_count: int = 0

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Run the agent's core logic and return a result dict."""
        ...

    # ---- LLM helpers ----

    async def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a simple system+user message pair and return the assistant text.

        Returns an empty string when no LLM client is available (deterministic mode).
        """
        if self.context.client is None:
            return ""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        resp = await self.context.client.chat_completion(
            messages=messages,
            temperature=temperature if temperature is not None else self.context.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.context.max_tokens,
        )
        self.call_count += 1
        return self._extract_text(resp)

    async def call_llm_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
        max_tool_rounds: int = 5,
        tool_choice: str | dict | None = None,
    ) -> dict[str, Any]:
        """Multi-round tool-calling loop."""
        if self.context.client is None:
            return {"role": "assistant", "content": ""}

        conversation = list(messages)

        for _round in range(max_tool_rounds):
            resp = await self.context.client.chat_completion(
                messages=conversation,
                tools=tools,
                tool_choice=tool_choice,
                temperature=self.context.temperature,
                max_tokens=self.context.max_tokens,
            )
            self.call_count += 1

            msg = resp.get("choices", [{}])[0].get("message", {})
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                return msg

            conversation.append(msg)
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    args = {}
                result = tool_executor(tool_name, args)
                conversation.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result),
                })

            tool_choice = None

        return conversation[-1] if conversation else {"role": "assistant", "content": ""}

    # ---- JSON parsing helper ----

    @staticmethod
    def parse_json(text: str) -> dict[str, Any]:
        """Robustly extract a JSON object from LLM output."""
        if not text:
            return {}

        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = re.sub(r"```", "", cleaned)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return {}

    # ---- internals ----

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        """Pull assistant text from an OpenAI-style response dict."""
        choices = response.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""
