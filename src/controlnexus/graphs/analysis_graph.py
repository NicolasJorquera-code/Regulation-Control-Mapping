"""LangGraph analysis graph: ingest → scan → report.

Implements the analysis pipeline as a StateGraph with fan-out/fan-in
for the 4 scanners.

Flow: START → ingest → load_context → [reg_scan, bal_scan, freq_scan, evid_scan] → merge → build_report → END
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from controlnexus.analysis.ingest import ingest_excel
from controlnexus.analysis.pipeline import (
    WEIGHT_BALANCE,
    WEIGHT_EVIDENCE,
    WEIGHT_FREQUENCY,
    WEIGHT_REGULATORY,
)
from controlnexus.analysis.scanners import (
    ecosystem_balance_analysis,
    evidence_sufficiency_scan,
    frequency_coherence_scan,
    regulatory_coverage_scan,
)
from controlnexus.core.config import load_all_section_profiles
from controlnexus.core.models import SectionProfile
from controlnexus.core.state import FinalControlRecord
from controlnexus.graphs.state import AnalysisState

logger = logging.getLogger(__name__)


# -- Node functions ------------------------------------------------------------


def ingest_node(state: AnalysisState) -> dict[str, Any]:
    """Parse Excel file into control records."""
    path = state.get("excel_path", "")
    if not path:
        return {"ingested_records": []}

    records = ingest_excel(Path(path))
    return {"ingested_records": [r.model_dump() for r in records]}


def load_context_node(state: AnalysisState) -> dict[str, Any]:
    """Load all section profiles from config directory."""
    config_dir = state.get("config_dir", "config")
    profiles = load_all_section_profiles(Path(config_dir))
    # Serialize profiles for state
    return {
        "section_profiles": {k: v.model_dump() for k, v in profiles.items()},
    }


def _records_and_profiles(state: AnalysisState) -> tuple[list[FinalControlRecord], dict[str, SectionProfile]]:
    """Reconstruct typed objects from state dicts."""
    records = [FinalControlRecord(**r) for r in state.get("ingested_records", [])]
    profiles = {k: SectionProfile(**v) for k, v in state.get("section_profiles", {}).items()}
    return records, profiles


def reg_scan_node(state: AnalysisState) -> dict[str, Any]:
    """Run regulatory coverage scan."""
    records, profiles = _records_and_profiles(state)
    gaps = regulatory_coverage_scan(records, profiles)
    return {"regulatory_gaps": [g.model_dump() for g in gaps]}


def bal_scan_node(state: AnalysisState) -> dict[str, Any]:
    """Run ecosystem balance analysis."""
    records, profiles = _records_and_profiles(state)
    gaps = ecosystem_balance_analysis(records, profiles)
    return {"balance_gaps": [g.model_dump() for g in gaps]}


def freq_scan_node(state: AnalysisState) -> dict[str, Any]:
    """Run frequency coherence scan."""
    records, _ = _records_and_profiles(state)
    issues = frequency_coherence_scan(records)
    return {"frequency_issues": [i.model_dump() for i in issues]}


def evid_scan_node(state: AnalysisState) -> dict[str, Any]:
    """Run evidence sufficiency scan."""
    records, _ = _records_and_profiles(state)
    issues = evidence_sufficiency_scan(records)
    return {"evidence_issues": [i.model_dump() for i in issues]}


def build_report_node(state: AnalysisState) -> dict[str, Any]:
    """Build the final GapReport from scanner outputs."""
    reg_gaps = state.get("regulatory_gaps", [])
    bal_gaps = state.get("balance_gaps", [])
    freq_issues = state.get("frequency_issues", [])
    evid_issues = state.get("evidence_issues", [])
    records = state.get("ingested_records", [])

    total_records = len(records)
    profiles_data = state.get("section_profiles", {})

    # Score each dimension
    total_frameworks = sum(len(p.get("registry", {}).get("regulatory_frameworks", [])) for p in profiles_data.values())
    reg_score = ((total_frameworks - len(reg_gaps)) / total_frameworks * 100) if total_frameworks else 100.0

    total_types = len({r.get("selected_level_2") or r.get("control_type", "") for r in records})
    bal_score = (max(0, total_types - len(bal_gaps)) / total_types * 100) if total_types else 100.0

    freq_score = ((total_records - len(freq_issues)) / total_records * 100) if total_records else 100.0
    evid_score = ((total_records - len(evid_issues)) / total_records * 100) if total_records else 100.0

    overall = (
        WEIGHT_REGULATORY * reg_score
        + WEIGHT_BALANCE * bal_score
        + WEIGHT_FREQUENCY * freq_score
        + WEIGHT_EVIDENCE * evid_score
    )

    summary_parts = []
    if reg_gaps:
        summary_parts.append(f"{len(reg_gaps)} regulatory coverage gaps")
    if bal_gaps:
        summary_parts.append(f"{len(bal_gaps)} ecosystem balance issues")
    if freq_issues:
        summary_parts.append(f"{len(freq_issues)} frequency coherence issues")
    if evid_issues:
        summary_parts.append(f"{len(evid_issues)} evidence sufficiency issues")
    summary = "; ".join(summary_parts) if summary_parts else "No gaps identified"

    return {
        "gap_report": {
            "regulatory_gaps": reg_gaps,
            "balance_gaps": bal_gaps,
            "frequency_issues": freq_issues,
            "evidence_issues": evid_issues,
            "historical_regressions": [],
            "overall_score": round(overall, 1),
            "summary": summary,
        }
    }


# -- Graph builder -------------------------------------------------------------


def build_analysis_graph() -> StateGraph:
    """Build and return the compiled analysis StateGraph.

    Topology:
        START → ingest → load_context → [reg_scan, bal_scan, freq_scan, evid_scan] → build_report → END
    """
    graph = StateGraph(AnalysisState)

    # Add nodes
    graph.add_node("ingest", ingest_node)
    graph.add_node("load_context", load_context_node)
    graph.add_node("reg_scan", reg_scan_node)
    graph.add_node("bal_scan", bal_scan_node)
    graph.add_node("freq_scan", freq_scan_node)
    graph.add_node("evid_scan", evid_scan_node)
    graph.add_node("build_report", build_report_node)

    # Sequential: START → ingest → load_context
    graph.add_edge(START, "ingest")
    graph.add_edge("ingest", "load_context")

    # Fan-out: load_context → all 4 scanners
    graph.add_edge("load_context", "reg_scan")
    graph.add_edge("load_context", "bal_scan")
    graph.add_edge("load_context", "freq_scan")
    graph.add_edge("load_context", "evid_scan")

    # Fan-in: all 4 scanners → build_report
    graph.add_edge("reg_scan", "build_report")
    graph.add_edge("bal_scan", "build_report")
    graph.add_edge("freq_scan", "build_report")
    graph.add_edge("evid_scan", "build_report")

    # build_report → END
    graph.add_edge("build_report", END)

    return graph.compile()
