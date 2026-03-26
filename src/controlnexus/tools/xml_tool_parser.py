"""XML tool-call parser for ICA/Granite tool-call simulation.

When ICA is configured with ``ICA_TOOL_CALLING=true``, the LLM is instructed to
emit tool invocations as XML tags inside its text response.  This module
provides helpers to:

1. Parse ``<tool_call>`` blocks from LLM text output.
2. Format tool results as ``<tool_result>`` blocks for re-injection.
3. Strip ``<tool_call>`` blocks from the final response text.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Regex to capture <tool_call>...</tool_call> blocks (non-greedy, DOTALL).
_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*"
    r"<name>\s*(?P<name>[^<]+?)\s*</name>\s*"
    r"<arguments>\s*(?P<arguments>.*?)\s*</arguments>\s*"
    r"</tool_call>",
    re.DOTALL,
)

# Broader pattern to strip any <tool_call>...</tool_call> block (even malformed inner content).
_TOOL_CALL_STRIP_RE = re.compile(r"<tool_call>.*?</tool_call>", re.DOTALL)


def parse_xml_tool_calls(text: str) -> list[dict[str, Any]]:
    """Extract tool calls from LLM text containing ``<tool_call>`` XML blocks.

    Returns a list of dicts with keys ``name`` (str) and ``arguments`` (dict).
    Malformed blocks (e.g. unparseable JSON in arguments) are logged and skipped.
    """
    results: list[dict[str, Any]] = []
    for match in _TOOL_CALL_RE.finditer(text):
        name = match.group("name").strip()
        raw_args = match.group("arguments").strip()
        try:
            arguments = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            logger.warning("Skipping tool_call '%s' — invalid JSON arguments: %s", name, raw_args[:200])
            continue
        results.append({"name": name, "arguments": arguments})
    return results


def format_tool_results(results: list[dict[str, Any]]) -> str:
    """Format executed tool results as ``<tool_result>`` XML for re-injection.

    Each entry in *results* must have ``name`` (str) and ``output`` (dict).
    """
    parts: list[str] = []
    for r in results:
        name = r["name"]
        output = json.dumps(r["output"], ensure_ascii=False)
        parts.append(f"<tool_result name=\"{name}\">\n{output}\n</tool_result>")
    return "\n\n".join(parts)


def strip_tool_calls(text: str) -> str:
    """Remove all ``<tool_call>`` blocks from *text*, returning clean content."""
    return _TOOL_CALL_STRIP_RE.sub("", text).strip()
