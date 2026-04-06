"""
ObligationClassifierAgent — classifies regulatory obligations using
Promontory/IBM RCM methodology.

Categories: Attestation, Documentation, Controls, General Awareness, Not Assigned
"""

from __future__ import annotations

from typing import Any

from regrisk.agents.base import AgentContext, BaseAgent, register_agent

_SYSTEM_PROMPT = """\
You are a regulatory compliance analyst specializing in regulatory change management for financial institutions.

You are classifying regulatory obligations using the Promontory/IBM RCM methodology.

For each obligation, determine:

1. OBLIGATION CATEGORY (exactly one):
   - Attestation: Requires senior management sign-off, certification, or board approval
   - Documentation: Requires maintenance of written policies, procedures, plans, or records
   - Controls: Requires evidence of operating processes, controls, systems, or monitoring
   - General Awareness: Is principle-based, definitional, or provides general authority with no explicit implementation requirement
   - Not Assigned: Is a general requirement not directly actionable

2. RELATIONSHIP TYPE (for Attestation, Documentation, and Controls only; "N/A" for General Awareness and Not Assigned):
   - Requires Existence: The regulation requires a specific function, committee, role, or process to exist
   - Constrains Execution: The regulation imposes specific requirements on HOW a process must be performed (e.g., board approval, independence, specific methodology)
   - Requires Evidence: The regulation requires documentation, reports, or records to be produced and maintained
   - Sets Frequency: The regulation specifies how often an activity must be performed (e.g., "at least quarterly", "annually")

3. CRITICALITY TIER:
   - High: Violation would likely trigger enforcement action, consent order, or MRA
   - Medium: Violation would result in supervisory criticism or examination findings
   - Low: Violation would be noted as an observation or best-practice gap

Respond ONLY with JSON:
{
  "classifications": [
    {
      "citation": "12 CFR 252.34(a)(1)(i)",
      "obligation_category": "Controls",
      "relationship_type": "Constrains Execution",
      "criticality_tier": "High",
      "classification_rationale": "Requires the board to approve liquidity risk tolerance annually, imposing a specific governance constraint on the risk management process."
    }
  ]
}
"""


@register_agent
class ObligationClassifierAgent(BaseAgent):
    """Classifies obligations in a section group."""

    def __init__(self, context: AgentContext) -> None:
        super().__init__(context, name="ObligationClassifierAgent")

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        group: dict[str, Any] = kwargs.get("group", {})
        config: dict[str, Any] = kwargs.get("config", {})

        obligations = group.get("obligations", [])
        if not obligations:
            return {"classifications": []}

        regulation_name = kwargs.get("regulation_name", "")
        section_citation = group.get("section_citation", "")
        section_title = group.get("section_title", "")
        subpart = group.get("subpart", "")
        topic_title = group.get("topic_title", "")

        # Build user prompt
        ob_lines: list[str] = []
        for ob in obligations:
            cit = ob.get("citation", "") if isinstance(ob, dict) else ob.citation
            tl3 = ob.get("title_level_3", "") if isinstance(ob, dict) else ob.title_level_3
            tl4 = ob.get("title_level_4", "") if isinstance(ob, dict) else ob.title_level_4
            tl5 = ob.get("title_level_5", "") if isinstance(ob, dict) else ob.title_level_5
            abstract = ob.get("abstract", "") if isinstance(ob, dict) else ob.abstract
            ob_lines.append(f"  - {cit}: {tl3} | {tl4} | {tl5}\n    {abstract[:300]}")

        user_prompt = f"""\
Classify each obligation in this regulatory section:

REGULATION: {regulation_name}
SECTION: {section_citation} — {section_title}
SUBPART: {subpart} — {topic_title}

OBLIGATIONS ({len(obligations)}):
{chr(10).join(ob_lines)}

Classify ALL {len(obligations)} obligations. Return one classification per obligation."""

        raw = await self.call_llm(_SYSTEM_PROMPT, user_prompt, max_tokens=8000)
        if raw:
            parsed = self.parse_json(raw)
            classifications = parsed.get("classifications", [])
            if classifications:
                # Enrich with section metadata
                for c in classifications:
                    c.setdefault("section_citation", section_citation)
                    c.setdefault("section_title", section_title)
                    c.setdefault("subpart", subpart)
                    # Map citation to abstract
                    for ob in obligations:
                        ob_cit = ob.get("citation", "") if isinstance(ob, dict) else ob.citation
                        if ob_cit == c.get("citation"):
                            ob_abs = ob.get("abstract", "") if isinstance(ob, dict) else ob.abstract
                            c.setdefault("abstract", ob_abs)
                            break
                return {"classifications": classifications}

        # Deterministic fallback
        return {"classifications": self._deterministic_classify(
            obligations, section_citation, section_title, subpart,
        )}

    @staticmethod
    def _deterministic_classify(
        obligations: list[Any],
        section_citation: str,
        section_title: str,
        subpart: str,
    ) -> list[dict[str, Any]]:
        """Keyword-based deterministic classification."""
        results: list[dict[str, Any]] = []
        for ob in obligations:
            if isinstance(ob, dict):
                cit = ob.get("citation", "")
                abstract = ob.get("abstract", "")
                tl3 = ob.get("title_level_3", "")
                tl4 = ob.get("title_level_4", "")
                tl5 = ob.get("title_level_5", "")
            else:
                cit = ob.citation
                abstract = ob.abstract
                tl3 = ob.title_level_3
                tl4 = ob.title_level_4
                tl5 = ob.title_level_5

            combined = f"{tl3} {tl4} {tl5} {abstract}".lower()

            if any(kw in combined for kw in ("definition", "authority", "purpose", "scope")):
                cat, rel, crit = "General Awareness", "N/A", "Low"
                rationale = "Contains definitional or authority language."
            elif any(kw in combined for kw in ("must", "shall", "require", "ensure", "maintain")):
                cat, rel, crit = "Controls", "Constrains Execution", "High"
                rationale = "Contains mandatory control language."
            elif any(kw in combined for kw in ("report", "submit", "disclose", "document", "record")):
                cat, rel, crit = "Documentation", "Requires Evidence", "Medium"
                rationale = "Contains documentation or reporting language."
            elif any(kw in combined for kw in ("approve", "attest", "certif", "board")):
                cat, rel, crit = "Attestation", "Requires Existence", "High"
                rationale = "Contains attestation or board approval language."
            else:
                cat, rel, crit = "Not Assigned", "N/A", "Low"
                rationale = "No clear actionable requirement identified."

            results.append({
                "citation": cit,
                "abstract": abstract,
                "section_citation": section_citation,
                "section_title": section_title,
                "subpart": subpart,
                "obligation_category": cat,
                "relationship_type": rel,
                "criticality_tier": crit,
                "classification_rationale": rationale,
            })
        return results
