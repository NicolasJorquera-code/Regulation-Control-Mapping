"""
Tests for the validation module.
"""

from __future__ import annotations

import pytest

from regrisk.validation.validator import (
    derive_inherent_rating,
    validate_classification,
    validate_coverage,
    validate_mapping,
    validate_risk,
)


class TestValidateClassification:
    def test_valid_controls_classification(self):
        c = {
            "citation": "12 CFR 252.34(a)",
            "obligation_category": "Controls",
            "relationship_type": "Constrains Execution",
            "criticality_tier": "High",
        }
        passed, failures = validate_classification(c)
        assert passed is True
        assert failures == []

    def test_valid_general_awareness(self):
        c = {
            "citation": "12 CFR 252.31",
            "obligation_category": "General Awareness",
            "relationship_type": "N/A",
            "criticality_tier": "Low",
        }
        passed, failures = validate_classification(c)
        assert passed is True

    def test_invalid_category(self):
        c = {
            "citation": "test",
            "obligation_category": "InvalidCategory",
            "relationship_type": "N/A",
            "criticality_tier": "Low",
        }
        passed, failures = validate_classification(c)
        assert passed is False
        assert "INVALID_CATEGORY" in failures

    def test_missing_relationship_type_for_controls(self):
        c = {
            "citation": "test",
            "obligation_category": "Controls",
            "relationship_type": "N/A",
            "criticality_tier": "High",
        }
        passed, failures = validate_classification(c)
        assert passed is False
        assert "MISSING_RELATIONSHIP_TYPE" in failures

    def test_invalid_criticality(self):
        c = {
            "citation": "test",
            "obligation_category": "Not Assigned",
            "relationship_type": "N/A",
            "criticality_tier": "Critical",  # not valid
        }
        passed, failures = validate_classification(c)
        assert passed is False
        assert "INVALID_CRITICALITY" in failures

    def test_missing_citation(self):
        c = {
            "citation": "",
            "obligation_category": "Controls",
            "relationship_type": "Constrains Execution",
            "criticality_tier": "Medium",
        }
        passed, failures = validate_classification(c)
        assert passed is False
        assert "MISSING_CITATION" in failures


class TestValidateMapping:
    def test_valid_mapping(self):
        m = {
            "citation": "12 CFR 252.34(a)",
            "apqc_hierarchy_id": "11.1.1",
            "relationship_detail": "Requires board approval of risk appetite",
            "confidence": 0.85,
        }
        passed, failures = validate_mapping(m)
        assert passed is True

    def test_missing_apqc_id(self):
        m = {
            "citation": "test",
            "apqc_hierarchy_id": "",
            "relationship_detail": "test",
            "confidence": 0.5,
        }
        passed, failures = validate_mapping(m)
        assert passed is False
        assert "MISSING_APQC_ID" in failures

    def test_invalid_confidence(self):
        m = {
            "citation": "test",
            "apqc_hierarchy_id": "11.1.1",
            "relationship_detail": "test",
            "confidence": 1.5,  # out of range
        }
        passed, failures = validate_mapping(m)
        assert passed is False
        assert "INVALID_CONFIDENCE" in failures

    def test_missing_relationship_detail(self):
        m = {
            "citation": "test",
            "apqc_hierarchy_id": "11.1.1",
            "relationship_detail": "",
            "confidence": 0.5,
        }
        passed, failures = validate_mapping(m)
        assert passed is False
        assert "MISSING_RELATIONSHIP_DETAIL" in failures


class TestValidateCoverage:
    def test_valid_covered(self):
        a = {
            "overall_coverage": "Covered",
            "semantic_match": "Full",
        }
        passed, failures = validate_coverage(a)
        assert passed is True

    def test_invalid_coverage_status(self):
        a = {
            "overall_coverage": "Maybe",
            "semantic_match": "Full",
        }
        passed, failures = validate_coverage(a)
        assert passed is False
        assert "INVALID_COVERAGE_STATUS" in failures

    def test_invalid_semantic_match(self):
        a = {
            "overall_coverage": "Covered",
            "semantic_match": "Maybe",
        }
        passed, failures = validate_coverage(a)
        assert passed is False
        assert "INVALID_SEMANTIC_MATCH" in failures


class TestValidateRisk:
    def test_valid_risk(self):
        r = {
            "risk_description": " ".join(["word"] * 30),  # 30 words
            "impact_rating": 3,
            "frequency_rating": 2,
        }
        passed, failures = validate_risk(r)
        assert passed is True

    def test_too_short_description(self):
        r = {
            "risk_description": "Too short",
            "impact_rating": 3,
            "frequency_rating": 2,
        }
        passed, failures = validate_risk(r)
        assert passed is False
        assert any("WORD_COUNT" in f for f in failures)

    def test_too_long_description(self):
        r = {
            "risk_description": " ".join(["word"] * 65),  # 65 words
            "impact_rating": 3,
            "frequency_rating": 2,
        }
        passed, failures = validate_risk(r)
        assert passed is False
        assert any("WORD_COUNT" in f for f in failures)

    def test_invalid_impact_rating(self):
        r = {
            "risk_description": " ".join(["word"] * 30),
            "impact_rating": 5,  # out of range
            "frequency_rating": 2,
        }
        passed, failures = validate_risk(r)
        assert passed is False
        assert any("IMPACT_RATING" in f for f in failures)

    def test_invalid_frequency_rating(self):
        r = {
            "risk_description": " ".join(["word"] * 30),
            "impact_rating": 2,
            "frequency_rating": 0,  # out of range
        }
        passed, failures = validate_risk(r)
        assert passed is False
        assert any("FREQUENCY_RATING" in f for f in failures)


class TestDeriveInherentRating:
    def test_critical(self):
        assert derive_inherent_rating(4, 3) == "Critical"
        assert derive_inherent_rating(3, 4) == "Critical"
        assert derive_inherent_rating(4, 4) == "Critical"

    def test_high(self):
        assert derive_inherent_rating(4, 2) == "High"
        assert derive_inherent_rating(2, 4) == "High"

    def test_medium(self):
        assert derive_inherent_rating(2, 2) == "Medium"
        assert derive_inherent_rating(4, 1) == "Medium"
        assert derive_inherent_rating(1, 4) == "Medium"

    def test_low(self):
        assert derive_inherent_rating(1, 1) == "Low"
        assert derive_inherent_rating(1, 2) == "Low"
        assert derive_inherent_rating(1, 3) == "Low"
