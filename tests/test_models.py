"""Tests for core Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from controlnexus.core.models import (
    DomainRegistry,
    ExemplarControl,
    OutputConfig,
    RiskProfile,
    RunConfig,
    ScopeConfig,
    SectionProfile,
    SizingConfig,
    TaxonomyCatalog,
    TaxonomyItem,
    TransportConfig,
)
from controlnexus.core.state import (
    ControlAssignment,
    FinalControlRecord,
    GapReport,
    HierarchyNode,
    RegulatoryGap,
    ValidationResult,
)


class TestRiskProfile:
    def test_construction(self):
        rp = RiskProfile(inherent_risk=4, regulatory_intensity=5, control_density=4, multiplier=2.9, rationale="High")
        assert rp.inherent_risk == 4
        assert rp.multiplier == 2.9

    def test_frozen(self):
        rp = RiskProfile(inherent_risk=4, regulatory_intensity=5, control_density=4, multiplier=2.9, rationale="High")
        with pytest.raises(ValidationError):
            rp.inherent_risk = 3


class TestTaxonomyItem:
    def test_construction(self):
        item = TaxonomyItem(control_type="Reconciliation", definition="A process of comparing records")
        assert item.control_type == "Reconciliation"

    def test_frozen(self):
        item = TaxonomyItem(control_type="Reconciliation", definition="Test")
        with pytest.raises(ValidationError):
            item.control_type = "Other"


class TestExemplarControl:
    def test_frozen(self):
        ec = ExemplarControl(
            control_type="Reconciliation",
            placement="Detective",
            method="Manual",
            full_description="Test description",
            word_count=2,
            quality_rating="Strong",
        )
        with pytest.raises(ValidationError):
            ec.quality_rating = "Weak"


class TestScopeConfig:
    def test_valid(self):
        sc = ScopeConfig(sections=["4", "9"])
        assert len(sc.sections) == 2

    def test_empty_sections_raises(self):
        with pytest.raises(ValidationError):
            ScopeConfig(sections=[])

    def test_blank_section_raises(self):
        with pytest.raises(ValidationError):
            ScopeConfig(sections=["4", ""])


class TestSizingConfig:
    def test_compat_target_override(self):
        sc = SizingConfig(**{"target_override": 100, "mode": "derived"})
        assert sc.target_count == 100

    def test_negative_target_raises(self):
        with pytest.raises(ValidationError):
            SizingConfig(target_count=-1)

    def test_zero_target_raises(self):
        with pytest.raises(ValidationError):
            SizingConfig(target_count=0)

    def test_none_is_valid(self):
        sc = SizingConfig()
        assert sc.target_count is None


class TestSectionProfile:
    def test_extra_fields_ignored(self):
        sp = SectionProfile(
            section_id="4.0",
            domain="Procurement",
            risk_profile=RiskProfile(
                inherent_risk=3, regulatory_intensity=4, control_density=3, multiplier=2.3, rationale="Test"
            ),
            registry=DomainRegistry(),
            unknown_field="should_be_ignored",
        )
        assert sp.section_id == "4.0"


class TestRunConfig:
    def test_minimal_valid(self):
        rc = RunConfig(
            run_id="test-001",
            scope=ScopeConfig(sections=["4"]),
            sizing=SizingConfig(),
            checkpoint={"enabled": True, "resume": True, "directory": "./checkpoints"},
            transport=TransportConfig(),
            concurrency={"max_parallel_sections": 1, "max_parallel_controls": 1},
            output=OutputConfig(),
        )
        assert rc.run_id == "test-001"


class TestOutputConfig:
    def test_default_formats(self):
        oc = OutputConfig()
        assert oc.formats == ["excel"]


class TestFinalControlRecord:
    def test_to_export_dict(self):
        record = FinalControlRecord(
            control_id="CTRL-0401-REC-001",
            hierarchy_id="4.1.1.1",
            leaf_name="Test",
        )
        export = record.to_export_dict()
        assert len(export) == 19
        assert "control_id" in export
        assert "control_type" not in export or export.get("control_type") is not None
        assert "placement" not in export
        assert "method" not in export

    def test_export_keys(self):
        record = FinalControlRecord(control_id="CTRL-0401-REC-001", hierarchy_id="4.1.1.1")
        export = record.to_export_dict()
        expected_keys = {
            "control_id",
            "hierarchy_id",
            "leaf_name",
            "selected_level_1",
            "selected_level_2",
            "business_unit_id",
            "business_unit_name",
            "who",
            "what",
            "when",
            "frequency",
            "where",
            "why",
            "full_description",
            "quality_rating",
            "validator_passed",
            "validator_retries",
            "validator_failures",
            "evidence",
        }
        assert set(export.keys()) == expected_keys


class TestValidationResult:
    def test_frozen(self):
        vr = ValidationResult(passed=True, failures=[], word_count=45)
        with pytest.raises(ValidationError):
            vr.passed = False


class TestHierarchyNode:
    def test_construction(self):
        node = HierarchyNode(hierarchy_id="4.1.1.1", name="Develop procurement plan")
        assert node.hierarchy_id == "4.1.1.1"
        assert node.is_leaf is False


class TestControlAssignment:
    def test_defaults(self):
        ca = ControlAssignment(hierarchy_id="4.1.1.1", leaf_name="Test", control_type="Reconciliation")
        assert ca.business_unit_id == "BU-UNSPECIFIED"


class TestGapReport:
    def test_empty_report(self):
        report = GapReport()
        assert report.overall_score == 0.0
        assert len(report.regulatory_gaps) == 0

    def test_with_gaps(self):
        report = GapReport(
            regulatory_gaps=[RegulatoryGap(framework="SOX", required_theme="SOX")],
            overall_score=42.5,
            summary="Gaps found",
        )
        assert len(report.regulatory_gaps) == 1
        assert report.overall_score == 42.5


class TestTaxonomyCatalog:
    def test_empty(self):
        cat = TaxonomyCatalog()
        assert len(cat.control_types) == 0
        assert len(cat.business_units) == 0
