"""LangGraph ToolNode wrapper for ControlNexus tools.

Maps tool names to implementation functions for use as a LangGraph node.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from controlnexus.tools.implementations import (
    frequency_lookup,
    hierarchy_search,
    memory_retrieval,
    regulatory_lookup,
    taxonomy_validator,
)

logger = logging.getLogger(__name__)

# Tool name → function mapping
TOOL_MAP: dict[str, Any] = {
    "taxonomy_validator": taxonomy_validator,
    "regulatory_lookup": regulatory_lookup,
    "hierarchy_search": hierarchy_search,
    "frequency_lookup": frequency_lookup,
    "memory_retrieval": memory_retrieval,
}


def execute_tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a single tool call by name with given arguments.

    Returns the tool's result dict, or an error dict if the tool is unknown.
    """
    func = TOOL_MAP.get(tool_name)
    if func is None:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return func(**arguments)
    except Exception as exc:
        logger.error("Tool %s failed: %s", tool_name, exc)
        return {"error": str(exc)}


def tool_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node that processes tool calls from agent messages.

    Reads the last message in state["messages"]. If it contains
    tool_calls, executes each and appends tool response messages.

    Compatible with LangGraph's message-passing pattern.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}

    last_msg = messages[-1]
    tool_calls = last_msg.get("tool_calls", [])
    if not tool_calls:
        return {"messages": []}

    new_messages: list[dict[str, Any]] = []
    for call in tool_calls:
        tool_name = call.get("function", {}).get("name", "")
        raw_args = call.get("function", {}).get("arguments", "{}")

        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
        else:
            args = raw_args

        result = execute_tool_call(tool_name, args)
        new_messages.append({
            "role": "tool",
            "tool_call_id": call.get("id", ""),
            "content": json.dumps(result),
        })

    return {"messages": new_messages}
