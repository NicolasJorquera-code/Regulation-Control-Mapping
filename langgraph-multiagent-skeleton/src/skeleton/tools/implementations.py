"""
Tool implementations and executor factory.

Pattern: ``build_tool_executor(config)`` returns a **closure** that
dispatches by tool name.  The closure captures ``config`` so agents
never manage configuration state — they just call
``executor("web_search", {"query": "..."})``.

This makes testing trivial: inject a mock executor that returns canned
results, and the agent under test never knows the difference.

# CUSTOMIZE: Replace tool bodies with real integrations (search APIs,
# databases, external services).  Keep the executor-closure pattern.
"""

from __future__ import annotations

from typing import Any, Callable

from skeleton.core.config import DomainConfig


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------

def _web_search(query: str, config: DomainConfig) -> dict[str, Any]:
    """Search the web for *query*.

    # CUSTOMIZE: Replace with a real search API (Tavily, SerpAPI, Brave, etc.).
    # The mock returns deterministic placeholder results so the skeleton
    # is runnable without any external API keys.
    """
    return {
        "results": [
            {
                "title": f"Result 1 for: {query}",
                "snippet": (
                    f"This is a placeholder snippet about '{query}'. "
                    "In production, replace this tool with a real search API."
                ),
                "url": f"https://example.com/search?q={query.replace(' ', '+')}",
            },
            {
                "title": f"Result 2 for: {query}",
                "snippet": (
                    f"Another perspective on '{query}'. "
                    "The skeleton uses mock tools so it runs without external deps."
                ),
                "url": f"https://example.org/article/{query.replace(' ', '-')}",
            },
        ]
    }


# In-memory note storage (reset per executor instance)
_NOTE_STORE: dict[str, str] = {}


def _note_store(key: str, value: str, config: DomainConfig) -> dict[str, Any]:
    """Store a key-value note in memory.

    # CUSTOMIZE: Replace with a persistent store if needed (Redis, DB, vector store).
    """
    _NOTE_STORE[key] = value
    return {"stored": True, "key": key}


# ---------------------------------------------------------------------------
# Tool dispatch table
# ---------------------------------------------------------------------------

# Maps tool name → implementation function.
# Every function has the signature (arg1, arg2, ..., config) → dict.
_TOOL_TABLE: dict[str, Callable[..., dict[str, Any]]] = {
    "web_search": lambda config, **kw: _web_search(query=kw.get("query", ""), config=config),
    "note_store": lambda config, **kw: _note_store(key=kw.get("key", ""), value=kw.get("value", ""), config=config),
}


# ---------------------------------------------------------------------------
# Executor factory
# ---------------------------------------------------------------------------

def build_tool_executor(
    config: DomainConfig,
) -> Callable[[str, dict[str, Any]], dict[str, Any]]:
    """Return a tool-executor closure that captures *config*.

    Usage::

        executor = build_tool_executor(my_config)
        result = executor("web_search", {"query": "LangGraph patterns"})

    Unknown tool names return an error dict (never raise).
    """

    def executor(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = _TOOL_TABLE.get(tool_name)
        if fn is None:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return fn(config, **args)
        except Exception as exc:
            return {"error": str(exc)}

    return executor
