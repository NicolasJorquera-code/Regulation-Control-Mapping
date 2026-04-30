"""Tests for controlnexus.analysis.scanners."""

from __future__ import annotations


from controlnexus.analysis.scanners import (
    _score_evidence,
    ecosystem_balance_analysis,
    evidence_sufficiency_scan,
    frequency_coherence_scan,
    regulatory_coverage_scan,
    risk_coverage_scan,
)
from controlnexus.core.models import (
    AffinityMatrix,
    DomainRegistry,
    RiskProfile,
    SectionProfile,
)
from controlnexus.core.state import FinalControlRecord


# -- Helpers -------------------------------------------------------------------


def _make_control(**overrides) -> FinalControlRecord:
    base = {
        "control_id": "CTRL-0401-REC-001",
        "hierarchy_id": "4.1.1.1",
        "leaf_name": "Test leaf",
        "full_description": "Monthly reconciliation of accounts by the senior accountant in the GL system to prevent discrepancies.",
        "selected_level_1": "Preventive",
        "selected_level_2": "Reconciliation",
        "business_unit_id": "BU-001",
        "who": "Senior Accountant",
        "what": "Reconciles accounts",
        "when": "Monthly, by the 5th business day",
        "frequency": "Monthly",
        "where": "General Ledger System",
        "why": "To prevent unreconciled account discrepancies and regulatory violations",
        "quality_rating": "Strong",
        "validator_passed": True,
        "evidence": "GL reconciliation report with Senior Accountant preparer sign-off, retained in the financial close platform",
    }
    base.update(overrides)
    return FinalControlRecord(**base)


def _make_profile(
    section_id: str = "4.0",
    frameworks: list[str] | None = None,
    affinity: AffinityMatrix | None = None,
) -> SectionProfile:
    return SectionProfile(
        section_id=section_id,
        domain="test",
        risk_profile=RiskProfile(
            inherent_risk=3,
            regulatory_intensity=3,
            control_density=3,
            multiplier=1.0,
            rationale="test",
        ),
        registry=DomainRegistry(
            roles=["Senior Accountant"],
            systems=["GL System"],
            regulatory_frameworks=frameworks or ["SOX Compliance", "OCC Guidelines"],
        ),
        affinity=affinity
        or AffinityMatrix(
            HIGH=["Reconciliation"],
            MEDIUM=["Authorization"],
            LOW=["Training and Awareness Programs"],
            NONE=["Surveillance"],
        ),
    )


# -- Regulatory Coverage Scan --------------------------------------------------


class TestRegulatoryCoverageScan:
    def test_no_controls_no_gaps(self):
        gaps = regulatory_coverage_scan([], {"4.0": _make_profile()})
        assert gaps == []

    def test_good_coverage_no_gaps(self):
        # Controls mention SOX and OCC keywords
        controls = [
            _make_control(why="Ensure SOX compliance and prevent violations"),
            _make_control(why="Meet OCC guidelines for regulatory compliance"),
            _make_control(why="SOX compliance verification"),
        ]
        profiles = {"4.0": _make_profile(frameworks=["SOX Compliance"])}
        gaps = regulatory_coverage_scan(controls, profiles)
        # "compliance" is a keyword from "SOX Compliance" — all controls match
        assert len(gaps) == 0

    def test_poor_coverage_flagged(self):
        controls = [
            _make_control(why="Prevent account errors"),
            _make_control(why="Ensure timely processing"),
            _make_control(why="Reduce manual effort"),
        ]
        profiles = {"4.0": _make_profile(frameworks=["Basel Capital Requirements"])}
        gaps = regulatory_coverage_scan(controls, profiles)
        assert len(gaps) >= 1
        assert gaps[0].framework == "Basel Capital Requirements"
        assert gaps[0].current_coverage < 0.6


class TestEcosystemBalanceAnalysis:
    def test_balanced_no_gaps(self):
        # 10 controls: 5 HIGH type (50%), 3 MEDIUM (30%), 2 LOW (20%)
        controls = (
            [_make_control(selected_level_2="Reconciliation") for _ in range(5)]
            + [_make_control(selected_level_2="Authorization") for _ in range(3)]
            + [_make_control(selected_level_2="Training and Awareness Programs") for _ in range(2)]
        )
        profiles = {"4.0": _make_profile()}
        gaps = ecosystem_balance_analysis(controls, profiles)
        # HIGH at 50% (>=40% ok), MEDIUM at 30% (20-40% ok), LOW at 20% (5-20% ok)
        # All within range
        assert len(gaps) == 0

    def test_over_represented_detected(self):
        # All controls are NONE-affinity type
        controls = [_make_control(selected_level_2="Surveillance") for _ in range(10)]
        profiles = {"4.0": _make_profile()}
        gaps = ecosystem_balance_analysis(controls, profiles)
        assert any(g.direction == "over" for g in gaps)

    def test_no_profile_no_gaps(self):
        controls = [_make_control()]
        gaps = ecosystem_balance_analysis(controls, {})
        assert gaps == []


class TestFrequencyCoherenceScan:
    def test_monthly_reconciliation_passes(self):
        controls = [
            _make_control(
                selected_level_2="Reconciliation",
                when="Monthly, by the 5th business day",
            )
        ]
        issues = frequency_coherence_scan(controls)
        assert len(issues) == 0

    def test_annual_reconciliation_fails(self):
        controls = [
            _make_control(
                selected_level_2="Reconciliation",
                when="Annually during the year-end close",
            )
        ]
        issues = frequency_coherence_scan(controls)
        assert len(issues) == 1
        assert issues[0].expected_frequency == "Monthly"
        assert issues[0].actual_frequency == "Annual"

    def test_quarterly_authorization_passes(self):
        controls = [
            _make_control(
                selected_level_2="Authorization",
                when="Quarterly review cycle",
            )
        ]
        issues = frequency_coherence_scan(controls)
        assert len(issues) == 0

    def test_annual_authorization_fails(self):
        controls = [
            _make_control(
                selected_level_2="Authorization",
                when="Annual review",
            )
        ]
        issues = frequency_coherence_scan(controls)
        assert len(issues) == 1

    def test_other_frequency_not_flagged(self):
        # "Other" frequency is not checked
        controls = [
            _make_control(
                selected_level_2="Reconciliation",
                when="On vendor engagement",
            )
        ]
        issues = frequency_coherence_scan(controls)
        assert len(issues) == 0


class TestEvidenceSufficiencyScan:
    def test_strong_evidence_passes(self):
        controls = [
            _make_control(
                evidence="GL reconciliation report with Senior Accountant sign-off, retained in the financial close platform",
            )
        ]
        issues = evidence_sufficiency_scan(controls)
        assert len(issues) == 0

    def test_weak_evidence_flagged(self):
        controls = [_make_control(evidence="Documentation")]
        issues = evidence_sufficiency_scan(controls)
        assert len(issues) == 1
        assert "0/3" in issues[0].issue or "1/3" in issues[0].issue

    def test_empty_evidence_flagged(self):
        controls = [_make_control(evidence="")]
        issues = evidence_sufficiency_scan(controls)
        assert len(issues) == 1


class TestScoreEvidence:
    def test_perfect_score(self):
        score, missing = _score_evidence(
            "GL reconciliation report with Senior Accountant sign-off, retained in the financial close platform"
        )
        assert score == 3
        assert missing == []

    def test_missing_signer(self):
        score, missing = _score_evidence("Reconciliation report retained in the GL platform")
        assert score == 2
        assert "signer/approver" in missing

    def test_empty_string(self):
        score, missing = _score_evidence("")
        assert score == 0
        assert len(missing) == 3


# -- Risk Coverage Scan --------------------------------------------------------


class TestRiskCoverageScan:
    """Test risk_coverage_scan for risk-aware gap analysis."""

    def test_no_risk_catalog_returns_empty(self):
        """Config without risk_catalog returns no gaps."""
        from controlnexus.core.domain_config import ControlTypeConfig, DomainConfig

        config = DomainConfig(
            control_types=[ControlTypeConfig(name="Auth", definition="d")],
        )
        gaps = risk_coverage_scan([], config)
        assert gaps == []

    def test_uncovered_high_severity_risk(self):
        """High-severity risk with 0 controls → high gap."""
        from controlnexus.core.domain_config import (
            ControlTypeConfig,
            DomainConfig,
            RiskCatalogEntry,
        )

        config = DomainConfig(
            control_types=[ControlTypeConfig(name="Auth", definition="d")],
            risk_catalog=[
                RiskCatalogEntry(id="R1", name="Critical Risk", default_severity=5),
                RiskCatalogEntry(id="R2", name="Low Risk", default_severity=2),
            ],
        )
        # One control covers R2, none cover R1
        controls = [_make_control(risk_id="R2")]
        gaps = risk_coverage_scan(controls, config)
        # R1 (severity 5) has 0 controls → high gap
        # R2 (severity 2) has 1 control which meets expected=1
        high_gaps = [g for g in gaps if g.risk_id == "R1"]
        assert len(high_gaps) == 1
        assert high_gaps[0].gap_severity == "high"
        assert high_gaps[0].actual_control_count == 0

    def test_partially_covered_risk(self):
        """Severity-4 risk with 1 control (expected 2) → low gap."""
        from controlnexus.core.domain_config import (
            ControlTypeConfig,
            DomainConfig,
            RiskCatalogEntry,
        )

        config = DomainConfig(
            control_types=[ControlTypeConfig(name="Auth", definition="d")],
            risk_catalog=[
                RiskCatalogEntry(id="R1", name="Important Risk", default_severity=4),
            ],
        )
        controls = [_make_control(risk_id="R1")]
        gaps = risk_coverage_scan(controls, config)
        assert len(gaps) == 1
        assert gaps[0].gap_severity == "low"
        assert gaps[0].actual_control_count == 1
        assert gaps[0].expected_control_count == 2

    def test_fully_covered_no_gaps(self):
        """All risks with sufficient controls → no gaps."""
        from controlnexus.core.domain_config import (
            ControlTypeConfig,
            DomainConfig,
            RiskCatalogEntry,
        )

        config = DomainConfig(
            control_types=[ControlTypeConfig(name="Auth", definition="d")],
            risk_catalog=[
                RiskCatalogEntry(id="R1", name="Low Risk", default_severity=2),
            ],
        )
        controls = [_make_control(risk_id="R1")]
        gaps = risk_coverage_scan(controls, config)
        assert gaps == []
