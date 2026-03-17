"""Tests for controlnexus.graphs (state, analysis, remediation)."""

from __future__ import annotations

from typing import Any, get_type_hints

from controlnexus.graphs.state import AnalysisState, RemediationState
from controlnexus.graphs.analysis_graph import (
    build_analysis_graph,
    build_report_node,
    ingest_node,
)
from controlnexus.graphs.remediation_graph import (
    build_remediation_graph,
    planner_node,
    router_node,
    should_retry,
)


# -- State TypedDicts -----------------------------------------------------------


class TestAnalysisState:
    def test_has_expected_fields(self):
        hints = get_type_hints(AnalysisState, include_extras=True)
        assert "ingested_records" in hints
        assert "section_profiles" in hints
        assert "regulatory_gaps" in hints
        assert "balance_gaps" in hints
        assert "frequency_issues" in hints
        assert "evidence_issues" in hints
        assert "gap_report" in hints


class TestRemediationState:
    def test_has_expected_fields(self):
        hints = get_type_hints(RemediationState, include_extras=True)
        assert "run_id" in hints
        assert "gap_report" in hints
        assert "assignments" in hints
        assert "current_assignment" in hints
        assert "validation_passed" in hints
        assert "retry_count" in hints
        assert "generated_records" in hints
        assert "messages" in hints


# -- Analysis Graph Nodes -------------------------------------------------------


class TestAnalysisNodes:
    def test_ingest_node_empty_path(self):
        result = ingest_node({"excel_path": ""})
        assert result["ingested_records"] == []

    def test_build_report_node_no_gaps(self):
        state: dict[str, Any] = {
            "ingested_records": [{"control_id": "C1", "selected_level_2": "Reconciliation"}],
            "section_profiles": {},
            "regulatory_gaps": [],
            "balance_gaps": [],
            "frequency_issues": [],
            "evidence_issues": [],
        }
        result = build_report_node(state)
        report = result["gap_report"]
        assert report["summary"] == "No gaps identified"
        assert report["overall_score"] == 100.0

    def test_build_report_node_with_gaps(self):
        state: dict[str, Any] = {
            "ingested_records": [{"control_id": "C1", "selected_level_2": "Reconciliation"}] * 10,
            "section_profiles": {
                "4.0": {"registry": {"regulatory_frameworks": ["SOX", "OCC"]}}
            },
            "regulatory_gaps": [{"framework": "SOX"}],
            "balance_gaps": [],
            "frequency_issues": [{"control_id": "C1"}, {"control_id": "C2"}],
            "evidence_issues": [],
        }
        result = build_report_node(state)
        report = result["gap_report"]
        assert report["overall_score"] < 100.0
        assert "regulatory coverage gaps" in report["summary"]
        assert "frequency coherence issues" in report["summary"]


# -- Analysis Graph Compilation -------------------------------------------------


class TestAnalysisGraph:
    def test_compiles(self):
        graph = build_analysis_graph()
        assert graph is not None


# -- Remediation Graph Nodes ----------------------------------------------------


class TestRemediationNodes:
    def test_planner_node_with_gaps(self):
        result = planner_node({"gap_report": {
            "regulatory_gaps": [{"framework": "SOX"}],
            "balance_gaps": [],
            "frequency_issues": [],
            "evidence_issues": [],
        }})
        assert len(result["assignments"]) == 1
        assert result["assignments"][0]["gap_source"] == "regulatory"

    def test_planner_node_empty(self):
        result = planner_node({"gap_report": {}})
        assert result["assignments"] == []

    def test_router_node_picks_first(self):
        result = router_node({"assignments": [
            {"id": 1, "gap_source": "balance"},
            {"id": 2, "gap_source": "regulatory"},
        ]})
        assert result["current_gap_source"] == "balance"

    def test_router_node_empty(self):
        result = router_node({"assignments": []})
        assert result["current_assignment"] == {}

    def test_should_retry_passed(self):
        assert should_retry({"validation_passed": True}) == "enricher"

    def test_should_retry_failed_low_count(self):
        assert should_retry({"validation_passed": False, "retry_count": 1}) == "narrative_agent"

    def test_should_retry_failed_max_count(self):
        assert should_retry({"validation_passed": False, "retry_count": 3}) == "merge"


# -- Remediation Graph Compilation -----------------------------------------------


class TestRemediationGraph:
    def test_compiles(self):
        graph = build_remediation_graph()
        assert graph is not None
