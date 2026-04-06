"""
Tests for Pydantic domain models — construction, frozen enforcement, serialization.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from regrisk.core.models import (
    APQCNode,
    ClassifiedObligation,
    ComplianceMatrix,
    ControlRecord,
    CoverageAssessment,
    GapReport,
    Obligation,
    ObligationAPQCMapping,
    ObligationGroup,
    RiskRegister,
    ScoredRisk,
)


class TestObligation:
    def test_construction(self):
        ob = Obligation(
            citation="12 CFR 252.34(a)(1)",
            mandate_title="Regulation YY",
            abstract="Test abstract",
            text="",
            link="https://example.com",
            status="In Force",
            title_level_2="Subpart D",
            title_level_3="Liquidity",
            title_level_4="Tolerance",
            title_level_5="",
            citation_level_2="Subpart D",
            citation_level_3="12 CFR 252.34",
            effective_date="2021-04-01",
            applicability="",
        )
        assert ob.citation == "12 CFR 252.34(a)(1)"
        assert ob.status == "In Force"

    def test_frozen(self):
        ob = Obligation(
            citation="test", mandate_title="", abstract="", text="", link="",
            status="", title_level_2="", title_level_3="", title_level_4="",
            title_level_5="", citation_level_2="", citation_level_3="",
            effective_date="", applicability="",
        )
        with pytest.raises(ValidationError):
            ob.citation = "modified"

    def test_serialization(self):
        ob = Obligation(
            citation="test", mandate_title="", abstract="A", text="", link="",
            status="In Force", title_level_2="", title_level_3="", title_level_4="",
            title_level_5="", citation_level_2="", citation_level_3="",
            effective_date="", applicability="",
        )
        d = ob.model_dump()
        assert isinstance(d, dict)
        assert d["citation"] == "test"
        assert d["abstract"] == "A"


class TestAPQCNode:
    def test_construction(self):
        node = APQCNode(pcf_id=10001, hierarchy_id="11.1.1", name="Test", depth=3, parent_id="11.1")
        assert node.depth == 3

    def test_frozen(self):
        node = APQCNode(pcf_id=1, hierarchy_id="1.0", name="X", depth=1, parent_id="")
        with pytest.raises(ValidationError):
            node.name = "modified"


class TestControlRecord:
    def test_construction(self):
        ctrl = ControlRecord(
            control_id="CTRL-001", hierarchy_id="11.1.1", leaf_name="Test",
            full_description="Desc", selected_level_1="Preventive",
            selected_level_2="Authorization", who="CRO", what="Approves",
            when="Annual", frequency="Annual", where="Platform",
            why="Compliance", evidence="Report", quality_rating="Strong",
            business_unit_name="Risk",
        )
        assert ctrl.control_id == "CTRL-001"

    def test_frozen(self):
        ctrl = ControlRecord(
            control_id="X", hierarchy_id="1.0", leaf_name="", full_description="",
            selected_level_1="", selected_level_2="", who="", what="",
            when="", frequency="", where="", why="", evidence="",
            quality_rating="", business_unit_name="",
        )
        with pytest.raises(ValidationError):
            ctrl.control_id = "Y"


class TestClassifiedObligation:
    def test_construction(self):
        co = ClassifiedObligation(
            citation="test", abstract="test abstract",
            section_citation="12 CFR 252.34", section_title="Liquidity",
            subpart="Subpart D", obligation_category="Controls",
            relationship_type="Constrains Execution",
            criticality_tier="High",
            classification_rationale="Test rationale",
        )
        assert co.obligation_category == "Controls"


class TestObligationAPQCMapping:
    def test_construction(self):
        m = ObligationAPQCMapping(
            citation="test", apqc_hierarchy_id="11.1.1",
            apqc_process_name="Test process",
            relationship_type="Constrains Execution",
            relationship_detail="Board must approve",
            confidence=0.92,
        )
        assert m.confidence == 0.92

    def test_confidence_range(self):
        with pytest.raises(ValidationError):
            ObligationAPQCMapping(
                citation="test", apqc_hierarchy_id="11.1.1",
                apqc_process_name="Test",
                relationship_type="test",
                relationship_detail="test",
                confidence=1.5,  # out of range
            )


class TestCoverageAssessment:
    def test_construction(self):
        ca = CoverageAssessment(
            citation="test", apqc_hierarchy_id="11.1.1",
            control_id="CTRL-001", structural_match=True,
            semantic_match="Full", semantic_rationale="Direct match",
            relationship_match="Satisfied", relationship_rationale="Matches frequency",
            overall_coverage="Covered",
        )
        assert ca.overall_coverage == "Covered"


class TestScoredRisk:
    def test_construction(self):
        risk = ScoredRisk(
            risk_id="RISK-001", source_citation="test",
            source_apqc_id="11.1.1", risk_description="Test risk description",
            risk_category="Compliance Risk",
            sub_risk_category="Regulatory Compliance Risk",
            impact_rating=3, impact_rationale="High impact",
            frequency_rating=2, frequency_rationale="Unlikely",
            inherent_risk_rating="High",
            coverage_status="Not Covered",
        )
        assert risk.inherent_risk_rating == "High"

    def test_rating_range(self):
        with pytest.raises(ValidationError):
            ScoredRisk(
                risk_id="X", source_citation="", source_apqc_id="",
                risk_description="", risk_category="", sub_risk_category="",
                impact_rating=5,  # out of range
                impact_rationale="",
                frequency_rating=2, frequency_rationale="",
                inherent_risk_rating="", coverage_status="",
            )


class TestGapReport:
    def test_construction(self):
        report = GapReport(
            regulation_name="Reg YY",
            total_obligations=693,
            classified_counts={"Controls": 400, "Documentation": 200},
            mapped_obligation_count=500,
            coverage_summary={"Covered": 300, "Not Covered": 200},
            gaps=[],
        )
        assert report.total_obligations == 693


class TestComplianceMatrix:
    def test_construction(self):
        matrix = ComplianceMatrix(rows=[{"citation": "test"}])
        assert len(matrix.rows) == 1


class TestRiskRegister:
    def test_construction(self):
        reg = RiskRegister(
            scored_risks=[],
            total_risks=0,
            risk_distribution={},
            critical_count=0,
            high_count=0,
        )
        assert reg.total_risks == 0
