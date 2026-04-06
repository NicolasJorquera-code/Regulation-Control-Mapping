"""
APQCMapperAgent — maps classified obligations to APQC processes.

Produces many-to-many mappings with typed relationships and confidence scores.
"""

from __future__ import annotations

from typing import Any

from regrisk.agents.base import AgentContext, BaseAgent, register_agent

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

# Keyword → APQC category mapping for deterministic fallback
_KEYWORD_APQC_MAP: dict[str, list[tuple[str, str]]] = {
    "liquidity": [("9.7.1", "Manage treasury operations")],
    "capital": [("9.5.1", "Manage capital structure")],
    "stress test": [("9.7.1", "Manage treasury operations"), ("11.1.1", "Establish enterprise risk framework")],
    "risk committee": [("11.1.1", "Establish enterprise risk framework")],
    "risk management": [("11.1.1", "Establish enterprise risk framework")],
    "credit": [("9.6.1", "Manage credit")],
    "counterparty": [("9.6.1", "Manage credit")],
    "compliance": [("11.2.1", "Manage regulatory compliance")],
    "audit": [("11.3.1", "Manage internal audit")],
    "report": [("11.2.1", "Manage regulatory compliance")],
    "governance": [("11.1.1", "Establish enterprise risk framework")],
    "board": [("11.1.1", "Establish enterprise risk framework")],
    "foreign": [("11.2.1", "Manage regulatory compliance")],
    "debt": [("9.5.1", "Manage capital structure")],
    "resolution": [("11.1.1", "Establish enterprise risk framework")],
    "contingency": [("9.7.1", "Manage treasury operations")],
}


@register_agent
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
        for ob in obligations:
            cit = ob.get("citation", "")
            cat = ob.get("obligation_category", "")
            rel = ob.get("relationship_type", "")
            crit = ob.get("criticality_tier", "")
            abstract = ob.get("abstract", "")
            ob_lines.append(f"  - {cit} [{cat}, {rel}, {crit}]:\n    {abstract[:300]}")

        user_prompt = f"""\
Map the following regulatory obligations to APQC processes:

REGULATION: {regulation_name}
SECTION: {section_citation} — {section_title}

OBLIGATIONS TO MAP ({len(obligations)}):
{chr(10).join(ob_lines)}

Produce mappings for ALL listed obligations."""

        raw = await self.call_llm(system_prompt, user_prompt, max_tokens=8000)
        if raw:
            parsed = self.parse_json(raw)
            mappings = parsed.get("mappings", [])
            if mappings:
                return {"mappings": mappings}

        # Deterministic fallback
        return {"mappings": self._deterministic_map(obligations)}

    @staticmethod
    def _deterministic_map(obligations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keyword-based deterministic mapping to APQC categories."""
        mappings: list[dict[str, Any]] = []
        for ob in obligations:
            cit = ob.get("citation", "")
            combined = f"{ob.get('section_title', '')} {ob.get('abstract', '')}".lower()

            matched = False
            for keyword, targets in _KEYWORD_APQC_MAP.items():
                if keyword in combined:
                    for apqc_id, apqc_name in targets:
                        mappings.append({
                            "citation": cit,
                            "apqc_hierarchy_id": apqc_id,
                            "apqc_process_name": apqc_name,
                            "relationship_type": ob.get("relationship_type", "Constrains Execution"),
                            "relationship_detail": f"Deterministic mapping based on keyword '{keyword}' in obligation text.",
                            "confidence": 0.5,
                        })
                    matched = True
                    break

            if not matched:
                # Default to risk management
                mappings.append({
                    "citation": cit,
                    "apqc_hierarchy_id": "11.1.1",
                    "apqc_process_name": "Establish enterprise risk framework",
                    "relationship_type": ob.get("relationship_type", "Constrains Execution"),
                    "relationship_detail": "Default mapping — no specific keyword match found.",
                    "confidence": 0.3,
                })
        return mappings
