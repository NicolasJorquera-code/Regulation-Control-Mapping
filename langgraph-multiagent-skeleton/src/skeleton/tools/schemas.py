"""
Tool JSON schemas — OpenAI function-calling format.

Pattern: Define tool schemas as plain dicts in one place so they can
be passed to ``BaseAgent.call_llm_with_tools()`` and also used in tests.
Each schema follows the OpenAI ``tools`` array format:
``{"type": "function", "function": {"name": ..., "parameters": ...}}``.

# CUSTOMIZE: Replace these with your domain's tools.
"""

WEB_SEARCH_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for information on a topic. "
            "Returns a list of relevant snippets with source URLs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
            },
            "required": ["query"],
        },
    },
}

NOTE_STORE_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "note_store",
        "description": (
            "Store a key-value note for later retrieval. "
            "Use this to save intermediate observations during research."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "A short label for the note.",
                },
                "value": {
                    "type": "string",
                    "description": "The note content.",
                },
            },
            "required": ["key", "value"],
        },
    },
}

# Convenience list — pass this directly to ``call_llm_with_tools``.
ALL_TOOL_SCHEMAS: list[dict] = [WEB_SEARCH_SCHEMA, NOTE_STORE_SCHEMA]
