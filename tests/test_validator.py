"""Tests for controlnexus.validation.validator."""

from __future__ import annotations

import pytest

from controlnexus.validation.validator import (
    MAX_WORDS,
    MIN_WORDS,
    VAGUE_WHEN_TERMS,
    build_retry_appendix,
    validate,
)


def _make_narrative(**overrides) -> dict:
    """Build a passing narrative with sensible defaults."""
    base = {
        "who": "Accounting Manager",
        "what": "Reviews monthly reconciliation report",
        "when": "Monthly, by the 5th business day",
        "where": "General Ledger System",
        "why": "To mitigate the risk of unreconciled accounts",
        "full_description": " ".join(["word"] * 40),
    }
    base.update(overrides)
    return base


def _make_spec(**overrides) -> dict:
    base = {
        "who": "Accounting Manager",
        "where_system": "General Ledger System",
    }
    base.update(overrides)
    return base


class TestValidateAllPassing:
    def test_clean_narrative_passes(self):
        result = validate(_make_narrative(), _make_spec())
        assert result.passed is True
        assert result.failures == []
        assert result.word_count == 40


class TestMultipleWhats:
    def test_single_verb_passes(self):
        result = validate(_make_narrative(what="Reviews the report"), _make_spec())
        assert "MULTIPLE_WHATS" not in result.failures

    def test_three_verbs_fails(self):
        result = validate(
            _make_narrative(what="Reviews, approves, and validates the report"),
            _make_spec(),
        )
        assert "MULTIPLE_WHATS" in result.failures


class TestVagueWhen:
    @pytest.mark.parametrize("term", VAGUE_WHEN_TERMS)
    def test_vague_term_detected(self, term):
        result = validate(_make_narrative(when=f"Performed {term}"), _make_spec())
        assert "VAGUE_WHEN" in result.failures

    def test_specific_when_passes(self):
        result = validate(_make_narrative(when="Monthly"), _make_spec())
        assert "VAGUE_WHEN" not in result.failures


class TestWhoEqualsWhere:
    def test_identical_fails(self):
        result = validate(
            _make_narrative(who="Treasury", where="Treasury"),
            _make_spec(who="Treasury", where_system="Treasury"),
        )
        assert "WHO_EQUALS_WHERE" in result.failures

    def test_substring_fails(self):
        result = validate(
            _make_narrative(who="IT", where="IT Systems"),
            _make_spec(who="IT", where_system="IT Systems"),
        )
        assert "WHO_EQUALS_WHERE" in result.failures

    def test_distinct_passes(self):
        result = validate(_make_narrative(), _make_spec())
        assert "WHO_EQUALS_WHERE" not in result.failures


class TestWhyMissingRisk:
    def test_no_risk_marker_fails(self):
        result = validate(
            _make_narrative(why="To complete the process on time"),
            _make_spec(),
        )
        assert "WHY_MISSING_RISK" in result.failures

    @pytest.mark.parametrize("marker", ["risk", "prevent", "mitigate", "ensure", "compliance"])
    def test_risk_marker_passes(self, marker):
        result = validate(
            _make_narrative(why=f"To {marker} regulatory issues"),
            _make_spec(),
        )
        assert "WHY_MISSING_RISK" not in result.failures


class TestWordCount:
    def test_too_few_words_fails(self):
        result = validate(
            _make_narrative(full_description="Too short"),
            _make_spec(),
        )
        assert "WORD_COUNT_OUT_OF_RANGE" in result.failures
        assert result.word_count == 2

    def test_too_many_words_fails(self):
        result = validate(
            _make_narrative(full_description=" ".join(["word"] * 100)),
            _make_spec(),
        )
        assert "WORD_COUNT_OUT_OF_RANGE" in result.failures
        assert result.word_count == 100

    def test_min_boundary_passes(self):
        result = validate(
            _make_narrative(full_description=" ".join(["word"] * MIN_WORDS)),
            _make_spec(),
        )
        assert "WORD_COUNT_OUT_OF_RANGE" not in result.failures

    def test_max_boundary_passes(self):
        result = validate(
            _make_narrative(full_description=" ".join(["word"] * MAX_WORDS)),
            _make_spec(),
        )
        assert "WORD_COUNT_OUT_OF_RANGE" not in result.failures


class TestSpecMismatch:
    def test_who_mismatch_fails(self):
        result = validate(
            _make_narrative(who="CFO"),
            _make_spec(who="Accounting Manager"),
        )
        assert "SPEC_MISMATCH" in result.failures

    def test_where_mismatch_fails(self):
        result = validate(
            _make_narrative(where="SAP"),
            _make_spec(where_system="General Ledger System"),
        )
        assert "SPEC_MISMATCH" in result.failures

    def test_both_mismatch_deduplicates(self):
        result = validate(
            _make_narrative(who="CFO", where="SAP"),
            _make_spec(who="Accounting Manager", where_system="General Ledger System"),
        )
        assert result.failures.count("SPEC_MISMATCH") == 1


class TestBuildRetryAppendix:
    def test_contains_attempt_header(self):
        text = build_retry_appendix(2, 3, ["VAGUE_WHEN"], 40)
        assert "ATTEMPT 2/3" in text

    def test_each_failure_has_instruction(self):
        codes = [
            "MULTIPLE_WHATS",
            "VAGUE_WHEN",
            "WHO_EQUALS_WHERE",
            "WHY_MISSING_RISK",
            "WORD_COUNT_OUT_OF_RANGE",
            "SPEC_MISMATCH",
        ]
        text = build_retry_appendix(1, 3, codes, 25)
        for code in codes:
            assert code in text

    def test_word_count_low_message(self):
        text = build_retry_appendix(1, 3, ["WORD_COUNT_OUT_OF_RANGE"], 10)
        assert "increase" in text.lower()

    def test_word_count_high_message(self):
        text = build_retry_appendix(1, 3, ["WORD_COUNT_OUT_OF_RANGE"], 100)
        assert "reduce" in text.lower()


# ── Custom Word Count Limits ─────────────────────────────────────────────────


class TestCustomWordCountLimits:
    def test_custom_min_words_passes(self):
        narr = _make_narrative(full_description=" ".join(["word"] * 25))
        spec = _make_spec()
        result = validate(narr, spec, min_words=20, max_words=100)
        assert result.passed

    def test_custom_min_words_fails(self):
        narr = _make_narrative(full_description=" ".join(["word"] * 15))
        spec = _make_spec()
        result = validate(narr, spec, min_words=20, max_words=100)
        assert "WORD_COUNT_OUT_OF_RANGE" in result.failures

    def test_custom_max_words_passes(self):
        narr = _make_narrative(full_description=" ".join(["word"] * 90))
        spec = _make_spec()
        result = validate(narr, spec, min_words=20, max_words=100)
        assert "WORD_COUNT_OUT_OF_RANGE" not in result.failures

    def test_custom_max_words_fails(self):
        narr = _make_narrative(full_description=" ".join(["word"] * 110))
        spec = _make_spec()
        result = validate(narr, spec, min_words=20, max_words=100)
        assert "WORD_COUNT_OUT_OF_RANGE" in result.failures

    def test_default_params_unchanged(self):
        """Default call without custom params behaves the same as before."""
        narr = _make_narrative(full_description=" ".join(["word"] * 40))
        spec = _make_spec()
        result = validate(narr, spec)
        assert result.passed

    def test_retry_appendix_uses_custom_limits(self):
        text = build_retry_appendix(1, 3, ["WORD_COUNT_OUT_OF_RANGE"], 15, min_words=20, max_words=100)
        assert "20" in text
        assert "increase" in text.lower()
