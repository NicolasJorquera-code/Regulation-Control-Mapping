"""
Deterministic validator with typed failure codes.

Validates pipeline artifacts at each stage without calling an LLM.
Each rule produces a specific failure code for targeted feedback.
"""

from __future__ import annotations

from regrisk.core.constants import (
    OBLIGATION_CATEGORIES,
    RELATIONSHIP_TYPES,
    COVERAGE_STATUSES,
    SEMANTIC_MATCHES,
    RELATIONSHIP_MATCHES,
    CRITICALITY_TIERS,
    REL_NA,
    ACTIONABLE_CATEGORIES,
)

# Re-export from core.scoring so existing callers keep working.
from regrisk.core.scoring import derive_inherent_rating  # noqa: F401

VALID_CATEGORIES = OBLIGATION_CATEGORIES
VALID_RELATIONSHIP_TYPES = RELATIONSHIP_TYPES
VALID_COVERAGE_STATUSES = COVERAGE_STATUSES
VALID_SEMANTIC_MATCHES = SEMANTIC_MATCHES
VALID_RELATIONSHIP_MATCHES = RELATIONSHIP_MATCHES


def validate_classification(c: dict) -> tuple[bool, list[str]]:
    """Validate a classification dict."""
    failures: list[str] = []

    if c.get("obligation_category") not in VALID_CATEGORIES:
        failures.append("INVALID_CATEGORY")

    if c.get("obligation_category") in ACTIONABLE_CATEGORIES:
        if c.get("relationship_type") not in (VALID_RELATIONSHIP_TYPES - {REL_NA}):
            failures.append("MISSING_RELATIONSHIP_TYPE")
    elif c.get("obligation_category") in (OBLIGATION_CATEGORIES - ACTIONABLE_CATEGORIES):
        if c.get("relationship_type") not in {REL_NA, "", None}:
            # Warn but don't fail — just note it
            pass

    if c.get("criticality_tier") not in CRITICALITY_TIERS:
        failures.append("INVALID_CRITICALITY")

    if not c.get("citation"):
        failures.append("MISSING_CITATION")

    return (len(failures) == 0, failures)


def validate_mapping(m: dict) -> tuple[bool, list[str]]:
    """Validate a mapping dict."""
    failures: list[str] = []

    if not m.get("apqc_hierarchy_id"):
        failures.append("MISSING_APQC_ID")

    if not m.get("relationship_detail"):
        failures.append("MISSING_RELATIONSHIP_DETAIL")

    confidence = m.get("confidence", 0)
    try:
        conf_val = float(confidence)
        if not (0.0 <= conf_val <= 1.0):
            failures.append("INVALID_CONFIDENCE")
    except (TypeError, ValueError):
        failures.append("INVALID_CONFIDENCE")

    if not m.get("citation"):
        failures.append("MISSING_CITATION")

    return (len(failures) == 0, failures)


def validate_coverage(a: dict) -> tuple[bool, list[str]]:
    """Validate a coverage assessment dict."""
    failures: list[str] = []

    if a.get("overall_coverage") not in VALID_COVERAGE_STATUSES:
        failures.append("INVALID_COVERAGE_STATUS")

    if a.get("semantic_match") not in VALID_SEMANTIC_MATCHES:
        failures.append("INVALID_SEMANTIC_MATCH")

    return (len(failures) == 0, failures)


def validate_risk(r: dict) -> tuple[bool, list[str]]:
    """Validate a risk dict."""
    failures: list[str] = []

    desc = r.get("risk_description", "")
    words = len(desc.split())
    if words < 20 or words > 60:
        failures.append(f"WORD_COUNT ({words})")

    for field_name in ("impact_rating", "frequency_rating"):
        val = r.get(field_name, 0)
        try:
            int_val = int(val)
            if not (1 <= int_val <= 4):
                failures.append(f"INVALID_{field_name.upper()} ({val})")
        except (TypeError, ValueError):
            failures.append(f"INVALID_{field_name.upper()} ({val})")

    return (len(failures) == 0, failures)
