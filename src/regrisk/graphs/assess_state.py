"""
AssessState — TypedDict for Graph 2 (Map + Assess + Score + Finalize).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AssessState(TypedDict, total=False):
    # Carried from Graph 1 (loaded from session state)
    regulation_name: str
    pipeline_config: dict[str, Any]
    risk_taxonomy: dict[str, Any]
    llm_enabled: bool
    apqc_nodes: list[dict[str, Any]]
    controls: list[dict[str, Any]]

    # Approved classifications (from human review)
    approved_obligations: list[dict[str, Any]]

    # Groups that need APQC mapping
    mappable_groups: list[dict[str, Any]]

    # Mapping loop
    map_idx: int
    obligation_mappings: Annotated[list[dict[str, Any]], operator.add]

    # Coverage assessment loop
    assess_items: list[dict[str, Any]]
    assess_idx: int
    coverage_assessments: Annotated[list[dict[str, Any]], operator.add]

    # Risk extraction loop
    gap_obligations: list[dict[str, Any]]
    risk_idx: int
    scored_risks: Annotated[list[dict[str, Any]], operator.add]

    # Final
    risk_register: dict[str, Any]
    gap_report: dict[str, Any]
    compliance_matrix: dict[str, Any]

    # Errors
    errors: Annotated[list[str], operator.add]
