"""LangGraph state definitions for analysis and remediation graphs.

Uses TypedDict with Annotated[list, add] reducers so parallel nodes
can append to list fields without overwriting each other.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict


def add(left: list, right: list) -> list:
    """Reducer that appends right list to left list."""
    return left + right


class AnalysisState(TypedDict, total=False):
    """State for the analysis graph.

    Flow: ingest → load_context → [4 scanners in parallel] → merge → build_report
    """

    # Input
    excel_path: str
    config_dir: str

    # After ingest
    ingested_records: list[dict[str, Any]]

    # After load_context
    section_profiles: dict[str, Any]

    # Scanner outputs (use add reducer for parallel writes)
    regulatory_gaps: Annotated[list[dict[str, Any]], add]
    balance_gaps: Annotated[list[dict[str, Any]], add]
    frequency_issues: Annotated[list[dict[str, Any]], add]
    evidence_issues: Annotated[list[dict[str, Any]], add]

    # Final output
    gap_report: dict[str, Any]


class RemediationState(TypedDict, total=False):
    """State for the remediation graph.

    Flow: planner → router → [agent pipeline] → validator → enricher → merge → export
    """

    # Run metadata
    run_id: str

    # Input
    gap_report: dict[str, Any]
    assignments: list[dict[str, Any]]

    # Context
    section_profiles: dict[str, Any]

    # Current processing
    current_assignment: dict[str, Any]
    current_gap_source: str  # "regulatory" | "balance" | "frequency" | "evidence"
    current_spec: dict[str, Any]
    current_narrative: dict[str, Any]
    validation_passed: bool
    retry_count: int
    current_enriched: dict[str, Any]
    quality_gate_passed: bool

    # Accumulated outputs (use add reducer for append)
    generated_records: Annotated[list[dict[str, Any]], add]

    # LLM messages for tool calling
    messages: Annotated[list[dict[str, Any]], add]
