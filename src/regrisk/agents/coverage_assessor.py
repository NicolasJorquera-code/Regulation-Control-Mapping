"""
CoverageAssessorAgent — evaluates whether controls cover mapped obligations.

Uses a 3-tier resolution system:
  Tier 1 — Deterministic: strong structural + keyword match → no LLM needed.
  Tier 2 — Edge Case Detection: rules flag ambiguity → LLM resolves.
  Tier 3 — Deterministic Fallback: edge case but no LLM → conservative default.

Edge case detection is ALWAYS rule-based. LLM resolves ambiguity — never defines it.
"""

from __future__ import annotations

import logging
from typing import Any

from regrisk.agents.base import AgentContext, BaseAgent, register_agent
from regrisk.agents.edge_case_detector import (
    EdgeCaseDetector,
    EdgeCaseResult,
    ResolutionTier,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are evaluating whether existing internal controls adequately cover a specific regulatory obligation.

This is an EDGE CASE that could not be resolved deterministically. The reasons are provided below.

EVALUATION LAYERS:

Layer 1 — STRUCTURAL MATCH (already completed, provided below):
Controls were found at APQC hierarchy nodes that overlap with the obligation's mapped processes.

Layer 2 — SEMANTIC MATCH:
Does the control's description, purpose ('why' field), and action ('what' field) substantively address what the obligation requires?
Rate: "Full" (directly addresses), "Partial" (related but incomplete), "None" (unrelated despite structural match)

Layer 3 — RELATIONSHIP TYPE MATCH:
The obligation has a specific relationship type. Does the control satisfy it?
- If "Requires Existence": Does the control demonstrate the required function/role/committee exists?
- If "Constrains Execution": Does the control enforce the specific constraint (e.g., board approval, independence)?
- If "Requires Evidence": Does the control produce the required documentation/reports?
- If "Sets Frequency": Does the control operate at the required frequency or more often?
Rate: "Satisfied" | "Partial" | "Not Satisfied"

OVERALL COVERAGE:
- "Covered": Semantic=Full AND Relationship=Satisfied
- "Partially Covered": Semantic=Partial OR Relationship=Partial
- "Not Covered": Semantic=None OR Relationship=Not Satisfied OR no structural matches

Respond ONLY with JSON:
{
  "semantic_match": "Partial",
  "semantic_rationale": "The control addresses risk appetite thresholds broadly but does not specifically address liquidity risk tolerance as required by this obligation.",
  "relationship_match": "Partial",
  "relationship_rationale": "The control operates annually which meets the frequency requirement, but it covers enterprise-wide risk appetite rather than specifically liquidity risk tolerance.",
  "overall_coverage": "Partially Covered"
}
"""

# Keywords that indicate strong deterministic coverage
_STRONG_MATCH_KEYWORDS = frozenset({
    "approve", "review", "monitor", "verify", "validate", "audit",
    "assess", "ensure", "maintain", "establish", "certify", "attest",
    "report", "document", "record", "enforce", "control", "check",
})


def _deterministic_strong_match(
    obligation: dict[str, Any],
    control: dict[str, Any],
) -> bool:
    """Check if obligation and control have strong keyword overlap (Tier 1)."""
    ob_text = f"{obligation.get('abstract', '')} {obligation.get('section_title', '')}".lower()
    ctrl_text = (
        f"{control.get('full_description', '')} "
        f"{control.get('what', '')} "
        f"{control.get('why', '')}"
    ).lower()

    ob_keywords = set(ob_text.split()) & _STRONG_MATCH_KEYWORDS
    ctrl_keywords = set(ctrl_text.split()) & _STRONG_MATCH_KEYWORDS

    overlap = ob_keywords & ctrl_keywords
    return len(overlap) >= 3


def _deterministic_coverage_result(
    obligation: dict[str, Any],
    control: dict[str, Any],
    apqc_hierarchy_id: str,
) -> dict[str, Any]:
    """Produce Tier 1 deterministic coverage without LLM (strong match)."""
    ctrl_hid = control.get("hierarchy_id", "")
    exact_match = ctrl_hid == apqc_hierarchy_id or ctrl_hid.startswith(f"{apqc_hierarchy_id}.")

    if exact_match:
        return {
            "semantic_match": "Full",
            "semantic_rationale": f"Deterministic Tier 1 — strong keyword overlap and exact APQC structural match at {ctrl_hid}.",
            "relationship_match": "Satisfied",
            "relationship_rationale": f"Deterministic Tier 1 — control operates at the required APQC node with strong alignment.",
            "overall_coverage": "Covered",
        }
    return {
        "semantic_match": "Partial",
        "semantic_rationale": f"Deterministic Tier 1 — strong keyword overlap but control is at parent/sibling APQC node {ctrl_hid}.",
        "relationship_match": "Partial",
        "relationship_rationale": f"Deterministic Tier 1 — structural match at broader level, specific relationship not verified.",
        "overall_coverage": "Partially Covered",
    }


@register_agent
class CoverageAssessorAgent(BaseAgent):
    """Evaluates control coverage using a 3-tier resolution system.

    Tier 1: Deterministic — strong match → immediate result, no LLM.
    Tier 2: Edge Case → LLM resolves ambiguity.
    Tier 3: Deterministic Fallback → conservative default when no LLM.
    """

    def __init__(self, context: AgentContext) -> None:
        super().__init__(context, name="CoverageAssessorAgent")
        self.edge_detector = EdgeCaseDetector()

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        obligation: dict[str, Any] = kwargs.get("obligation", {})
        control: dict[str, Any] | None = kwargs.get("control")
        candidate_controls: list[dict[str, Any]] = kwargs.get("candidate_controls", [])
        mapping: dict[str, Any] | None = kwargs.get("mapping")
        apqc_hierarchy_id: str = kwargs.get("apqc_hierarchy_id", "")

        citation = obligation.get("citation", "")

        # ─── No candidate controls → deterministic Not Covered ───
        if control is None:
            edge_result = self.edge_detector.detect_coverage_edge_case(
                obligation, [], mapping,
            )
            return self._build_result(
                citation=citation,
                apqc_hierarchy_id=apqc_hierarchy_id,
                control_id=None,
                structural_match=False,
                semantic_match="None",
                semantic_rationale="No candidate controls found at this APQC node.",
                relationship_match="Not Satisfied",
                relationship_rationale="No controls available for evaluation.",
                overall_coverage="Not Covered",
                edge_result=edge_result,
                llm_used=False,
            )

        # ─── Run edge case detection ───
        edge_result = self.edge_detector.detect_coverage_edge_case(
            obligation,
            candidate_controls or ([control] if control else []),
            mapping,
        )

        # ─── Tier 1: Deterministic — strong match, no LLM needed ───
        if not edge_result.is_edge_case and _deterministic_strong_match(obligation, control):
            logger.info(
                "[%s] Tier 1 deterministic resolution for %s",
                self.name, citation,
            )
            det = _deterministic_coverage_result(obligation, control, apqc_hierarchy_id)
            return self._build_result(
                citation=citation,
                apqc_hierarchy_id=apqc_hierarchy_id,
                control_id=control.get("control_id"),
                structural_match=True,
                edge_result=edge_result,
                llm_used=False,
                **det,
            )

        # ─── Tier 2: Edge case → call LLM to resolve ambiguity ───
        if edge_result.is_edge_case and self.context.client is not None:
            logger.info(
                "[%s] Tier 2 LLM resolution for %s — reasons: %s",
                self.name, citation,
                [r.value for r in edge_result.reasons],
            )
            llm_result = await self._resolve_with_llm(
                obligation, control, apqc_hierarchy_id, edge_result, kwargs,
            )
            if llm_result:
                return self._build_result(
                    citation=citation,
                    apqc_hierarchy_id=apqc_hierarchy_id,
                    control_id=control.get("control_id"),
                    structural_match=True,
                    edge_result=EdgeCaseResult(
                        is_edge_case=True,
                        reasons=edge_result.reasons,
                        tier=ResolutionTier.EDGE_CASE_LLM,
                        details=edge_result.details,
                    ),
                    llm_used=True,
                    **llm_result,
                )

        # ─── Tier 3: Deterministic fallback ───
        logger.info(
            "[%s] Tier 3 deterministic fallback for %s — edge_case=%s, llm_available=%s",
            self.name, citation, edge_result.is_edge_case, self.context.client is not None,
        )
        fallback_tier = ResolutionTier.DETERMINISTIC_FALLBACK if edge_result.is_edge_case else ResolutionTier.DETERMINISTIC
        return self._build_result(
            citation=citation,
            apqc_hierarchy_id=apqc_hierarchy_id,
            control_id=control.get("control_id"),
            structural_match=True,
            semantic_match="Partial",
            semantic_rationale="Deterministic fallback — structural match found but semantic evaluation unavailable.",
            relationship_match="Partial",
            relationship_rationale="Deterministic fallback — relationship evaluation unavailable.",
            overall_coverage="Partially Covered",
            edge_result=EdgeCaseResult(
                is_edge_case=edge_result.is_edge_case,
                reasons=edge_result.reasons,
                tier=fallback_tier,
                details=edge_result.details,
            ),
            llm_used=False,
        )

    # ── LLM resolution (Tier 2 only) ──

    async def _resolve_with_llm(
        self,
        obligation: dict[str, Any],
        control: dict[str, Any],
        apqc_hierarchy_id: str,
        edge_result: EdgeCaseResult,
        kwargs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Call LLM only for edge cases. Returns coverage fields or None."""
        edge_reasons_str = ", ".join(r.value for r in edge_result.reasons)

        user_prompt = f"""\
Evaluate control coverage for this regulatory obligation.

⚠️ EDGE CASE — flagged because: {edge_reasons_str}
Edge case details: {edge_result.details}

OBLIGATION: {obligation.get('citation', '')}
REQUIREMENT: {obligation.get('abstract', '')}
OBLIGATION CATEGORY: {obligation.get('obligation_category', '')}
RELATIONSHIP TYPE: {obligation.get('relationship_type', '')}
CRITICALITY: {obligation.get('criticality_tier', '')}
MAPPED APQC PROCESS: {apqc_hierarchy_id} — {kwargs.get('apqc_process_name', '')}

CANDIDATE CONTROL:
  ID: {control.get('control_id', '')}
  APQC: {control.get('hierarchy_id', '')} — {control.get('leaf_name', '')}
  Type: {control.get('selected_level_2', '')}
  Description: {control.get('full_description', '')}
  Who: {control.get('who', '')}
  What: {control.get('what', '')}
  When: {control.get('when', '')} (Frequency: {control.get('frequency', '')})
  Where: {control.get('where', '')}
  Why: {control.get('why', '')}
  Evidence: {control.get('evidence', '')}

Evaluate whether this control covers the obligation."""

        raw = await self.call_llm(_SYSTEM_PROMPT, user_prompt)
        if raw:
            parsed = self.parse_json(raw)
            if parsed.get("overall_coverage"):
                return {
                    "semantic_match": parsed.get("semantic_match", "None"),
                    "semantic_rationale": parsed.get("semantic_rationale", ""),
                    "relationship_match": parsed.get("relationship_match", "Not Satisfied"),
                    "relationship_rationale": parsed.get("relationship_rationale", ""),
                    "overall_coverage": parsed["overall_coverage"],
                }
        return None

    # ── Result builder ──

    @staticmethod
    def _build_result(
        *,
        citation: str,
        apqc_hierarchy_id: str,
        control_id: str | None,
        structural_match: bool,
        semantic_match: str,
        semantic_rationale: str,
        relationship_match: str,
        relationship_rationale: str,
        overall_coverage: str,
        edge_result: EdgeCaseResult,
        llm_used: bool,
    ) -> dict[str, Any]:
        """Build standardized coverage result with edge case audit trail."""
        return {
            "citation": citation,
            "apqc_hierarchy_id": apqc_hierarchy_id,
            "control_id": control_id,
            "structural_match": structural_match,
            "semantic_match": semantic_match,
            "semantic_rationale": semantic_rationale,
            "relationship_match": relationship_match,
            "relationship_rationale": relationship_rationale,
            "overall_coverage": overall_coverage,
            "edge_case": {
                "is_edge_case": edge_result.is_edge_case,
                "reasons": [r.value for r in edge_result.reasons],
                "resolution_tier": edge_result.tier.value,
                "llm_used": llm_used,
                "details": edge_result.details,
            },
        }
