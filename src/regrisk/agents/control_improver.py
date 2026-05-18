"""
ControlImprovementAgent — proposes new or enhanced controls to close coverage gaps.

For each gap (Not Covered / Partially Covered assessment), the agent generates
a proposed control following the exact 15-field ControlRecord schema so that
the output can be directly appended to the control inventory.
"""

from __future__ import annotations

from typing import Any

from regrisk.agents.base import AgentContext, BaseAgent

_SYSTEM_PROMPT = """\
You are a controls advisory specialist for a large financial institution. Your task is to \
propose a new or improved internal control that would close a specific regulatory compliance gap.

CONTEXT:
A regulatory obligation was mapped to an APQC process node and evaluated against existing controls. \
The evaluation found a coverage gap — either "Not Covered" (no control addresses the requirement) \
or "Partially Covered" (existing control is insufficient).

YOUR TASK:
Propose a control that would fully satisfy the regulatory obligation. The control must follow the \
exact schema of the institution's control inventory.

CONTROL SCHEMA (all 15 fields are required):
- control_id: A unique identifier. Use the format "PROP-{section}-{seq}" where section is the \
  APQC top-level section number and seq is a 3-digit sequence (e.g., "PROP-11-001").
- hierarchy_id: The APQC hierarchy node this control maps to (use the provided APQC ID).
- leaf_name: Short name for the control activity (< 80 chars).
- full_description: Comprehensive description of the control including what it does, who performs it, \
  frequency, regulatory context, and expected outcomes. (2-4 sentences)
- selected_level_1: Either "Preventive" or "Detective".
- selected_level_2: One of: "Policy Control", "Risk and Compliance Assessments", \
  "Exception Reporting", "Authorization", "Reconciliation", "Monitoring", \
  "Segregation of Duties", "Training and Awareness".
- who: The role responsible for executing the control (e.g., "Chief Risk Officer").
- what: Description of the control activity performed.
- when: Timing of execution (e.g., "Quarterly", "Upon significant regulatory changes").
- frequency: Frequency summary (e.g., "Quarterly", "Annual", "Monthly", "Daily", "Event-Driven").
- where: Geographic or system scope (e.g., "Enterprise-wide", "U.S. Operations").
- why: Business rationale connecting the control to risk mitigation.
- evidence: Specific documentation/artifacts produced as evidence of control execution.
- quality_rating: Expected effectiveness — "Effective" for well-designed controls, \
  "Strong" for controls with multiple layers.
- business_unit_name: The business unit that owns this control.

If an existing control is provided (enhancement case), improve upon it to close the gap. \
If no existing control exists (new control case), design one from scratch.

Respond ONLY with JSON:
{
  "proposed_control": {
    "control_id": "PROP-11-001",
    "hierarchy_id": "11.1.5",
    "leaf_name": "...",
    "full_description": "...",
    "selected_level_1": "Preventive",
    "selected_level_2": "Policy Control",
    "who": "...",
    "what": "...",
    "when": "...",
    "frequency": "...",
    "where": "...",
    "why": "...",
    "evidence": "...",
    "quality_rating": "Effective",
    "business_unit_name": "..."
  },
  "improvement_rationale": "Explanation of why this control closes the gap...",
  "change_type": "new",
  "gap_addressed": "Summary of the specific gap this control resolves..."
}
"""


class ControlImprovementAgent(BaseAgent):
    """Proposes new or enhanced controls to close coverage gaps."""

    def __init__(self, context: AgentContext) -> None:
        super().__init__(context, name="ControlImprovementAgent")

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        obligation: dict[str, Any] = kwargs.get("obligation", {})
        assessment: dict[str, Any] = kwargs.get("assessment", {})
        existing_control: dict[str, Any] | None = kwargs.get("existing_control")
        apqc_hierarchy_id: str = kwargs.get("apqc_hierarchy_id", "")
        apqc_process_name: str = kwargs.get("apqc_process_name", "")
        improvement_counter: int = kwargs.get("improvement_counter", 0)

        citation = obligation.get("citation", "")
        coverage_status = assessment.get("overall_coverage", "Not Covered")
        change_type = "enhancement" if existing_control else "new"

        # Build a sequential proposed control ID
        section = apqc_hierarchy_id.split(".")[0] if apqc_hierarchy_id else "0"
        seq = f"{improvement_counter + 1:03d}"
        default_ctrl_id = f"PROP-{section}-{seq}"

        # Build user prompt
        existing_ctrl_block = ""
        if existing_control:
            existing_ctrl_block = f"""
EXISTING CONTROL (to be enhanced):
  ID: {existing_control.get('control_id', '')}
  APQC: {existing_control.get('hierarchy_id', '')} — {existing_control.get('leaf_name', '')}
  Type: {existing_control.get('selected_level_1', '')} / {existing_control.get('selected_level_2', '')}
  Description: {existing_control.get('full_description', '')}
  Who: {existing_control.get('who', '')}
  What: {existing_control.get('what', '')}
  When: {existing_control.get('when', '')} (Frequency: {existing_control.get('frequency', '')})
  Where: {existing_control.get('where', '')}
  Why: {existing_control.get('why', '')}
  Evidence: {existing_control.get('evidence', '')}
  Quality: {existing_control.get('quality_rating', '')}
  Business Unit: {existing_control.get('business_unit_name', '')}
"""
        else:
            existing_ctrl_block = "\nNo existing control — propose a new control from scratch.\n"

        user_prompt = f"""\
Propose a control to close this regulatory compliance gap:

OBLIGATION: {citation}
REQUIREMENT: {obligation.get('abstract', '')}
FULL TEXT: {obligation.get('text', '')}
OBLIGATION CATEGORY: {obligation.get('obligation_category', '')}
RELATIONSHIP TYPE: {obligation.get('relationship_type', '')}
CRITICALITY: {obligation.get('criticality_tier', '')}

MAPPED APQC PROCESS: {apqc_hierarchy_id} — {apqc_process_name}

COVERAGE ASSESSMENT:
  Status: {coverage_status}
  Semantic Rationale: {assessment.get('semantic_rationale', '')}
  Relationship Rationale: {assessment.get('relationship_rationale', '')}
{existing_ctrl_block}
Use control_id: "{default_ctrl_id}"
Use hierarchy_id: "{apqc_hierarchy_id}"

Propose a {"enhanced version of the existing" if existing_control else "new"} control \
that would achieve "Covered" status for this obligation."""

        raw = await self.call_llm(_SYSTEM_PROMPT, user_prompt)
        parsed = self.parse_json(raw)
        proposed = parsed.get("proposed_control", {})
        if not (proposed and proposed.get("control_id")):
            return {
                "proposed_control": None,
                "improvement_rationale": "",
                "change_type": change_type,
                "gap_addressed": assessment.get("semantic_rationale", ""),
                "source_citation": citation,
                "source_apqc_id": apqc_hierarchy_id,
                "original_control_id": (
                    existing_control.get("control_id") if existing_control else None
                ),
            }

        proposed.setdefault("hierarchy_id", apqc_hierarchy_id)
        return {
            "proposed_control": proposed,
            "improvement_rationale": parsed.get("improvement_rationale", ""),
            "change_type": parsed.get("change_type", change_type),
            "gap_addressed": parsed.get("gap_addressed", ""),
            "source_citation": citation,
            "source_apqc_id": apqc_hierarchy_id,
            "original_control_id": (
                existing_control.get("control_id") if existing_control else None
            ),
        }
