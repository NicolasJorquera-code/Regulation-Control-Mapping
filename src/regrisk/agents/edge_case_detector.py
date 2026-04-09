"""
EdgeCaseDetector — deterministic rule-based detection of edge cases.

In a regulated compliance pipeline, edge case detection must be rule-based
and deterministic. The LLM resolves ambiguity — it does NOT define it.

Architecture (3-tier mapping system):
  Tier 1 — Deterministic: exact/keyword match, high confidence
  Tier 2 — Edge Case Detection (rules): weak match, ambiguous text, missing controls
  Tier 3 — LLM Resolution: semantic mapping, reasoning, explanation

Each detection result is fully explainable and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EdgeCaseReason(str, Enum):
    """Typed reasons for why something is flagged as an edge case."""

    NO_CANDIDATE_CONTROLS = "no_candidate_controls"
    LOW_KEYWORD_OVERLAP = "low_keyword_overlap"
    AMBIGUOUS_OBLIGATION_TEXT = "ambiguous_obligation_text"
    WEAK_STRUCTURAL_MATCH = "weak_structural_match"
    MULTIPLE_CONFLICTING_MATCHES = "multiple_conflicting_matches"
    CROSS_DOMAIN_MAPPING = "cross_domain_mapping"
    LOW_CONFIDENCE_MAPPING = "low_confidence_mapping"
    FREQUENCY_MISMATCH = "frequency_mismatch"
    RELATIONSHIP_TYPE_UNCLEAR = "relationship_type_unclear"


class ResolutionTier(str, Enum):
    """Which tier resolved the mapping/coverage."""

    DETERMINISTIC = "deterministic"
    EDGE_CASE_LLM = "edge_case_llm"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"


@dataclass(frozen=True)
class EdgeCaseResult:
    """Immutable result of edge case detection — fully auditable."""

    is_edge_case: bool
    reasons: tuple[EdgeCaseReason, ...] = ()
    tier: ResolutionTier = ResolutionTier.DETERMINISTIC
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_edge_case": self.is_edge_case,
            "reasons": [r.value for r in self.reasons],
            "tier": self.tier.value,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Thresholds (configurable via pipeline config)
# ---------------------------------------------------------------------------

_DEFAULT_THRESHOLDS = {
    "min_keyword_overlap": 2,
    "min_obligation_text_length": 20,
    "max_candidate_controls_for_conflict": 5,
    "low_confidence_cutoff": 0.5,
    "short_text_cutoff": 30,
}


# ---------------------------------------------------------------------------
# Core keyword sets for overlap detection
# ---------------------------------------------------------------------------

_CONTROL_KEYWORDS = frozenset({
    "control", "monitor", "review", "verify", "validate", "check",
    "enforce", "ensure", "maintain", "operate", "process", "system",
    "test", "audit", "inspect", "assess", "evaluate", "measure",
})

_OBLIGATION_ACTION_KEYWORDS = frozenset({
    "must", "shall", "require", "ensure", "maintain", "establish",
    "approve", "attest", "certify", "submit", "report", "disclose",
    "document", "record", "implement", "conduct", "perform", "review",
})

_FREQUENCY_KEYWORDS = frozenset({
    "annual", "annually", "quarterly", "monthly", "weekly", "daily",
    "periodic", "periodically", "semi-annual", "biennial",
})


class EdgeCaseDetector:
    """Rule-based edge case detector for obligation-to-control mapping.

    Rules decide edge cases → LLM resolves them.
    This class NEVER calls an LLM — it is purely deterministic.
    """

    def __init__(self, thresholds: dict[str, Any] | None = None) -> None:
        self.thresholds = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def detect_coverage_edge_case(
        self,
        obligation: dict[str, Any],
        candidate_controls: list[dict[str, Any]],
        mapping: dict[str, Any] | None = None,
    ) -> EdgeCaseResult:
        """Detect if a coverage assessment is an edge case.

        Parameters
        ----------
        obligation : dict
            The classified obligation (citation, abstract, category, etc.)
        candidate_controls : list[dict]
            Controls structurally matched to this obligation's APQC node.
        mapping : dict | None
            The APQC mapping for this obligation (if available).

        Returns
        -------
        EdgeCaseResult
            Immutable, auditable result with reasons and tier.
        """
        reasons: list[EdgeCaseReason] = []
        details: dict[str, Any] = {}

        # Rule 1: No candidate controls at all
        if not candidate_controls:
            reasons.append(EdgeCaseReason.NO_CANDIDATE_CONTROLS)
            details["candidate_count"] = 0

        # Rule 2: Obligation text too short / ambiguous
        abstract = obligation.get("abstract", "")
        if len(abstract.split()) < self.thresholds["min_obligation_text_length"]:
            reasons.append(EdgeCaseReason.AMBIGUOUS_OBLIGATION_TEXT)
            details["text_word_count"] = len(abstract.split())

        # Rule 3: Low keyword overlap between obligation and controls
        if candidate_controls:
            overlap = self._keyword_overlap(obligation, candidate_controls)
            details["keyword_overlap_score"] = overlap
            if overlap < self.thresholds["min_keyword_overlap"]:
                reasons.append(EdgeCaseReason.LOW_KEYWORD_OVERLAP)

        # Rule 4: Too many conflicting candidate controls
        if len(candidate_controls) > self.thresholds["max_candidate_controls_for_conflict"]:
            reasons.append(EdgeCaseReason.MULTIPLE_CONFLICTING_MATCHES)
            details["candidate_count"] = len(candidate_controls)

        # Rule 5: Weak structural match (control at higher APQC level only)
        if candidate_controls and mapping:
            apqc_id = mapping.get("apqc_hierarchy_id", "")
            exact_matches = sum(
                1 for c in candidate_controls
                if c.get("hierarchy_id", "") == apqc_id
            )
            if exact_matches == 0:
                reasons.append(EdgeCaseReason.WEAK_STRUCTURAL_MATCH)
                details["exact_apqc_matches"] = 0

        # Rule 6: Low confidence mapping
        if mapping:
            confidence = mapping.get("confidence", 1.0)
            details["mapping_confidence"] = confidence
            if confidence < self.thresholds["low_confidence_cutoff"]:
                reasons.append(EdgeCaseReason.LOW_CONFIDENCE_MAPPING)

        # Rule 7: Cross-domain mapping (obligation domain ≠ control domain)
        if candidate_controls and mapping:
            if self._is_cross_domain(obligation, candidate_controls, mapping):
                reasons.append(EdgeCaseReason.CROSS_DOMAIN_MAPPING)

        # Rule 8: Frequency mismatch
        if candidate_controls:
            if self._has_frequency_mismatch(obligation, candidate_controls):
                reasons.append(EdgeCaseReason.FREQUENCY_MISMATCH)
                details["frequency_mismatch"] = True

        # Rule 9: Relationship type unclear
        rel_type = obligation.get("relationship_type", "")
        if rel_type in ("N/A", "", None) and obligation.get("obligation_category") in (
            "Controls", "Documentation", "Attestation"
        ):
            reasons.append(EdgeCaseReason.RELATIONSHIP_TYPE_UNCLEAR)

        is_edge = len(reasons) > 0
        tier = ResolutionTier.EDGE_CASE_LLM if is_edge else ResolutionTier.DETERMINISTIC

        return EdgeCaseResult(
            is_edge_case=is_edge,
            reasons=tuple(reasons),
            tier=tier,
            details=details,
        )

    def detect_mapping_edge_case(
        self,
        obligation: dict[str, Any],
        mappings: list[dict[str, Any]],
    ) -> EdgeCaseResult:
        """Detect if an APQC mapping result is an edge case.

        Parameters
        ----------
        obligation : dict
            The classified obligation.
        mappings : list[dict]
            APQC mappings produced for this obligation.
        """
        reasons: list[EdgeCaseReason] = []
        details: dict[str, Any] = {}

        if not mappings:
            reasons.append(EdgeCaseReason.NO_CANDIDATE_CONTROLS)
            details["mapping_count"] = 0
            return EdgeCaseResult(
                is_edge_case=True,
                reasons=tuple(reasons),
                tier=ResolutionTier.EDGE_CASE_LLM,
                details=details,
            )

        # All mappings low confidence
        confidences = [m.get("confidence", 0.0) for m in mappings]
        avg_confidence = sum(confidences) / len(confidences)
        details["avg_mapping_confidence"] = round(avg_confidence, 3)

        if all(c < self.thresholds["low_confidence_cutoff"] for c in confidences):
            reasons.append(EdgeCaseReason.LOW_CONFIDENCE_MAPPING)

        # Ambiguous text
        abstract = obligation.get("abstract", "")
        if len(abstract.split()) < self.thresholds["min_obligation_text_length"]:
            reasons.append(EdgeCaseReason.AMBIGUOUS_OBLIGATION_TEXT)
            details["text_word_count"] = len(abstract.split())

        is_edge = len(reasons) > 0
        tier = ResolutionTier.EDGE_CASE_LLM if is_edge else ResolutionTier.DETERMINISTIC

        return EdgeCaseResult(
            is_edge_case=is_edge,
            reasons=tuple(reasons),
            tier=tier,
            details=details,
        )

    # ------------------------------------------------------------------
    # Internal rule helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _keyword_overlap(
        obligation: dict[str, Any],
        controls: list[dict[str, Any]],
    ) -> int:
        """Count how many action/control keywords appear in both obligation and controls."""
        ob_text = f"{obligation.get('abstract', '')} {obligation.get('section_title', '')}".lower()
        ob_words = set(ob_text.split())
        ob_keywords = ob_words & (_CONTROL_KEYWORDS | _OBLIGATION_ACTION_KEYWORDS)

        ctrl_text = " ".join(
            f"{c.get('full_description', '')} {c.get('what', '')} {c.get('why', '')}"
            for c in controls
        ).lower()
        ctrl_words = set(ctrl_text.split())
        ctrl_keywords = ctrl_words & (_CONTROL_KEYWORDS | _OBLIGATION_ACTION_KEYWORDS)

        return len(ob_keywords & ctrl_keywords)

    @staticmethod
    def _is_cross_domain(
        obligation: dict[str, Any],
        controls: list[dict[str, Any]],
        mapping: dict[str, Any],
    ) -> bool:
        """Check if obligation maps to a different APQC top-level domain than controls."""
        apqc_id = mapping.get("apqc_hierarchy_id", "")
        ob_domain = apqc_id.split(".")[0] if apqc_id else ""

        ctrl_domains = set()
        for c in controls:
            hid = c.get("hierarchy_id", "")
            if hid:
                ctrl_domains.add(hid.split(".")[0])

        return bool(ob_domain and ctrl_domains and ob_domain not in ctrl_domains)

    @staticmethod
    def _has_frequency_mismatch(
        obligation: dict[str, Any],
        controls: list[dict[str, Any]],
    ) -> bool:
        """Check if obligation specifies a frequency not met by any candidate control."""
        ob_text = obligation.get("abstract", "").lower()
        ob_freqs = _FREQUENCY_KEYWORDS & set(ob_text.split())

        if not ob_freqs:
            return False

        ctrl_freqs: set[str] = set()
        for c in controls:
            freq_text = f"{c.get('frequency', '')} {c.get('when', '')}".lower()
            ctrl_freqs |= _FREQUENCY_KEYWORDS & set(freq_text.split())

        # If obligation mentions frequency but no control does → mismatch
        return len(ctrl_freqs) == 0
