"""
Tests for Graph 2 — assess graph compilation and deterministic e2e.
"""

from __future__ import annotations

import pytest

from regrisk.graphs.assess_graph import build_assess_graph, reset_caches
from regrisk.graphs.assess_state import AssessState


class TestAssessGraphCompilation:
    def setup_method(self):
        reset_caches()

    def teardown_method(self):
        reset_caches()

    def test_graph_compiles(self):
        graph = build_assess_graph()
        assert graph is not None

    def test_graph_has_correct_nodes(self):
        graph = build_assess_graph()
        node_names = set(graph.get_graph().nodes.keys())
        expected = {
            "map_group", "prepare_assessment", "assess_coverage",
            "prepare_risks", "extract_and_score", "finalize",
        }
        assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


class TestAssessGraphDeterministic:
    """Deterministic e2e tests for the assess pipeline."""

    def setup_method(self):
        reset_caches()

    def teardown_method(self):
        reset_caches()

    def test_deterministic_map_group(
        self, sample_obligations, sample_apqc_nodes, sample_controls, sample_config
    ):
        """Test mapping node deterministically."""
        from regrisk.graphs.assess_graph import map_group_node

        # Build approved obligations
        approved = []
        for ob in sample_obligations:
            approved.append({
                "citation": ob.citation,
                "abstract": ob.abstract,
                "section_citation": ob.citation_level_3,
                "section_title": ob.title_level_3,
                "subpart": ob.citation_level_2,
                "obligation_category": "Controls",
                "relationship_type": "Constrains Execution",
                "criticality_tier": "High",
            })

        mappable_groups = [{
            "section_citation": "12 CFR 252.22",
            "section_title": "Risk committee requirements",
            "subpart": "Subpart C",
            "obligations": approved,
        }]

        state: dict = {
            "regulation_name": "Regulation YY",
            "pipeline_config": sample_config.model_dump(),
            "risk_taxonomy": {},
            "llm_enabled": False,
            "apqc_nodes": [n.model_dump() for n in sample_apqc_nodes],
            "controls": [c.model_dump() for c in sample_controls],
            "approved_obligations": approved,
            "mappable_groups": mappable_groups,
            "map_idx": 0,
            "obligation_mappings": [],
            "errors": [],
        }

        result = map_group_node(state)
        assert "obligation_mappings" in result
        assert len(result["obligation_mappings"]) > 0

        for m in result["obligation_mappings"]:
            assert m.get("citation")
            assert m.get("apqc_hierarchy_id")
            assert "confidence" in m

    def test_structural_matching(self, sample_controls):
        """Test that find_controls_for_apqc works with the control index."""
        from regrisk.ingest.control_loader import build_control_index, find_controls_for_apqc

        index = build_control_index(sample_controls)

        # Should find controls at 11.1.1
        results = find_controls_for_apqc(index, "11.1.1")
        assert len(results) >= 1
        assert any(c.hierarchy_id.startswith("11.1.1") for c in results)

        # Should find nothing at 99.0
        results = find_controls_for_apqc(index, "99.0")
        assert len(results) == 0
