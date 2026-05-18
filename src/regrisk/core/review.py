"""
AI Governance -- Needs-Review derivation.

Pure-Python rules table run AFTER each LLM-produced artifact. Every
``needs_review`` flag and ``needs_review_reasons`` list in the system is
emitted by this module -- no LLM judges itself, so reviews stay auditable.

See the design plan (section 12) for the rule catalogue. Rules are
rule-based, dependency-free, and idempotent: re-running on the same
input produces the same flags.

Inputs are accepted as plain ``dict`` (matching the LangGraph state shape)
rather than Pydantic models, so the caller can use the same function on
serialized checkpoint JSON without rehydrating.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from regrisk.core.constants import (
    CATEGORY_NOT_ASSIGNED,
    COVERAGE_NOT_COVERED,
    COVERAGE_PARTIALLY_COVERED,
    INTERNAL_SOURCE_TYPES,
    REL_REQUIRES_EVIDENCE,
    REVIEW_AMBIGUOUS_CONTROL_OWNER,
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
    SOURCE_TYPE_PROCEDURE_STEP,
    SOURCE_TYPE_REGULATORY_OBLIGATION,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _parse_date(value: Any) -> date | None:
    """Parse a date-like value into a ``date`` or return ``None``."""
    if value in (None, "", 0):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _source_metadata(source: dict[str, Any]) -> dict[str, Any]:
    md = source.get("source_metadata") or {}
    return md if isinstance(md, dict) else {}


# ── Per-artifact rule functions ───────────────────────────────────────────

def review_source(source: dict[str, Any], today: date | None = None) -> list[str]:
    """Reasons that attach to the SOURCE row itself (lifecycle, owner, etc.).

    Returned reasons are propagated onto each downstream artifact derived
    from this source so the Needs Review Queue is self-explanatory.
    """
    today = today or date.today()
    reasons: list[str] = []
    source_type = source.get("source_type") or SOURCE_TYPE_REGULATORY_OBLIGATION
    md = _source_metadata(source)

    # Rule 1: missing owner on a non-regulatory source
    owner = md.get("source_owner") or source.get("source_owner")
    if source_type in INTERNAL_SOURCE_TYPES and not (owner or "").strip():
        reasons.append(REVIEW_MISSING_SOURCE_OWNER)

    # Rule 6: lifecycle breach
    eff = _parse_date(source.get("effective_date"))
    rev = _parse_date(md.get("review_date"))
    if eff and eff > today:
        reasons.append(REVIEW_POLICY_LIFECYCLE_BREACH)
    if rev and rev < today and REVIEW_POLICY_LIFECYCLE_BREACH not in reasons:
        reasons.append(REVIEW_POLICY_LIFECYCLE_BREACH)

    # Rule 7: orphan procedure
    if source_type == SOURCE_TYPE_PROCEDURE_STEP and not (source.get("parent_source_id") or "").strip():
        reasons.append(REVIEW_ORPHAN_PROCEDURE)

    # Rule 13: low extraction confidence
    sc = source.get("source_confidence")
    if isinstance(sc, (int, float)) and sc < 0.7:
        reasons.append(REVIEW_LOW_EXTRACTION_CONFIDENCE)

    return reasons


def review_classification(classification: dict[str, Any]) -> list[str]:
    """Reasons specific to a classification artifact."""
    reasons: list[str] = []
    # Rule 14: unclassified
    if classification.get("obligation_category") == CATEGORY_NOT_ASSIGNED:
        reasons.append(REVIEW_UNCLASSIFIED_REQUIREMENT)
    return reasons


def review_mapping(
    mapping: dict[str, Any],
    *,
    fanout: int = 1,
    source: dict[str, Any] | None = None,
) -> list[str]:
    """Reasons specific to one APQC mapping.

    ``fanout`` is the total mapping count for the same source_id (used for
    the excessive-fanout rule).
    """
    reasons: list[str] = []
    # Rule 2: low mapping confidence
    conf = mapping.get("confidence")
    if isinstance(conf, (int, float)) and conf < 0.5:
        reasons.append(REVIEW_LOW_MAPPING_CONFIDENCE)

    # Rule 3: excessive fanout
    if fanout > 3:
        reasons.append(REVIEW_EXCESSIVE_MAPPING_FANOUT)

    # Rule 11: weak regulatory traceability (policy claims a regulation link
    # but the mapper produced low confidence)
    if source is not None:
        md = _source_metadata(source)
        reg_links = md.get("regulation_links") or []
        if reg_links and isinstance(conf, (int, float)) and conf < 0.6:
            reasons.append(REVIEW_WEAK_REGULATORY_TRACEABILITY)

    return reasons


def review_coverage(
    assessment: dict[str, Any],
    *,
    classification: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    has_improvement_proposal: bool = False,
) -> list[str]:
    """Reasons specific to one coverage assessment."""
    reasons: list[str] = []
    coverage = assessment.get("overall_coverage")

    # Rule 4
    if coverage == COVERAGE_PARTIALLY_COVERED:
        reasons.append(REVIEW_COVERAGE_PARTIAL)

    # Rule 5: pending control generation for policy-led gaps
    source_type = (source or {}).get("source_type") or assessment.get("source_type")
    if (
        coverage == COVERAGE_NOT_COVERED
        and source_type in INTERNAL_SOURCE_TYPES
        and not has_improvement_proposal
    ):
        reasons.append(REVIEW_PENDING_CONTROL_GENERATION)

    # Rule 9: missing evidence artifact when the requirement asks for it
    if classification is not None and classification.get("relationship_type") == REL_REQUIRES_EVIDENCE:
        md = _source_metadata(source or {})
        evidence_ref = md.get("evidence_reference") or assessment.get("evidence_reference")
        if not (evidence_ref or "").strip():
            reasons.append(REVIEW_MISSING_EVIDENCE_ARTIFACT)

    return reasons


def review_risk(risk: dict[str, Any]) -> list[str]:
    """Reasons specific to one scored risk."""
    reasons: list[str] = []
    # Rule 10: critical residual risk
    if (
        risk.get("inherent_risk_rating") == RISK_CRITICAL
        and risk.get("coverage_status") == COVERAGE_NOT_COVERED
    ):
        reasons.append(REVIEW_CRITICAL_RESIDUAL_RISK)
    return reasons


# ── Procedure / Policy contradiction (group-level) ───────────────────────

def review_procedure_contradictions(
    classifications: list[dict[str, Any]],
    sources_by_id: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    """Flag procedures whose ``relationship_type`` contradicts their parent policy.

    Returns ``{source_id: [reasons]}``. A contradiction is detected when a
    procedure's relationship type is present in a different relationship
    family than its parent policy's relationship type AND the parent has a
    non-N/A type.
    """
    by_citation = {c.get("citation"): c for c in classifications}
    out: dict[str, list[str]] = {}
    for c in classifications:
        cit = c.get("citation")
        src = sources_by_id.get(cit, {})
        if src.get("source_type") != SOURCE_TYPE_PROCEDURE_STEP:
            continue
        parent_id = src.get("parent_source_id")
        if not parent_id:
            continue
        parent_class = by_citation.get(parent_id)
        if not parent_class:
            continue
        p_rel = parent_class.get("relationship_type")
        c_rel = c.get("relationship_type")
        if p_rel and p_rel != "N/A" and c_rel and c_rel != "N/A" and p_rel != c_rel:
            out.setdefault(cit, []).append(REVIEW_PROCEDURE_CONTRADICTS_POLICY)
    return out


# ── Convenience aggregator ────────────────────────────────────────────────

def merge_reasons(*lists: list[str]) -> list[str]:
    """De-duplicate while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for r in lst or []:
            if r not in seen:
                seen.add(r)
                out.append(r)
    return out


def annotate_artifact(artifact: dict[str, Any], reasons: list[str]) -> dict[str, Any]:
    """Stamp ``needs_review`` / ``needs_review_reasons`` on a dict artifact.

    Idempotent: if the artifact already has reasons, they are merged.
    """
    existing = artifact.get("needs_review_reasons") or []
    merged = merge_reasons(existing, reasons)
    artifact["needs_review_reasons"] = merged
    artifact["needs_review"] = bool(merged)
    return artifact


__all__ = [
    "review_source",
    "review_classification",
    "review_mapping",
    "review_coverage",
    "review_risk",
    "review_procedure_contradictions",
    "merge_reasons",
    "annotate_artifact",
]


# Rule 8 (ambiguous control owner) and rule 12 are emitted by the metadata
# enrichment / control-improver layer, where multiple owner candidates are
# resolved. Exposed for callers to import the constant from this module.
AMBIGUOUS_CONTROL_OWNER = REVIEW_AMBIGUOUS_CONTROL_OWNER
