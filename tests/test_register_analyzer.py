"""Tests for controlnexus.analysis.register_analyzer."""

from __future__ import annotations

from pathlib import Path

import pytest

from controlnexus.analysis.register_analyzer import RegisterSummary, analyze_register


FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ── RegisterSummary model ─────────────────────────────────────────────────────


class TestRegisterSummary:
    def test_empty_summary(self):
        s = RegisterSummary()
        assert s.row_count == 0
        assert s.unique_control_types == []
        assert s.unique_business_units == []

    def test_fields_populated(self):
        s = RegisterSummary(
            row_count=5,
            unique_control_types=["Access Review"],
            unique_business_units=[{"id": "BU-001", "name": "Retail Banking"}],
            unique_sections=[{"id": "1.0", "name": "Lending"}],
            unique_placements=["Preventive"],
            unique_methods=["Automated"],
            frequency_values=["Daily"],
            role_mentions=["IT Security"],
            system_mentions=["LOS"],
        )
        assert s.row_count == 5
        assert "Access Review" in s.unique_control_types


# ── analyze_register with standard headers ────────────────────────────────────


class TestAnalyzeStandardRegister:
    @pytest.fixture
    def summary(self) -> RegisterSummary:
        return analyze_register(FIXTURES / "sample_register.xlsx")

    def test_total_rows(self, summary: RegisterSummary):
        assert summary.row_count == 10

    def test_control_types_extracted(self, summary: RegisterSummary):
        assert "Access Review" in summary.unique_control_types
        assert "Reconciliation" in summary.unique_control_types
        assert len(summary.unique_control_types) >= 8

    def test_business_units_extracted(self, summary: RegisterSummary):
        bu_names = [bu["name"] for bu in summary.unique_business_units]
        assert "Retail Banking" in bu_names

    def test_sections_extracted(self, summary: RegisterSummary):
        # Section values like "1.0 Lending" are parsed to top-level IDs
        sec_ids = [s["id"] for s in summary.unique_sections]
        assert "1.0" in sec_ids or any(s.startswith("1") for s in sec_ids)

    def test_placements_extracted(self, summary: RegisterSummary):
        assert "Preventive" in summary.unique_placements
        assert "Detective" in summary.unique_placements

    def test_methods_extracted(self, summary: RegisterSummary):
        assert "Automated" in summary.unique_methods
        assert "Manual" in summary.unique_methods

    def test_frequencies_extracted(self, summary: RegisterSummary):
        assert "Daily" in summary.frequency_values

    def test_roles_extracted(self, summary: RegisterSummary):
        assert len(summary.role_mentions) > 0

    def test_systems_extracted(self, summary: RegisterSummary):
        assert len(summary.system_mentions) > 0

    def test_regulatory_frameworks(self, summary: RegisterSummary):
        assert len(summary.regulatory_mentions) > 0


# ── analyze_register with nonstandard headers ─────────────────────────────────


class TestAnalyzeNonstandardRegister:
    @pytest.fixture
    def summary(self) -> RegisterSummary:
        return analyze_register(FIXTURES / "nonstandard_register.xlsx")

    def test_total_rows(self, summary: RegisterSummary):
        assert summary.row_count == 3

    def test_fuzzy_header_matching(self, summary: RegisterSummary):
        # "Type of Control" should match "control_type"
        assert "SOD Review" in summary.unique_control_types
        # "Division" should match "business_unit_name"
        bu_names = [bu["name"] for bu in summary.unique_business_units]
        assert "Operations" in bu_names
        # "How Often" should match "frequency"
        assert "Monthly" in summary.frequency_values

    def test_descriptions_captured(self, summary: RegisterSummary):
        assert len(summary.sample_descriptions) >= 1


# ── Edge cases ────────────────────────────────────────────────────────────────


class TestAnalyzerEdgeCases:
    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            analyze_register(Path("/nonexistent/file.xlsx"))
