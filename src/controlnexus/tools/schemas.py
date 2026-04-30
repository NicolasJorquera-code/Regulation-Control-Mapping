"""OpenAI function-calling JSON Schema definitions for ControlNexus tools.

These schemas define the 5 tools that agents can invoke via the
LangGraph ToolNode integration.
"""

from __future__ import annotations

from typing import Any

TAXONOMY_VALIDATOR_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "taxonomy_validator",
        "description": "Validate a control type pair (level_1, level_2) against the taxonomy. Returns whether the combination is valid and suggests the correct level_1 if not.",
        "parameters": {
            "type": "object",
            "properties": {
                "level_1": {
                    "type": "string",
                    "description": "Level 1 placement (Preventive, Detective, Contingency Planning)",
                },
                "level_2": {
                    "type": "string",
                    "description": "Level 2 control type (e.g., Reconciliation, Authorization)",
                },
            },
            "required": ["level_1", "level_2"],
        },
    },
}

REGULATORY_LOOKUP_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "regulatory_lookup",
        "description": "Look up regulatory requirements for a framework in a specific APQC section. Returns required themes and applicable control types.",
        "parameters": {
            "type": "object",
            "properties": {
                "framework": {"type": "string", "description": "Regulatory framework name (e.g., 'SOX Compliance')"},
                "section_id": {"type": "string", "description": "APQC section ID (e.g., '4.0')"},
            },
            "required": ["framework", "section_id"],
        },
    },
}

HIERARCHY_SEARCH_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "hierarchy_search",
        "description": "Search for APQC leaf nodes matching a keyword within a section.",
        "parameters": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string", "description": "APQC section ID (e.g., '4.0')"},
                "keyword": {"type": "string", "description": "Search keyword"},
            },
            "required": ["section_id", "keyword"],
        },
    },
}

FREQUENCY_LOOKUP_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "frequency_lookup",
        "description": "Get the expected frequency for a control type given a trigger/timing context.",
        "parameters": {
            "type": "object",
            "properties": {
                "control_type": {"type": "string", "description": "Control type (e.g., 'Reconciliation')"},
                "trigger": {"type": "string", "description": "Timing or trigger text"},
            },
            "required": ["control_type", "trigger"],
        },
    },
}

MEMORY_RETRIEVAL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "memory_retrieval",
        "description": "Retrieve similar existing controls from the vector memory store.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_text": {"type": "string", "description": "Control description to find similar controls for"},
                "section_id": {"type": "string", "description": "Optional section filter (e.g., '4.0')"},
                "n": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
            },
            "required": ["query_text"],
        },
    },
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    TAXONOMY_VALIDATOR_SCHEMA,
    REGULATORY_LOOKUP_SCHEMA,
    HIERARCHY_SEARCH_SCHEMA,
    FREQUENCY_LOOKUP_SCHEMA,
    MEMORY_RETRIEVAL_SCHEMA,
]


# ── Risk catalog tool ────────────────────────────────────────────────────────

RISK_CATALOG_LOOKUP_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "risk_catalog_lookup",
        "description": "Look up a risk catalog entry by ID. Returns the risk name, category, severity, and description.",
        "parameters": {
            "type": "object",
            "properties": {
                "risk_id": {
                    "type": "string",
                    "description": "The risk catalog entry ID (e.g., 'RISK-001')",
                },
            },
            "required": ["risk_id"],
        },
    },
}


# ── Lookup tools for slim-prompt / tool-calling mode ──────────────────────────

PLACEMENT_LOOKUP_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "placement_lookup",
        "description": "Look up allowed placement categories and their definitions for a control type.",
        "parameters": {
            "type": "object",
            "properties": {
                "control_type": {
                    "type": "string",
                    "description": "Control type name (e.g., 'Reconciliation', 'Authorization')",
                },
            },
            "required": ["control_type"],
        },
    },
}

METHOD_LOOKUP_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "method_lookup",
        "description": "Look up allowed control methods and their definitions.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

EVIDENCE_RULES_LOOKUP_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "evidence_rules_lookup",
        "description": "Look up evidence quality criteria for a control type.",
        "parameters": {
            "type": "object",
            "properties": {
                "control_type": {
                    "type": "string",
                    "description": "Control type name (e.g., 'Reconciliation', 'Authorization')",
                },
            },
            "required": ["control_type"],
        },
    },
}

EXEMPLAR_LOOKUP_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "exemplar_lookup",
        "description": "Retrieve exemplar narratives for a given APQC section.",
        "parameters": {
            "type": "object",
            "properties": {
                "section_id": {
                    "type": "string",
                    "description": "APQC section ID (e.g., '4.0', '1.0')",
                },
            },
            "required": ["section_id"],
        },
    },
}

SLIM_TOOL_SCHEMAS: list[dict[str, Any]] = [
    PLACEMENT_LOOKUP_SCHEMA,
    METHOD_LOOKUP_SCHEMA,
    EVIDENCE_RULES_LOOKUP_SCHEMA,
    EXEMPLAR_LOOKUP_SCHEMA,
]
