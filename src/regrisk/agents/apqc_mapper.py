"""
APQCMapperAgent — maps classified obligations to APQC processes.

Produces many-to-many mappings with typed relationships and confidence scores.
"""

from __future__ import annotations

from typing import Any

from regrisk.agents.base import AgentContext, BaseAgent
from regrisk.agents.source_type_prompts import mapper_guidance

_SYSTEM_PROMPT_TEMPLATE = """\
You are mapping regulatory obligations to business processes using the APQC Process Classification Framework (PCF).

For each obligation, identify 1-{max_mappings} APQC processes that the obligation constrains or requires. Map to depth {depth} (format: X.Y.Z).

APQC PROCESS HIERARCHY:
{apqc_summary}

For each mapping, specify:
- The APQC hierarchy_id and process name
- The relationship_type: Requires Existence | Constrains Execution | Requires Evidence | Sets Frequency
- A specific relationship_detail describing WHAT the regulation requires OF that process
- A confidence score (0.0 to 1.0)

RULES:
- Prefer specific processes over general ones. "11.1.1 Establish enterprise risk framework" is better than "11.0 Manage Enterprise Risk."
- An obligation CAN map to multiple processes (many-to-many is expected).
- Relationship_detail must be specific: NOT "relates to risk management" but "requires the board to approve risk tolerance levels at least annually."
- If no APQC process fits, map to the closest match with low confidence.

Respond ONLY with JSON:
{{
  "mappings": [
    {{
      "citation": "12 CFR 252.34(a)(1)(i)",
      "apqc_hierarchy_id": "11.1.1",
      "apqc_process_name": "Establish the enterprise risk framework and policies",
      "relationship_type": "Constrains Execution",
      "relationship_detail": "Board must approve acceptable level of liquidity risk at least annually.",
      "confidence": 0.92
    }}
  ]
}}
"""

# Module-level keyword routing previously used for a no-LLM fallback has been
# removed. The pipeline now requires an LLM client; see ADR 0006.



class APQCMapperAgent(BaseAgent):
    """Maps obligations to APQC processes."""

    def __init__(self, context: AgentContext) -> None:
        super().__init__(context, name="APQCMapperAgent")

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        obligations: list[dict[str, Any]] = kwargs.get("obligations", [])
        apqc_summary: str = kwargs.get("apqc_summary", "")
        config: dict[str, Any] = kwargs.get("config", {})
        regulation_name: str = kwargs.get("regulation_name", "")
        section_citation: str = kwargs.get("section_citation", "")
        section_title: str = kwargs.get("section_title", "")

        max_mappings = config.get("max_apqc_mappings_per_obligation", 5)
        depth = config.get("apqc_mapping_depth", 3)

        if not obligations:
            return {"mappings": []}

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            max_mappings=max_mappings,
            depth=depth,
            apqc_summary=apqc_summary[:15000],  # Truncate if needed
        )

        ob_lines: list[str] = []
        group_source_type = ""
        for ob in obligations:
            cit = ob.get("citation", "")
            cat = ob.get("obligation_category", "")
            rel = ob.get("relationship_type", "")
            crit = ob.get("criticality_tier", "")
            abstract = ob.get("abstract", "")
            st = ob.get("source_type", "")
            group_source_type = group_source_type or st
            ob_lines.append(f"  - {cit} [{cat}, {rel}, {crit}]:\n    {abstract[:300]}")

        guidance = mapper_guidance(group_source_type)
        guidance_block = f"\n{guidance}\n" if guidance else ""

        user_prompt = f"""\
Map the following regulatory obligations to APQC processes:
{guidance_block}
REGULATION: {regulation_name}
SECTION: {section_citation} — {section_title}

OBLIGATIONS TO MAP ({len(obligations)}):
{chr(10).join(ob_lines)}

Produce mappings for ALL listed obligations."""

        raw = await self.call_llm(system_prompt, user_prompt, max_tokens=8000)
        parsed = self.parse_json(raw)
        mappings = parsed.get("mappings", [])
        return {"mappings": mappings}
