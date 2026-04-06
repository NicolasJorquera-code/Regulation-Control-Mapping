"""
APQC Process Classification Framework loader.

Deterministic (no LLM). Pure Python + pandas.
"""

from __future__ import annotations

import pandas as pd

from regrisk.core.models import APQCNode
from regrisk.exceptions import IngestError


def load_apqc_hierarchy(path: str) -> list[APQCNode]:
    """Parse 'Combined' sheet → APQCNode objects.

    Computes depth from hierarchy_id dot-count and parent_id
    by stripping the last segment.
    """
    try:
        df = pd.read_excel(path, sheet_name="Combined", engine="openpyxl")
    except Exception as exc:
        raise IngestError(f"Failed to read APQC Excel at {path}: {exc}") from exc

    required = ["PCF ID", "Hierarchy ID", "Name"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise IngestError(f"Missing columns in APQC Excel: {missing}")

    nodes: list[APQCNode] = []
    for _, row in df.iterrows():
        hierarchy_id = str(row["Hierarchy ID"]).strip()
        name = str(row["Name"]).strip() if pd.notna(row["Name"]) else ""
        pcf_id = int(row["PCF ID"]) if pd.notna(row["PCF ID"]) else 0

        # Compute depth: "11.1.1" → 3 parts → depth 3
        parts = hierarchy_id.split(".")
        depth = len(parts)

        # Compute parent_id: "11.1.1" → "11.1"; "11.0" → ""
        if depth <= 1:
            parent_id = ""
        else:
            parent_id = ".".join(parts[:-1])

        nodes.append(APQCNode(
            pcf_id=pcf_id,
            hierarchy_id=hierarchy_id,
            name=name,
            depth=depth,
            parent_id=parent_id,
        ))

    return nodes


def build_apqc_summary(nodes: list[APQCNode], max_depth: int = 3) -> str:
    """Build indented text summary for LLM prompts.

    Only includes nodes up to max_depth. Returns a multi-line string
    with indentation showing the hierarchy.
    """
    lines: list[str] = []
    for node in nodes:
        if node.depth > max_depth:
            continue
        indent = "  " * (node.depth - 1)
        lines.append(f"{indent}{node.hierarchy_id} {node.name}")
    return "\n".join(lines)


def get_apqc_subtree(nodes: list[APQCNode], root_id: str) -> list[APQCNode]:
    """Get all descendants of a given hierarchy_id.

    A node is a descendant if its hierarchy_id starts with root_id + '.'
    or equals root_id exactly.
    """
    prefix = root_id + "."
    return [n for n in nodes if n.hierarchy_id == root_id or n.hierarchy_id.startswith(prefix)]
