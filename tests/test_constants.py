"""Tests for core constants and utility functions."""

from __future__ import annotations

from controlnexus.core.constants import (
    build_control_id,
    derive_frequency_from_when,
    type_to_code,
)


class TestDeriveFrequencyFromWhen:
    def test_daily(self):
        assert derive_frequency_from_when("daily review") == "Daily"
        assert derive_frequency_from_when("end of day reconciliation") == "Daily"

    def test_weekly(self):
        assert derive_frequency_from_when("weekly monitoring") == "Weekly"
        assert derive_frequency_from_when("biweekly check") == "Weekly"

    def test_monthly(self):
        assert derive_frequency_from_when("monthly within 5 business days of month-end") == "Monthly"
        assert derive_frequency_from_when("every month") == "Monthly"

    def test_quarterly(self):
        assert derive_frequency_from_when("quarterly assessment") == "Quarterly"
        assert derive_frequency_from_when("each quarter") == "Quarterly"

    def test_semi_annual(self):
        assert derive_frequency_from_when("semi-annual review") == "Semi-Annual"
        assert derive_frequency_from_when("twice a year") == "Semi-Annual"

    def test_annual(self):
        assert derive_frequency_from_when("annually") == "Annual"
        assert derive_frequency_from_when("once a year") == "Annual"

    def test_other(self):
        assert derive_frequency_from_when("as needed") == "Other"
        assert derive_frequency_from_when("upon request") == "Other"

    def test_empty(self):
        assert derive_frequency_from_when("") == "Other"
        assert derive_frequency_from_when(None) == "Other"

    def test_case_insensitive(self):
        assert derive_frequency_from_when("DAILY") == "Daily"
        assert derive_frequency_from_when("Monthly Review") == "Monthly"


class TestTypeToCode:
    def test_known_types(self):
        assert type_to_code("Reconciliation") == "REC"
        assert type_to_code("Authorization") == "AUT"
        assert type_to_code("Third Party Due Diligence") == "THR"

    def test_unknown_type_consonant_fallback(self):
        code = type_to_code("Custom Control Type")
        assert len(code) == 3
        assert code == code.upper()


class TestBuildControlId:
    def test_standard_format(self):
        cid = build_control_id("4.1.1.1", "REC", 1)
        assert cid == "CTRL-0401-REC-001"

    def test_sequence_padding(self):
        cid = build_control_id("9.2.1.1", "AUT", 42)
        assert cid == "CTRL-0902-AUT-042"

    def test_single_level(self):
        cid = build_control_id("4", "REC", 1)
        assert cid == "CTRL-0400-REC-001"
