"""
Base agent infrastructure — the contract every agent implements.

Provides BaseAgent ABC, AgentContext, call_llm, call_llm_with_tools, parse_json.
"""

from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from regrisk.core.transport import AsyncTransportClient

logger = logging.getLogger(__name__)


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
            logger.info("[%s] call #%d — no LLM client, using deterministic fallback", self.name, self.call_count + 1)
            return ""

        # Update trace context so transport wrapper knows which agent is calling
        from regrisk.tracing.decorators import get_current_trace_context, set_current_trace_context
        ctx = get_current_trace_context()
        set_current_trace_context(node_name=ctx.get("node_name", ""), agent_name=self.name)

        call_num = self.call_count + 1
        sys_len = len(system_prompt)
        usr_len = len(user_prompt)
        logger.info(
            "[%s] call #%d — sending request (system=%d chars, user=%d chars, max_tokens=%d)",
            self.name, call_num, sys_len, usr_len,
            max_tokens if max_tokens is not None else self.context.max_tokens,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        t0 = time.perf_counter()
        resp = await self.context.client.chat_completion(
            messages=messages,
            temperature=temperature if temperature is not None else self.context.temperature,
            max_tokens=max_tokens if max_tokens is not None else self.context.max_tokens,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.call_count += 1

        text = self._extract_text(resp)
        usage = resp.get("usage", {})
        logger.info(
            "[%s] call #%d — response received (%.1fs, %d chars, tokens: %s/%s/%s)",
            self.name, self.call_count, elapsed_ms / 1000,
            len(text),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            usage.get("total_tokens", "?"),
        )
        return text

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

        # Update trace context
        from regrisk.tracing.decorators import get_current_trace_context, set_current_trace_context
        ctx = get_current_trace_context()
        set_current_trace_context(node_name=ctx.get("node_name", ""), agent_name=self.name)

        conversation = list(messages)

        for _round in range(max_tool_rounds):
            logger.info("[%s] tool-call round %d/%d", self.name, _round + 1, max_tool_rounds)
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
