"""
Base agent infrastructure — the contract every agent implements.

Pattern:
- ``BaseAgent`` is an ABC with one required method: ``execute(**kwargs)``.
- ``AgentContext`` bundles the LLM transport client + runtime settings so
  agents don't reach into globals or environment variables.
- ``call_llm()`` and ``call_llm_with_tools()`` handle the low-level
  LLM interaction (retries, JSON parsing, multi-round tool loops).
- ``@register_agent`` decorator auto-registers subclasses in a global
  ``AGENT_REGISTRY`` dict for discovery/introspection.

How tools work:
    Agents don't import tool implementations directly.  Instead, the
    graph node passes a *tool executor* closure (built by
    ``build_tool_executor(config)``) that dispatches by tool name.
    This keeps agents decoupled from tool storage and makes testing
    trivial (inject a mock executor).

Deterministic fallback:
    Every agent should have a code path that works when ``context.client``
    is ``None`` (no LLM available).  This enables fully deterministic
    testing and graceful degradation in production.
"""

from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from skeleton.core.transport import AsyncTransportClient
from skeleton.exceptions import AgentError


# ---------------------------------------------------------------------------
# Agent registry (populated by @register_agent)
# ---------------------------------------------------------------------------

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {}


def register_agent(cls: type[BaseAgent]) -> type[BaseAgent]:
    """Class decorator — registers an agent subclass by its class name.

    Usage::

        @register_agent
        class PlannerAgent(BaseAgent):
            ...
    """
    AGENT_REGISTRY[cls.__name__] = cls
    return cls


# ---------------------------------------------------------------------------
# Runtime context (injected into every agent)
# ---------------------------------------------------------------------------

@dataclass
class AgentContext:
    """Runtime context injected into every agent instance.

    # CUSTOMIZE: Add fields like ``memory_store``, ``run_id``, ``user_id``.
    """

    client: AsyncTransportClient | None
    model: str = "gpt-4o"
    temperature: float = 0.2
    max_tokens: int = 1400
    timeout_seconds: int = 120


# ---------------------------------------------------------------------------
# Abstract base agent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """Abstract base for all agents in the pipeline.

    Subclasses *must* implement ``execute(**kwargs) -> dict[str, Any]``.
    They *should* use ``call_llm`` / ``call_llm_with_tools`` for LLM
    interaction rather than hitting the transport client directly.
    """

    def __init__(self, context: AgentContext, name: str | None = None) -> None:
        self.context = context
        self.name = name or self.__class__.__name__
        self.call_count: int = 0

    @abstractmethod
    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Run the agent's core logic and return a result dict.

        # CUSTOMIZE: Define the input/output contract per agent subclass.
        """
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
        """Multi-round tool-calling loop.

        The LLM may emit tool calls; this method executes them via
        *tool_executor*, appends the results, and re-prompts until the
        LLM returns a final text response (no more tool calls) or
        ``max_tool_rounds`` is exhausted.

        Returns the final LLM response dict (``choices[0].message``).

        # CUSTOMIZE: Adjust ``max_tool_rounds`` for your agents' tool usage patterns.
        """
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
                return msg  # done — LLM returned a final text response

            # Execute each tool call and append results
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

            # After first round, stop forcing tool_choice
            tool_choice = None

        # max rounds exhausted — return last message as-is
        return conversation[-1] if conversation else {"role": "assistant", "content": ""}

    # ---- JSON parsing helper ----

    @staticmethod
    def parse_json(text: str) -> dict[str, Any]:
        """Robustly extract a JSON object from LLM output.

        Handles markdown fences, leading prose, and trailing text.
        """
        if not text:
            return {}

        # Strip markdown code fences
        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = re.sub(r"```", "", cleaned)
        cleaned = cleaned.strip()

        # Try direct parse first
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Try to find a JSON object in the text
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
