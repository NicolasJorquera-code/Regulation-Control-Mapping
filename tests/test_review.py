"""
Tests for the deterministic Needs-Review derivation (Phase 4 hybrid model).
"""

from __future__ import annotations

from datetime import date

from regrisk.core import review
from regrisk.core.constants import (
    CATEGORY_NOT_ASSIGNED,
    COVERAGE_NOT_COVERED,
    COVERAGE_PARTIALLY_COVERED,
    REL_REQUIRES_EVIDENCE,
    REVIEW_COVERAGE_PARTIAL,
    REVIEW_CRITICAL_RESIDUAL_RISK,
    REVIEW_EXCESSIVE_MAPPING_FANOUT,
    REVIEW_LOW_EXTRACTION_CONFIDENCE,
    REVIEW_LOW_MAPPING_CONFIDENCE,
    REVIEW_MISSING_EVIDENCE_ARTIFACT,
    REVIEW_MISSING_SOURCE_OWNER,
    REVIEW_ORPHAN_PROCEDURE,
    REVIEW_PENDING_CONTROL_GENERATION,
    REVIEW_POLICY_LIFECYCLE_BREACH,
    REVIEW_PROCEDURE_CONTRADICTS_POLICY,
    REVIEW_UNCLASSIFIED_REQUIREMENT,
    REVIEW_WEAK_REGULATORY_TRACEABILITY,
    RISK_CRITICAL,
    SOURCE_TYPE_POLICY_REQUIREMENT,
    SOURCE_TYPE_PROCEDURE_STEP,
    SOURCE_TYPE_REGULATORY_OBLIGATION,
)


TODAY = date(2026, 4, 28)


# ── review_source ─────────────────────────────────────────────────────────

def test_regulatory_source_with_no_owner_is_not_flagged():
    src = {
        "source_type": SOURCE_TYPE_REGULATORY_OBLIGATION,
        "source_metadata": {},
    }
    assert review.review_source(src, today=TODAY) == []


def test_policy_with_missing_owner_is_flagged():
    src = {
        "source_type": SOURCE_TYPE_POLICY_REQUIREMENT,
        "source_metadata": {"source_owner": ""},
    }
    assert REVIEW_MISSING_SOURCE_OWNER in review.review_source(src, today=TODAY)


def test_orphan_procedure_is_flagged():
    src = {
        "source_type": SOURCE_TYPE_PROCEDURE_STEP,
        "parent_source_id": "",
        "source_metadata": {"source_owner": "MLRO"},
    }
    assert REVIEW_ORPHAN_PROCEDURE in review.review_source(src, today=TODAY)


def test_expired_review_date_is_lifecycle_breach():
    src = {
        "source_type": SOURCE_TYPE_POLICY_REQUIREMENT,
        "effective_date": "2020-01-01",
        "source_metadata": {"source_owner": "CRO", "review_date": "2025-01-01"},
    }
    assert REVIEW_POLICY_LIFECYCLE_BREACH in review.review_source(src, today=TODAY)


def test_future_effective_date_is_lifecycle_breach():
    src = {
        "source_type": SOURCE_TYPE_POLICY_REQUIREMENT,
        "effective_date": "2027-01-01",
        "source_metadata": {"source_owner": "CRO"},
    }
    assert REVIEW_POLICY_LIFECYCLE_BREACH in review.review_source(src, today=TODAY)


def test_low_extraction_confidence_is_flagged():
    src = {"source_type": SOURCE_TYPE_REGULATORY_OBLIGATION, "source_confidence": 0.4}
    assert REVIEW_LOW_EXTRACTION_CONFIDENCE in review.review_source(src, today=TODAY)


# ── review_classification ────────────────────────────────────────────────

def test_unclassified_category_is_flagged():
    cls = {"obligation_category": CATEGORY_NOT_ASSIGNED}
    assert review.review_classification(cls) == [REVIEW_UNCLASSIFIED_REQUIREMENT]


def test_classified_category_is_clean():
    cls = {"obligation_category": "Controls"}
    assert review.review_classification(cls) == []


# ── review_mapping ────────────────────────────────────────────────────────

def test_low_confidence_mapping_is_flagged():
    m = {"confidence": 0.3}
    assert REVIEW_LOW_MAPPING_CONFIDENCE in review.review_mapping(m)


def test_high_confidence_mapping_is_clean():
    m = {"confidence": 0.9}
    assert review.review_mapping(m) == []


def test_excessive_fanout_is_flagged():
    m = {"confidence": 0.9}
    assert REVIEW_EXCESSIVE_MAPPING_FANOUT in review.review_mapping(m, fanout=5)


def test_weak_regulatory_traceability_for_policy_with_low_conf_link():
    src = {"source_metadata": {"regulation_links": ["12 CFR 252.34"]}}
    m = {"confidence": 0.4}
    reasons = review.review_mapping(m, source=src)
    assert REVIEW_WEAK_REGULATORY_TRACEABILITY in reasons


# ── review_coverage ──────────────────────────────────────────────────────

def test_partial_coverage_is_flagged():
    a = {"overall_coverage": COVERAGE_PARTIALLY_COVERED}
    assert REVIEW_COVERAGE_PARTIAL in review.review_coverage(a)


def test_policy_not_covered_pending_control_generation():
    a = {"overall_coverage": COVERAGE_NOT_COVERED}
    src = {"source_type": SOURCE_TYPE_POLICY_REQUIREMENT}
    reasons = review.review_coverage(a, source=src, has_improvement_proposal=False)
    assert REVIEW_PENDING_CONTROL_GENERATION in reasons


def test_policy_not_covered_with_proposal_is_clear():
    a = {"overall_coverage": COVERAGE_NOT_COVERED}
    src = {"source_type": SOURCE_TYPE_POLICY_REQUIREMENT}
    reasons = review.review_coverage(a, source=src, has_improvement_proposal=True)
    assert REVIEW_PENDING_CONTROL_GENERATION not in reasons


def test_regulation_not_covered_does_not_pend_generation():
    a = {"overall_coverage": COVERAGE_NOT_COVERED}
    src = {"source_type": SOURCE_TYPE_REGULATORY_OBLIGATION}
    reasons = review.review_coverage(a, source=src, has_improvement_proposal=False)
    assert REVIEW_PENDING_CONTROL_GENERATION not in reasons


def test_missing_evidence_when_classification_requires_evidence():
    a = {"overall_coverage": "Covered"}
    cls = {"relationship_type": REL_REQUIRES_EVIDENCE}
    src = {"source_metadata": {"evidence_reference": ""}}
    reasons = review.review_coverage(a, classification=cls, source=src)
    assert REVIEW_MISSING_EVIDENCE_ARTIFACT in reasons


# ── review_risk ──────────────────────────────────────────────────────────

def test_critical_residual_risk_is_flagged():
    r = {"inherent_risk_rating": RISK_CRITICAL, "coverage_status": COVERAGE_NOT_COVERED}
    assert REVIEW_CRITICAL_RESIDUAL_RISK in review.review_risk(r)


def test_critical_but_covered_is_not_flagged():
    r = {"inherent_risk_rating": RISK_CRITICAL, "coverage_status": "Covered"}
    assert review.review_risk(r) == []


# ── procedure / policy contradiction ─────────────────────────────────────

def test_procedure_contradicts_policy_relationship_type():
    sources = {
        "POL-AML-022": {
            "source_type": SOURCE_TYPE_POLICY_REQUIREMENT,
            "parent_source_id": None,
        },
        "POL-AML-022.P1": {
            "source_type": SOURCE_TYPE_PROCEDURE_STEP,
            "parent_source_id": "POL-AML-022",
        },
    }
    classifications = [
        {"citation": "POL-AML-022", "relationship_type": "Requires Evidence"},
        {"citation": "POL-AML-022.P1", "relationship_type": "Sets Frequency"},
    ]
    result = review.review_procedure_contradictions(classifications, sources)
    assert result["POL-AML-022.P1"] == [REVIEW_PROCEDURE_CONTRADICTS_POLICY]


# ── annotate / merge ─────────────────────────────────────────────────────

def test_merge_reasons_dedupes_preserving_order():
    out = review.merge_reasons(["a", "b"], ["b", "c"], ["a", "d"])
    assert out == ["a", "b", "c", "d"]


def test_annotate_artifact_idempotent():
    art = {"foo": 1}
    review.annotate_artifact(art, ["x"])
    review.annotate_artifact(art, ["x", "y"])
    assert art["needs_review"] is True
    assert art["needs_review_reasons"] == ["x", "y"]


def test_annotate_artifact_no_reasons_clears_flag():
    art = {"foo": 1}
    review.annotate_artifact(art, [])
    assert art["needs_review"] is False
    assert art["needs_review_reasons"] == []
