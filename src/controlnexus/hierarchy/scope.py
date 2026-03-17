"""Scope selection and hierarchy analysis utilities."""

from __future__ import annotations

from collections import Counter
from typing import Any

from controlnexus.core.state import HierarchyNode


def select_scope(
    nodes: list[HierarchyNode],
    top_sections: list[str],
    subsection: str | None = None,
) -> list[HierarchyNode]:
    """Filter hierarchy nodes by top-level section and optional subsection.

    Args:
        nodes: Full list of hierarchy nodes.
        top_sections: Section IDs to include (e.g., ["4", "9"]).
        subsection: Optional hierarchy prefix to narrow scope (e.g., "4.1.1").

    Returns:
        Filtered list of nodes in the specified scope.
    """
    section_set = set(top_sections)
    filtered = [n for n in nodes if n.top_section in section_set]

    if subsection:
        prefix = subsection if subsection.endswith(".") else subsection + "."
        filtered = [
            n for n in filtered
            if n.hierarchy_id == subsection or n.hierarchy_id.startswith(prefix)
        ]

    return filtered


def build_section_breakdown(nodes: list[HierarchyNode]) -> list[dict[str, Any]]:
    """Summarize node/leaf counts per top-level section.

    Args:
        nodes: List of hierarchy nodes (typically scope-filtered).

    Returns:
        List of dicts: [{"section": "4", "nodes": 29, "leaves": 21}, ...]
    """
    node_counts: Counter[str] = Counter()
    leaf_counts: Counter[str] = Counter()

    for node in nodes:
        node_counts[node.top_section] += 1
        if node.is_leaf:
            leaf_counts[node.top_section] += 1

    sections = sorted(node_counts.keys(), key=lambda s: int(s) if s.isdigit() else float("inf"))
    return [
        {
            "section": s,
            "nodes": node_counts[s],
            "leaves": leaf_counts[s],
        }
        for s in sections
    ]
