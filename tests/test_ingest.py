"""
Tests for the ingest layer — regulation parser, APQC loader, control loader.

Uses actual data files from the data/ directory when available.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from regrisk.core.models import APQCNode, ControlRecord, Obligation, ObligationGroup
from regrisk.ingest.apqc_loader import build_apqc_summary, get_apqc_subtree, load_apqc_hierarchy
from regrisk.ingest.control_loader import (
    build_control_index,
    discover_control_files,
    find_controls_for_apqc,
    load_and_merge_controls,
)
from regrisk.ingest.regulation_parser import group_obligations, parse_regulation_excel


_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_REG_PATH = _DATA_DIR / "regulations yy.xlsx"
_APQC_PATH = _DATA_DIR / "APQC_Template.xlsx"
_CONTROLS_DIR = _DATA_DIR / "Control Dataset"


# ---------------------------------------------------------------------------
# Regulation parser
# ---------------------------------------------------------------------------

class TestRegulationParser:
    @pytest.mark.skipif(not _REG_PATH.exists(), reason="Regulation Excel not found")
    def test_parse_regulation_excel(self):
        name, obligations = parse_regulation_excel(str(_REG_PATH))
        assert name, "Regulation name should not be empty"
        assert len(obligations) > 600, f"Expected 690+ obligations, got {len(obligations)}"
        assert all(isinstance(ob, Obligation) for ob in obligations)

    @pytest.mark.skipif(not _REG_PATH.exists(), reason="Regulation Excel not found")
    def test_parse_returns_valid_citations(self):
        _, obligations = parse_regulation_excel(str(_REG_PATH))
        for ob in obligations[:10]:
            assert ob.citation, "Citation should not be empty"
            assert ob.status in ("In Force", "Pending", ""), f"Unexpected status: {ob.status}"

    @pytest.mark.skipif(not _REG_PATH.exists(), reason="Regulation Excel not found")
    def test_group_obligations(self):
        _, obligations = parse_regulation_excel(str(_REG_PATH))
        groups = group_obligations(obligations)
        assert len(groups) > 50, f"Expected 80+ groups, got {len(groups)}"
        assert all(isinstance(g, ObligationGroup) for g in groups)
        total = sum(g.obligation_count for g in groups)
        assert total == len(obligations), "Groups should cover all obligations"

    def test_group_obligations_fixture(self, sample_obligations):
        groups = group_obligations(sample_obligations)
        assert len(groups) >= 1
        assert groups[0].obligation_count == len(sample_obligations)


# ---------------------------------------------------------------------------
# APQC loader
# ---------------------------------------------------------------------------

class TestAPQCLoader:
    @pytest.mark.skipif(not _APQC_PATH.exists(), reason="APQC Excel not found")
    def test_load_apqc_hierarchy(self):
        nodes = load_apqc_hierarchy(str(_APQC_PATH))
        assert len(nodes) > 1700, f"Expected 1800+ nodes, got {len(nodes)}"
        assert all(isinstance(n, APQCNode) for n in nodes)

    @pytest.mark.skipif(not _APQC_PATH.exists(), reason="APQC Excel not found")
    def test_apqc_depth_distribution(self):
        nodes = load_apqc_hierarchy(str(_APQC_PATH))
        depths = {n.depth for n in nodes}
        assert len(depths) >= 3, "Should have at least 3 depth levels"
        assert 3 in depths
        assert max(depths) >= 4

    def test_build_apqc_summary(self, sample_apqc_nodes):
        summary = build_apqc_summary(sample_apqc_nodes, max_depth=3)
        assert "11.1.1" in summary
        assert "Establish enterprise risk framework" in summary
        # Depth 4 items should NOT appear
        assert "11.1.1.1" not in summary

    def test_get_apqc_subtree(self, sample_apqc_nodes):
        subtree = get_apqc_subtree(sample_apqc_nodes, "11.1")
        assert len(subtree) >= 5
        for n in subtree:
            assert n.hierarchy_id.startswith("11.1")


# ---------------------------------------------------------------------------
# Control loader
# ---------------------------------------------------------------------------

class TestControlLoader:
    @pytest.mark.skipif(not _CONTROLS_DIR.exists(), reason="Control Dataset not found")
    def test_discover_control_files(self):
        files = discover_control_files(str(_CONTROLS_DIR))
        assert len(files) >= 1, "Should find at least 1 control file"
        assert all(f.endswith(".xlsx") for f in files)

    @pytest.mark.skipif(not _CONTROLS_DIR.exists(), reason="Control Dataset not found")
    def test_load_and_merge_controls(self):
        files = discover_control_files(str(_CONTROLS_DIR))
        controls = load_and_merge_controls(files)
        assert len(controls) > 100, f"Expected 100+ controls, got {len(controls)}"
        assert all(isinstance(c, ControlRecord) for c in controls)
        # Verify no duplicate control_ids
        ids = [c.control_id for c in controls]
        assert len(ids) == len(set(ids)), "Duplicate control IDs found"

    def test_build_control_index(self, sample_controls):
        index = build_control_index(sample_controls)
        assert len(index) > 0
        assert "11.1.1" in index

    def test_find_controls_for_apqc(self, sample_controls):
        index = build_control_index(sample_controls)
        results = find_controls_for_apqc(index, "11.1")
        assert len(results) >= 2, "Should find controls at 11.1.x"

    def test_find_controls_no_match(self, sample_controls):
        index = build_control_index(sample_controls)
        results = find_controls_for_apqc(index, "99.9")
        assert len(results) == 0
