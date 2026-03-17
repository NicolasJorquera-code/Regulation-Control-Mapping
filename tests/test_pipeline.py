"""Tests for controlnexus.analysis.pipeline."""

from __future__ import annotations


from controlnexus.analysis.pipeline import run_analysis
from controlnexus.core.models import (
    AffinityMatrix,
    DomainRegistry,
    RiskProfile,
    SectionProfile,
)
from controlnexus.core.state import FinalControlRecord


def _make_control(**overrides) -> FinalControlRecord:
    base = {
        "control_id": "CTRL-0401-REC-001",
        "hierarchy_id": "4.1.1.1",
        "leaf_name": "Test leaf",
        "full_description": "Monthly reconciliation of accounts by the senior accountant in the GL system to prevent discrepancies and ensure compliance.",
        "selected_level_1": "Preventive",
        "selected_level_2": "Reconciliation",
        "business_unit_id": "BU-001",
        "who": "Senior Accountant",
        "what": "Reconciles accounts",
        "when": "Monthly",
        "frequency": "Monthly",
        "where": "GL System",
        "why": "To prevent unreconciled discrepancies and ensure SOX compliance",
        "quality_rating": "Strong",
        "validator_passed": True,
        "evidence": "GL reconciliation report with Senior Accountant sign-off, retained in the financial close platform",
    }
    base.update(overrides)
    return FinalControlRecord(**base)


def _make_profile() -> SectionProfile:
    return SectionProfile(
        section_id="4.0",
        domain="test",
        risk_profile=RiskProfile(
            inherent_risk=3, regulatory_intensity=3, control_density=3,
            multiplier=1.0, rationale="test",
        ),
        registry=DomainRegistry(
            roles=["Senior Accountant"],
            systems=["GL System"],
            regulatory_frameworks=["SOX Compliance"],
        ),
        affinity=AffinityMatrix(
            HIGH=["Reconciliation"],
            MEDIUM=["Authorization"],
            LOW=["Training and Awareness Programs"],
            NONE=[],
        ),
    )


class TestRunAnalysis:
    def test_empty_controls(self):
        report = run_analysis([], {"4.0": _make_profile()})
        assert report.overall_score >= 0
        assert report.summary == "No gaps identified"

    def test_healthy_controls(self):
        controls = [_make_control() for _ in range(5)]
        profiles = {"4.0": _make_profile()}
        report = run_analysis(controls, profiles)
        assert report.overall_score > 0
        assert isinstance(report.overall_score, float)

    def test_report_contains_all_fields(self):
        controls = [_make_control()]
        profiles = {"4.0": _make_profile()}
        report = run_analysis(controls, profiles)
        assert hasattr(report, "regulatory_gaps")
        assert hasattr(report, "balance_gaps")
        assert hasattr(report, "frequency_issues")
        assert hasattr(report, "evidence_issues")
        assert hasattr(report, "overall_score")
        assert hasattr(report, "summary")

    def test_score_in_range(self):
        controls = [_make_control() for _ in range(10)]
        profiles = {"4.0": _make_profile()}
        report = run_analysis(controls, profiles)
        assert 0 <= report.overall_score <= 100

    def test_poor_evidence_lowers_score(self):
        good_controls = [_make_control() for _ in range(5)]
        bad_controls = [_make_control(evidence="") for _ in range(5)]
        profiles = {"4.0": _make_profile()}

        good_report = run_analysis(good_controls, profiles)
        bad_report = run_analysis(good_controls + bad_controls, profiles)
        assert bad_report.overall_score <= good_report.overall_score
