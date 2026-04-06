"""
Deterministic validator with typed failure codes.

Validates pipeline artifacts at each stage without calling an LLM.
Each rule produces a specific failure code for targeted feedback.
"""

from __future__ import annotations

VALID_CATEGORIES = {"Attestation", "Documentation", "Controls", "General Awareness", "Not Assigned"}
VALID_RELATIONSHIP_TYPES = {"Requires Existence", "Constrains Execution", "Requires Evidence", "Sets Frequency", "N/A"}
VALID_COVERAGE_STATUSES = {"Covered", "Partially Covered", "Not Covered"}
VALID_SEMANTIC_MATCHES = {"Full", "Partial", "None"}
VALID_RELATIONSHIP_MATCHES = {"Satisfied", "Partial", "Not Satisfied"}


def validate_classification(c: dict) -> tuple[bool, list[str]]:
    """Validate a classification dict."""
    failures: list[str] = []

    if c.get("obligation_category") not in VALID_CATEGORIES:
        failures.append("INVALID_CATEGORY")

    if c.get("obligation_category") in {"Controls", "Documentation", "Attestation"}:
        if c.get("relationship_type") not in (VALID_RELATIONSHIP_TYPES - {"N/A"}):
            failures.append("MISSING_RELATIONSHIP_TYPE")
    elif c.get("obligation_category") in {"General Awareness", "Not Assigned"}:
        if c.get("relationship_type") not in {"N/A", "", None}:
            # Warn but don't fail — just note it
            pass

    if c.get("criticality_tier") not in {"High", "Medium", "Low"}:
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


def derive_inherent_rating(impact: int, frequency: int) -> str:
    """Derive inherent risk rating from impact × frequency."""
    score = impact * frequency
    if score >= 12:
        return "Critical"
    if score >= 8:
        return "High"
    if score >= 4:
        return "Medium"
    return "Low"
