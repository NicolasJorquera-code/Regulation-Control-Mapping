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
from controlnexus.tools.xml_tool_parser import (
    format_tool_results,
    parse_xml_tool_calls,
    strip_tool_calls,
)

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
            call_number,
            self.name,
            elapsed,
            prompt_tokens,
            completion_tokens,
        )
        return self._extract_text_from_openai_style(response_json)

    async def call_llm_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_executor: Any,
        *,
        max_tool_rounds: int = 5,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Multi-turn LLM call with tool execution loop.

        Sends *messages* to the LLM with the given *tools*.  If the
        response contains ``tool_calls``, executes each via *tool_executor*,
        appends tool-result messages, and re-sends.  Repeats until the LLM
        returns a content-only response or *max_tool_rounds* is reached.

        If the provider ignores the ``tools`` parameter (e.g. ICA/Granite)
        the response will contain content only on round 1 — this is expected
        and the method returns that content immediately.

        Returns the final assistant message dict with an extra
        ``_tool_calls_count`` key indicating how many tool invocations
        actually occurred.
        """
        if self.client is None:
            raise ExternalServiceException("No LLM client configured")

        effective_temp = temperature if temperature is not None else self.context.temperature
        effective_max = max_tokens if max_tokens is not None else self.context.max_tokens
        current_messages = list(messages)
        total_tool_calls = 0
        # After the first round with tool_choice="required", relax to "auto"
        # so the LLM can produce a content-only final response.
        active_tool_choice = tool_choice

        for round_idx in range(max_tool_rounds):
            self.call_count += 1
            call_number = self.call_count

            logger.info(
                "LLM round %d started (%s, call #%d, tools offered: %d)",
                round_idx + 1,
                self.name,
                call_number,
                len(tools),
            )
            t0 = time.monotonic()

            response_json = await self.client.chat_completion(
                messages=current_messages,
                temperature=effective_temp,
                max_tokens=effective_max,
                tools=tools,
                tool_choice=active_tool_choice,
            )

            usage = response_json.get("usage", {})
            self.total_input_tokens += int(usage.get("prompt_tokens", 0) or 0)
            self.total_output_tokens += int(usage.get("completion_tokens", 0) or 0)

            elapsed = time.monotonic() - t0
            logger.info(
                "LLM round %d completed (%s, %.3fs)",
                round_idx + 1,
                self.name,
                elapsed,
            )

            assistant_msg = response_json.get("choices", [{}])[0].get("message", {})
            current_messages.append(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls", [])
            if not tool_calls:
                if round_idx == 0 and total_tool_calls == 0:
                    logger.info(
                        "Provider returned content without tool calls (%s) — tools not supported or not needed",
                        self.name,
                    )
                assistant_msg["_tool_calls_count"] = total_tool_calls
                return assistant_msg

            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                total_tool_calls += 1
                logger.info(
                    "Tool executed: %s(%s) round %d (%s)",
                    tool_name,
                    list(arguments.keys()),
                    round_idx + 1,
                    self.name,
                )
                result = tool_executor(tool_name, arguments)
                current_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(result),
                    }
                )

            # After first round of tool calls, relax to "auto" so the LLM
            # can produce the final content response.
            if active_tool_choice == "required":
                active_tool_choice = "auto"

        # max_tool_rounds exhausted — return last assistant message
        if current_messages:
            for msg in reversed(current_messages):
                if msg.get("role") == "assistant":
                    msg["_tool_calls_count"] = total_tool_calls
                    return msg
        return {"_tool_calls_count": total_tool_calls}

    async def call_llm_with_xml_tools(
        self,
        messages: list[dict[str, Any]],
        tool_executor: Any,
        *,
        max_tool_rounds: int = 5,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Multi-turn LLM call using XML-based tool-call simulation.

        Designed for providers (e.g. ICA/Granite) that do not support native
        function calling.  The system prompt must instruct the LLM to emit
        tool invocations as ``<tool_call>`` XML blocks.

        On each round the method:
        1. Sends messages **without** ``tools`` / ``tool_choice`` parameters.
        2. Parses any ``<tool_call>`` blocks from the text response.
        3. Executes each tool via *tool_executor*.
        4. Formats results as ``<tool_result>`` XML and appends as a user message.
        5. Loops until no tool calls are found or *max_tool_rounds* is reached.

        Returns the final assistant message dict (with ``<tool_call>`` blocks
        stripped from the content) plus an ``_tool_calls_count`` key.
        """
        if self.client is None:
            raise ExternalServiceException("No LLM client configured")

        effective_temp = temperature if temperature is not None else self.context.temperature
        effective_max = max_tokens if max_tokens is not None else self.context.max_tokens
        current_messages = list(messages)
        total_tool_calls = 0

        for round_idx in range(max_tool_rounds):
            self.call_count += 1
            call_number = self.call_count

            logger.info(
                "XML-tool LLM round %d started (%s, call #%d)",
                round_idx + 1,
                self.name,
                call_number,
            )
            t0 = time.monotonic()

            response_json = await self.client.chat_completion(
                messages=current_messages,
                temperature=effective_temp,
                max_tokens=effective_max,
            )

            usage = response_json.get("usage", {})
            self.total_input_tokens += int(usage.get("prompt_tokens", 0) or 0)
            self.total_output_tokens += int(usage.get("completion_tokens", 0) or 0)

            elapsed = time.monotonic() - t0
            logger.info(
                "XML-tool LLM round %d completed (%s, %.3fs)",
                round_idx + 1,
                self.name,
                elapsed,
            )

            text = self._extract_text_from_openai_style(response_json)
            parsed_calls = parse_xml_tool_calls(text)

            if not parsed_calls:
                # No tool calls — this is the final response.
                cleaned = strip_tool_calls(text)
                return {
                    "role": "assistant",
                    "content": cleaned,
                    "_tool_calls_count": total_tool_calls,
                }

            # Execute each parsed tool call
            tool_results: list[dict[str, Any]] = []
            for tc in parsed_calls:
                tool_name = tc["name"]
                arguments = tc["arguments"]
                total_tool_calls += 1
                logger.info(
                    "XML-tool executed: %s(%s) round %d (%s)",
                    tool_name,
                    list(arguments.keys()),
                    round_idx + 1,
                    self.name,
                )
                result = tool_executor(tool_name, arguments)
                tool_results.append({"name": tool_name, "output": result})

            # Append the assistant's raw response and the tool results
            current_messages.append({"role": "assistant", "content": text})
            current_messages.append({
                "role": "user",
                "content": format_tool_results(tool_results),
            })

        # max_tool_rounds exhausted — return last text with tool calls stripped
        return {
            "role": "assistant",
            "content": strip_tool_calls(text) if "text" in dir() else "",
            "_tool_calls_count": total_tool_calls,
        }

    @staticmethod
    def parse_json(text: str) -> dict[str, Any]:
        """Parse JSON from LLM output, stripping markdown code fences and surrounding prose."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        candidate = text.strip()
        # Strip leading/trailing code fences when the entire text is fenced
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            pass

        # Extract the first ```json...``` block from prose-wrapped responses
        fence_match = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

        # Last resort: find the first top-level { ... } in the text
        brace_match = re.search(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(1))
            except json.JSONDecodeError:
                pass

        logger.error("JSON parse failure: %s", text[:300])
        raise ValidationException(f"Failed to parse JSON from LLM response: {text[:200]}")
