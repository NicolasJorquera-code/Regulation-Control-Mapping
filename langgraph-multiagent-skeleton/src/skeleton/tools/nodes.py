"""
LangGraph ToolNode — processes tool calls from agent messages.

Pattern: This node sits in the graph between an agent node and the
next processing step.  When the agent's LLM response contains
``tool_calls``, this node executes each one via the tool executor
and appends ``{role: "tool", ...}`` messages to the conversation.

In the skeleton's research graph, tool calling is handled inside
``BaseAgent.call_llm_with_tools()`` (the agent does its own tool loop),
so this standalone ToolNode is provided as an alternative integration
pattern for graphs that separate "agent decision" and "tool execution"
into distinct nodes.

# CUSTOMIZE: Wire this into your graph if you prefer the
# agent-node → tool-node → agent-node pattern over the self-contained
# tool loop inside BaseAgent.
"""

from __future__ import annotations

import json
from typing import Any, Callable


def make_tool_node(
    tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Return a LangGraph node function that executes pending tool calls.

    The node reads ``state["messages"]``, finds the last assistant message
    with ``tool_calls``, executes each, and returns new tool-result messages.
    """

    def tool_node(state: dict[str, Any]) -> dict[str, Any]:
        messages: list[dict[str, Any]] = state.get("messages", [])
        if not messages:
            return {"messages": []}

        last = messages[-1]
        tool_calls = last.get("tool_calls", [])
        if not tool_calls:
            return {"messages": []}

        new_messages: list[dict[str, Any]] = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            result = tool_executor(name, args)
            new_messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": json.dumps(result),
            })

        return {"messages": new_messages}

    return tool_node
