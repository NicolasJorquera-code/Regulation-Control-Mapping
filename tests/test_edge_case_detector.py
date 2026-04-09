"""
Tests for EdgeCaseDetector and the 3-tier coverage resolution system.
"""

from __future__ import annotations

import asyncio

import pytest

from regrisk.agents.base import AgentContext
from regrisk.agents.coverage_assessor import CoverageAssessorAgent
from regrisk.agents.edge_case_detector import (
    EdgeCaseDetector,
    EdgeCaseReason,
    EdgeCaseResult,
    ResolutionTier,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detector() -> EdgeCaseDetector:
    return EdgeCaseDetector()


@pytest.fixture
def no_llm_context() -> AgentContext:
    return AgentContext(client=None)


@pytest.fixture
def sample_obligation() -> dict:
    return {
        "citation": "12 CFR 252.34(a)(1)",
        "abstract": (
            "The board of directors must approve and review the liquidity risk "
            "tolerance at least annually and ensure that senior management establishes "
            "adequate policies and procedures to maintain compliance."
        ),
        "section_title": "Liquidity Risk Management",
        "obligation_category": "Controls",
        "relationship_type": "Constrains Execution",
        "criticality_tier": "High",
    }


@pytest.fixture
def strong_control() -> dict:
    """A control that strongly matches the sample obligation."""
    return {
        "control_id": "CTRL-1100-RSK-001",
        "hierarchy_id": "11.1.1",
        "leaf_name": "Enterprise risk framework controls",
        "full_description": "CRO reviews and ensures risk appetite thresholds are maintained and approved by board.",
        "selected_level_2": "Risk Limit Setting",
        "who": "CRO",
        "what": "Reviews risk tolerance, ensures approve and maintain compliance controls",
        "when": "At each annual cycle",
        "frequency": "Annual",
        "where": "Governance Platform",
        "why": "To ensure regulatory and internal policy compliance.",
        "evidence": "Board approval minutes",
    }


@pytest.fixture
def weak_control() -> dict:
    """A control with only weak structural match."""
    return {
        "control_id": "CTRL-0900-FIN-002",
        "hierarchy_id": "9.7.1",
        "leaf_name": "Treasury policy compliance",
        "full_description": "Treasury manager verifies treasury policy compliance.",
        "selected_level_2": "Verification and Validation",
        "who": "Treasury Manager",
        "what": "Verifies policy status",
        "when": "Monthly",
        "frequency": "Monthly",
        "where": "Treasury System",
        "why": "To verify treasury operations.",
        "evidence": "Treasury logs",
    }


@pytest.fixture
def short_obligation() -> dict:
    """An obligation with very short, ambiguous text."""
    return {
        "citation": "12 CFR 252.50(a)",
        "abstract": "General authority provision.",
        "section_title": "Authority",
        "obligation_category": "Controls",
        "relationship_type": "N/A",
        "criticality_tier": "Low",
    }


# ---------------------------------------------------------------------------
# EdgeCaseDetector tests
# ---------------------------------------------------------------------------

class TestEdgeCaseDetectorBasic:
    def test_no_candidates_is_edge_case(self, detector, sample_obligation):
        result = detector.detect_coverage_edge_case(sample_obligation, [])
        assert result.is_edge_case is True
        assert EdgeCaseReason.NO_CANDIDATE_CONTROLS in result.reasons

    def test_strong_match_not_edge_case(self, detector, sample_obligation, strong_control):
        mapping = {"apqc_hierarchy_id": "11.1.1", "confidence": 0.9}
        result = detector.detect_coverage_edge_case(
            sample_obligation, [strong_control], mapping,
        )
        # May or may not be edge case depending on keyword overlap, but
        # should NOT have NO_CANDIDATE_CONTROLS
        assert EdgeCaseReason.NO_CANDIDATE_CONTROLS not in result.reasons

    def test_short_text_is_edge_case(self, detector, short_obligation, weak_control):
        result = detector.detect_coverage_edge_case(
            short_obligation, [weak_control],
        )
        assert result.is_edge_case is True
        assert EdgeCaseReason.AMBIGUOUS_OBLIGATION_TEXT in result.reasons

    def test_low_confidence_mapping(self, detector, sample_obligation, strong_control):
        mapping = {"apqc_hierarchy_id": "11.1.1", "confidence": 0.2}
        result = detector.detect_coverage_edge_case(
            sample_obligation, [strong_control], mapping,
        )
        assert EdgeCaseReason.LOW_CONFIDENCE_MAPPING in result.reasons

    def test_weak_structural_match(self, detector, sample_obligation, weak_control):
        mapping = {"apqc_hierarchy_id": "11.1.1", "confidence": 0.8}
        result = detector.detect_coverage_edge_case(
            sample_obligation, [weak_control], mapping,
        )
        assert EdgeCaseReason.WEAK_STRUCTURAL_MATCH in result.reasons

    def test_cross_domain_mapping(self, detector, sample_obligation, weak_control):
        mapping = {"apqc_hierarchy_id": "11.1.1", "confidence": 0.8}
        # weak_control is at 9.7.1, mapping is at 11.1.1 → cross domain
        result = detector.detect_coverage_edge_case(
            sample_obligation, [weak_control], mapping,
        )
        assert EdgeCaseReason.CROSS_DOMAIN_MAPPING in result.reasons

    def test_relationship_unclear(self, detector, short_obligation, weak_control):
        # obligation_category=Controls but relationship_type=N/A
        result = detector.detect_coverage_edge_case(
            short_obligation, [weak_control],
        )
        assert EdgeCaseReason.RELATIONSHIP_TYPE_UNCLEAR in result.reasons

    def test_many_conflicting_controls(self, detector, sample_obligation, weak_control):
        # 6 controls → exceeds max_candidate_controls_for_conflict=5
        many_controls = [weak_control] * 6
        result = detector.detect_coverage_edge_case(
            sample_obligation, many_controls,
        )
        assert EdgeCaseReason.MULTIPLE_CONFLICTING_MATCHES in result.reasons


class TestEdgeCaseResultSerialization:
    def test_to_dict_roundtrip(self):
        result = EdgeCaseResult(
            is_edge_case=True,
            reasons=(EdgeCaseReason.LOW_KEYWORD_OVERLAP, EdgeCaseReason.WEAK_STRUCTURAL_MATCH),
            tier=ResolutionTier.EDGE_CASE_LLM,
            details={"keyword_overlap_score": 1},
        )
        d = result.to_dict()
        assert d["is_edge_case"] is True
        assert d["tier"] == "edge_case_llm"
        assert "low_keyword_overlap" in d["reasons"]
        assert "weak_structural_match" in d["reasons"]
        assert d["details"]["keyword_overlap_score"] == 1


class TestEdgeCaseDetectorMapping:
    def test_no_mappings_is_edge_case(self, detector, sample_obligation):
        result = detector.detect_mapping_edge_case(sample_obligation, [])
        assert result.is_edge_case is True

    def test_low_confidence_mappings(self, detector, sample_obligation):
        mappings = [
            {"apqc_hierarchy_id": "11.1.1", "confidence": 0.3},
            {"apqc_hierarchy_id": "11.2.1", "confidence": 0.2},
        ]
        result = detector.detect_mapping_edge_case(sample_obligation, mappings)
        assert EdgeCaseReason.LOW_CONFIDENCE_MAPPING in result.reasons

    def test_good_mappings_not_edge_case(self, detector, sample_obligation):
        mappings = [
            {"apqc_hierarchy_id": "11.1.1", "confidence": 0.9},
        ]
        result = detector.detect_mapping_edge_case(sample_obligation, mappings)
        assert result.is_edge_case is False


# ---------------------------------------------------------------------------
# CoverageAssessorAgent 3-tier tests
# ---------------------------------------------------------------------------

class TestCoverageAssessor3Tier:
    """Test the 3-tier resolution in the coverage assessor agent (no LLM)."""

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_tier1_deterministic_strong_match(
        self, no_llm_context, sample_obligation, strong_control,
    ):
        agent = CoverageAssessorAgent(no_llm_context)
        mapping = {"apqc_hierarchy_id": "11.1.1", "confidence": 0.9}
        result = self._run(agent.execute(
            obligation=sample_obligation,
            control=strong_control,
            candidate_controls=[strong_control],
            mapping=mapping,
            apqc_hierarchy_id="11.1.1",
            apqc_process_name="Establish enterprise risk framework",
        ))

        assert result["overall_coverage"] in ("Covered", "Partially Covered")
        edge = result.get("edge_case", {})
        assert edge.get("llm_used") is False
        assert edge.get("resolution_tier") in ("deterministic", "deterministic_fallback")

    def test_tier3_fallback_for_edge_case_no_llm(
        self, no_llm_context, sample_obligation, weak_control,
    ):
        agent = CoverageAssessorAgent(no_llm_context)
        mapping = {"apqc_hierarchy_id": "11.1.1", "confidence": 0.3}
        result = self._run(agent.execute(
            obligation=sample_obligation,
            control=weak_control,
            candidate_controls=[weak_control],
            mapping=mapping,
            apqc_hierarchy_id="11.1.1",
            apqc_process_name="Establish enterprise risk framework",
        ))

        edge = result.get("edge_case", {})
        assert edge.get("is_edge_case") is True
        assert edge.get("llm_used") is False
        assert edge.get("resolution_tier") == "deterministic_fallback"
        assert result["overall_coverage"] == "Partially Covered"

    def test_no_controls_produces_not_covered(
        self, no_llm_context, sample_obligation,
    ):
        agent = CoverageAssessorAgent(no_llm_context)
        result = self._run(agent.execute(
            obligation=sample_obligation,
            control=None,
            candidate_controls=[],
            mapping=None,
            apqc_hierarchy_id="11.1.1",
            apqc_process_name="Establish enterprise risk framework",
        ))

        assert result["overall_coverage"] == "Not Covered"
        edge = result.get("edge_case", {})
        assert edge.get("is_edge_case") is True
        assert "no_candidate_controls" in edge.get("reasons", [])

    def test_edge_case_audit_trail_complete(
        self, no_llm_context, sample_obligation, weak_control,
    ):
        """Verify the edge_case dict has all required audit fields."""
        agent = CoverageAssessorAgent(no_llm_context)
        result = self._run(agent.execute(
            obligation=sample_obligation,
            control=weak_control,
            candidate_controls=[weak_control],
            mapping={"apqc_hierarchy_id": "11.1.1", "confidence": 0.2},
            apqc_hierarchy_id="11.1.1",
        ))

        edge = result["edge_case"]
        assert "is_edge_case" in edge
        assert "reasons" in edge
        assert "resolution_tier" in edge
        assert "llm_used" in edge
        assert "details" in edge
        assert isinstance(edge["reasons"], list)
        assert isinstance(edge["details"], dict)


class TestEdgeCaseCustomThresholds:
    def test_custom_low_confidence_cutoff(self, sample_obligation, strong_control):
        # With a very high cutoff, even 0.8 confidence triggers edge case
        detector = EdgeCaseDetector(thresholds={"low_confidence_cutoff": 0.95})
        mapping = {"apqc_hierarchy_id": "11.1.1", "confidence": 0.8}
        result = detector.detect_coverage_edge_case(
            sample_obligation, [strong_control], mapping,
        )
        assert EdgeCaseReason.LOW_CONFIDENCE_MAPPING in result.reasons

    def test_custom_min_keyword_overlap(self, sample_obligation, strong_control):
        # With a very high keyword overlap requirement, it should trigger
        detector = EdgeCaseDetector(thresholds={"min_keyword_overlap": 20})
        result = detector.detect_coverage_edge_case(
            sample_obligation, [strong_control],
        )
        assert EdgeCaseReason.LOW_KEYWORD_OVERLAP in result.reasons
