"""
CoverageAssessorAgent — evaluates whether controls cover mapped obligations.

Three evaluation layers: structural match (pre-computed), semantic match (LLM),
relationship-type match (LLM).
"""

from __future__ import annotations

from typing import Any

from regrisk.agents.base import AgentContext, BaseAgent, register_agent

_SYSTEM_PROMPT = """\
You are evaluating whether existing internal controls adequately cover a specific regulatory obligation.

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


@register_agent
class CoverageAssessorAgent(BaseAgent):
    """Evaluates control coverage for a mapped obligation."""

    def __init__(self, context: AgentContext) -> None:
        super().__init__(context, name="CoverageAssessorAgent")

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        obligation: dict[str, Any] = kwargs.get("obligation", {})
        control: dict[str, Any] | None = kwargs.get("control")
        apqc_hierarchy_id: str = kwargs.get("apqc_hierarchy_id", "")

        citation = obligation.get("citation", "")

        # No candidate controls → deterministic Not Covered
        if control is None:
            return {
                "citation": citation,
                "apqc_hierarchy_id": apqc_hierarchy_id,
                "control_id": None,
                "structural_match": False,
                "semantic_match": "None",
                "semantic_rationale": "No candidate controls found at this APQC node.",
                "relationship_match": "Not Satisfied",
                "relationship_rationale": "No controls available for evaluation.",
                "overall_coverage": "Not Covered",
            }

        # Build user prompt for LLM evaluation
        user_prompt = f"""\
Evaluate control coverage for this regulatory obligation:

OBLIGATION: {citation}
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
                    "citation": citation,
                    "apqc_hierarchy_id": apqc_hierarchy_id,
                    "control_id": control.get("control_id"),
                    "structural_match": True,
                    "semantic_match": parsed.get("semantic_match", "None"),
                    "semantic_rationale": parsed.get("semantic_rationale", ""),
                    "relationship_match": parsed.get("relationship_match", "Not Satisfied"),
                    "relationship_rationale": parsed.get("relationship_rationale", ""),
                    "overall_coverage": parsed["overall_coverage"],
                }

        # Deterministic fallback: structural match → Partially Covered
        return {
            "citation": citation,
            "apqc_hierarchy_id": apqc_hierarchy_id,
            "control_id": control.get("control_id"),
            "structural_match": True,
            "semantic_match": "Partial",
            "semantic_rationale": "Deterministic fallback — structural match found but semantic evaluation unavailable.",
            "relationship_match": "Partial",
            "relationship_rationale": "Deterministic fallback — relationship evaluation unavailable.",
            "overall_coverage": "Partially Covered",
        }
