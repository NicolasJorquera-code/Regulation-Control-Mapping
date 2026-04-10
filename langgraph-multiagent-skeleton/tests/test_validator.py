"""Tests for the deterministic validator."""

from __future__ import annotations

from skeleton.validation.validator import ValidationResult, validate_summary


def test_valid_summary_passes():
    summary = {
        "text": " ".join(["word"] * 70),
        "sources_used": ["https://example.com"],
    }
    result = validate_summary(summary, min_words=50, max_words=300)
    assert result.passed is True
    assert result.failures == []
    assert result.metrics["word_count"] == 70


def test_too_short_fails():
    summary = {"text": "Short.", "sources_used": ["https://example.com"]}
    result = validate_summary(summary, min_words=50, max_words=300)
    assert result.passed is False
    assert "TOO_SHORT" in result.failures


def test_too_long_fails():
    summary = {
        "text": " ".join(["word"] * 500),
        "sources_used": ["https://example.com"],
    }
    result = validate_summary(summary, min_words=50, max_words=300)
    assert result.passed is False
    assert "TOO_LONG" in result.failures


def test_missing_sources_fails():
    summary = {
        "text": " ".join(["word"] * 70),
        "sources_used": [],
    }
    result = validate_summary(summary, min_words=50, max_words=300)
    assert result.passed is False
    assert "SOURCES_MISSING" in result.failures


def test_multiple_failures():
    summary = {"text": "Short.", "sources_used": []}
    result = validate_summary(summary, min_words=50, max_words=300)
    assert result.passed is False
    assert "TOO_SHORT" in result.failures
    assert "SOURCES_MISSING" in result.failures


def test_result_is_frozen():
    result = ValidationResult(passed=True, failures=[], metrics={"word_count": 100})
    assert result.passed is True
    # frozen=True means attributes can't be reassigned
    try:
        result.passed = False  # type: ignore
        assert False, "Should have raised"
    except AttributeError:
        pass
