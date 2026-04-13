"""Tests for controlnexus.ui.control_builder (unit tests for helpers, no Streamlit)."""

from __future__ import annotations

import pytest

from controlnexus.ui.control_builder import (
    STEP_LABELS,
    TOTAL_STEPS,
    _auto_code,
    _DEFAULT_FREQUENCY_TIERS,
    _DEFAULT_METHODS,
    _DEFAULT_PLACEMENTS,
    _DEFAULT_QUALITY_RATINGS,
    _AFFINITY_LEVELS,
)


class TestAutoCode:
    def test_simple_name(self):
        assert _auto_code("Access Review") == "CCS"  # consonants: ccssRvw → CCS

    def test_short_name(self):
        code = _auto_code("IT")
        assert len(code) <= 3

    def test_empty_name(self):
        assert _auto_code("") == "UNK"

    def test_vowels_only(self):
        assert _auto_code("aeiou") == "UNK"

    def test_name_with_spaces(self):
        # "Change Management" consonants: ChngMngmnt → CHN
        code = _auto_code("Change Management")
        assert len(code) == 3
        assert code.isupper()


class TestConstants:
    def test_step_count(self):
        assert TOTAL_STEPS == 5
        assert len(STEP_LABELS) == 5

    def test_step_labels(self):
        assert STEP_LABELS[0] == "Basics"
        assert STEP_LABELS[-1] == "Review & Export"

    def test_default_placements(self):
        assert "Preventive" in _DEFAULT_PLACEMENTS
        assert "Detective" in _DEFAULT_PLACEMENTS

    def test_default_methods(self):
        assert "Automated" in _DEFAULT_METHODS
        assert "Manual" in _DEFAULT_METHODS

    def test_default_frequency_tiers(self):
        labels = [t["label"] for t in _DEFAULT_FREQUENCY_TIERS]
        assert "Daily" in labels
        assert "Annual" in labels
        # Sorted by rank (most frequent first)
        ranks = [t["rank"] for t in _DEFAULT_FREQUENCY_TIERS]
        assert ranks == sorted(ranks)

    def test_default_quality_ratings(self):
        assert len(_DEFAULT_QUALITY_RATINGS) == 4

    def test_affinity_levels(self):
        assert _AFFINITY_LEVELS == ["HIGH", "MEDIUM", "LOW", "NONE"]
