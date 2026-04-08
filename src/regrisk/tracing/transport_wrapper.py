"""
Tracing wrapper for AsyncTransportClient — captures every LLM call.

This module intercepts the ``chat_completion`` method to record:

* Full system and user prompts
* The complete response text
* Model name, temperature, max_tokens
* Token counts (prompt, completion, total) from the API response
* Latency in milliseconds
* Any errors

The wrapper reads the *current trace context* (node name, agent name) from a
thread-local variable set by the ``trace_node`` decorator, so it always knows
which graph node / agent triggered the call — with **zero changes** to
``BaseAgent`` or existing agent code.

Usage (automatic — wired up by the graph builders)::

    from regrisk.tracing import TracingTransportClient, TraceDB

    db = TraceDB("data/traces.db")
    wrapper = TracingTransportClient(original_client, db, run_id="abc-123")
    # wrapper is API-compatible with AsyncTransportClient
"""

from __future__ import annotations

import time
from typing import Any

from regrisk.core.transport import AsyncTransportClient
from regrisk.tracing.db import TraceDB
from regrisk.tracing.decorators import get_current_trace_context


class TracingTransportClient(AsyncTransportClient):
    """Drop-in replacement for ``AsyncTransportClient`` that logs every call.

    Delegates all real work to an inner client instance, adding tracing
    around the actual HTTP call.
    """

    def __init__(
        self,
        inner: AsyncTransportClient,
        db: TraceDB,
        run_id: str,
    ) -> None:
        # Copy essential attributes from the inner client so the rest of the
        # codebase sees the same model, provider, etc.
        self.api_key = inner.api_key
        self.base_url = inner.base_url
        self.model = inner.model
        self.provider = inner.provider
        self.ica_tool_calling = inner.ica_tool_calling
        self.timeout_seconds = inner.timeout_seconds
        self.max_retries = inner.max_retries

        # Share the inner client's HTTP state (connection pool, resolved URL)
        self._client = inner._client
        self._resolved_url = inner._resolved_url

        self._inner = inner
        self._db = db
        self._run_id = run_id

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
    ) -> dict[str, Any]:
        # Capture context from the node decorator (if active)
        ctx = get_current_trace_context()
        node_name = ctx.get("node_name", "")
        agent_name = ctx.get("agent_name", "")

        # Extract prompts from messages
        system_prompt = ""
        user_prompt = ""
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_prompt = content
            elif role == "user":
                user_prompt = content

        start = time.perf_counter()
        error_text: str | None = None
        response_text = ""
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        total_tokens: int | None = None

        try:
            result = await self._inner.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
            )

            # Extract response text
            choices = result.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                response_text = msg.get("content", "") or ""

            # Extract token usage
            usage = result.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")

            return result

        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            raise

        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._db.insert_llm_call(
                self._run_id,
                node_name=node_name,
                agent_name=agent_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_text=response_text,
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=elapsed_ms,
                error=error_text,
            )

    # Delegate lifecycle methods to inner client
    async def close(self) -> None:
        await self._inner.close()

    async def _get_client(self):
        return await self._inner._get_client()
