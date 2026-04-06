"""
Tests for Graph 1 — classify graph compilation and deterministic e2e.
"""

from __future__ import annotations

import pytest

from regrisk.graphs.classify_graph import build_classify_graph, reset_caches
from regrisk.graphs.classify_state import ClassifyState


class TestClassifyGraphCompilation:
    def setup_method(self):
        reset_caches()

    def teardown_method(self):
        reset_caches()

    def test_graph_compiles(self):
        graph = build_classify_graph()
        assert graph is not None

    def test_graph_has_correct_nodes(self):
        graph = build_classify_graph()
        # The compiled graph should have nodes
        node_names = set(graph.get_graph().nodes.keys())
        expected = {"init", "ingest", "classify_group", "end_classify"}
        # LangGraph adds __start__ and __end__ nodes
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


class TestClassifyGraphDeterministic:
    """End-to-end deterministic test using sample data fixtures."""

    def setup_method(self):
        reset_caches()

    def teardown_method(self):
        reset_caches()

    def test_deterministic_classify_with_fixtures(
        self, sample_obligations, sample_apqc_nodes, sample_controls, sample_config
    ):
        """Test classification with pre-built state (skip ingest)."""
        from regrisk.ingest.regulation_parser import group_obligations

        groups = group_obligations(sample_obligations)
        groups_dicts = [g.model_dump() for g in groups]

        # Build a minimal state simulating post-ingest
        state: dict = {
            "regulation_name": "Enhanced Prudential Standards (Regulation YY)",
            "total_obligations": len(sample_obligations),
            "obligation_groups": groups_dicts,
            "apqc_nodes": [n.model_dump() for n in sample_apqc_nodes],
            "controls": [c.model_dump() for c in sample_controls],
            "pipeline_config": sample_config.model_dump(),
            "risk_taxonomy": {},
            "llm_enabled": False,
            "classify_idx": 0,
            "classified_obligations": [],
            "errors": [],
        }

        # Run just the classify_group_node directly
        from regrisk.graphs.classify_graph import classify_group_node

        result = classify_group_node(state)
        assert "classified_obligations" in result
        assert len(result["classified_obligations"]) > 0

        # All classifications should have required fields
        for c in result["classified_obligations"]:
            assert c.get("citation"), "Citation required"
            assert c.get("obligation_category") in {
                "Attestation", "Documentation", "Controls", "General Awareness", "Not Assigned"
            }
            assert c.get("criticality_tier") in {"High", "Medium", "Low"}
