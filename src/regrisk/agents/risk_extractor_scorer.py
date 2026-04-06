"""
RiskExtractorAndScorerAgent — extracts and scores risks for uncovered obligations.

Produces 1-3 scored risks per obligation using the banking risk taxonomy
and 4-point impact × frequency scales.
"""

from __future__ import annotations

from typing import Any

from regrisk.agents.base import AgentContext, BaseAgent, register_agent
from regrisk.validation.validator import derive_inherent_rating

_SYSTEM_PROMPT_TEMPLATE = """\
You are a senior risk analyst at a large financial institution.

For the given regulatory obligation that lacks adequate control coverage, identify the risks that arise from non-compliance.

RISK TAXONOMY (classify each risk into exactly one category and sub-category):
{risk_taxonomy}

IMPACT SCALE (1-4):
{impact_scale}

FREQUENCY/LIKELIHOOD SCALE (1-4):
{frequency_scale}

For each risk:
1. Write a 25-50 word risk description (what could go wrong)
2. Classify into a risk_category and sub_risk_category from the taxonomy
3. Score impact (1-4) and frequency (1-4) with 2-4 sentence rationales
4. The inherent_risk_rating is derived: impact × frequency. >=12=Critical, >=8=High, >=4=Medium, <4=Low.

Respond ONLY with JSON:
{{
  "risks": [
    {{
      "risk_description": "...",
      "risk_category": "Compliance Risk",
      "sub_risk_category": "Regulatory Compliance Risk",
      "impact_rating": 3,
      "impact_rationale": "...",
      "frequency_rating": 2,
      "frequency_rationale": "..."
    }}
  ]
}}
"""


def _format_taxonomy(taxonomy: dict[str, Any]) -> str:
    lines: list[str] = []
    for cat, info in taxonomy.items():
        desc = info.get("description", "")
        subs = ", ".join(info.get("sub_risks", []))
        lines.append(f"- {cat}: {desc}\n  Sub-risks: {subs}")
    return "\n".join(lines)


def _format_scale(scale: dict[int, dict[str, str]]) -> str:
    lines: list[str] = []
    for level, info in sorted(scale.items()):
        label = info.get("label", "")
        parts = [f"{k}: {v}" for k, v in info.items() if k != "label"]
        lines.append(f"  {level} ({label}): {'; '.join(parts)}")
    return "\n".join(lines)


@register_agent
class RiskExtractorAndScorerAgent(BaseAgent):
    """Extracts and scores risks for uncovered obligations."""

    def __init__(self, context: AgentContext) -> None:
        super().__init__(context, name="RiskExtractorAndScorerAgent")

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        obligation: dict[str, Any] = kwargs.get("obligation", {})
        coverage_status: str = kwargs.get("coverage_status", "Not Covered")
        gap_rationale: str = kwargs.get("gap_rationale", "")
        apqc_hierarchy_id: str = kwargs.get("apqc_hierarchy_id", "")
        apqc_process_name: str = kwargs.get("apqc_process_name", "")
        risk_taxonomy: dict[str, Any] = kwargs.get("risk_taxonomy", {})
        config: dict[str, Any] = kwargs.get("config", {})
        risk_counter: int = kwargs.get("risk_counter", 0)

        citation = obligation.get("citation", "")
        criticality = obligation.get("criticality_tier", "Medium")
        risk_id_prefix = config.get("risk_id_prefix", "RISK")

        impact_scale = config.get("impact_scale", {})
        frequency_scale = config.get("frequency_scale", {})

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            risk_taxonomy=_format_taxonomy(risk_taxonomy),
            impact_scale=_format_scale(impact_scale),
            frequency_scale=_format_scale(frequency_scale),
        )

        user_prompt = f"""\
The following regulatory obligation has {coverage_status} control coverage:

OBLIGATION: {citation}
REQUIREMENT: {obligation.get('abstract', '')}
CRITICALITY: {criticality}
MAPPED APQC: {apqc_hierarchy_id} — {apqc_process_name}
COVERAGE GAP: {gap_rationale}

Extract 1-3 risks and score them."""

        raw = await self.call_llm(system_prompt, user_prompt)
        if raw:
            parsed = self.parse_json(raw)
            risks = parsed.get("risks", [])
            if risks:
                scored: list[dict[str, Any]] = []
                for i, r in enumerate(risks):
                    impact = max(1, min(4, int(r.get("impact_rating", 2))))
                    freq = max(1, min(4, int(r.get("frequency_rating", 2))))
                    scored.append({
                        "risk_id": f"{risk_id_prefix}-{risk_counter + i + 1:03d}",
                        "source_citation": citation,
                        "source_apqc_id": apqc_hierarchy_id,
                        "risk_description": r.get("risk_description", ""),
                        "risk_category": r.get("risk_category", "Compliance Risk"),
                        "sub_risk_category": r.get("sub_risk_category", "Regulatory Compliance Risk"),
                        "impact_rating": impact,
                        "impact_rationale": r.get("impact_rationale", ""),
                        "frequency_rating": freq,
                        "frequency_rationale": r.get("frequency_rationale", ""),
                        "inherent_risk_rating": derive_inherent_rating(impact, freq),
                        "coverage_status": coverage_status,
                    })
                return {"risks": scored}

        # Deterministic fallback
        impact, freq = self._default_scores(criticality)
        return {"risks": [{
            "risk_id": f"{risk_id_prefix}-{risk_counter + 1:03d}",
            "source_citation": citation,
            "source_apqc_id": apqc_hierarchy_id,
            "risk_description": f"Non-compliance risk for {citation} due to {coverage_status.lower()} control coverage.",
            "risk_category": "Compliance Risk",
            "sub_risk_category": "Regulatory Compliance Risk",
            "impact_rating": impact,
            "impact_rationale": f"Deterministic score based on {criticality} criticality.",
            "frequency_rating": freq,
            "frequency_rationale": f"Deterministic score based on {criticality} criticality.",
            "inherent_risk_rating": derive_inherent_rating(impact, freq),
            "coverage_status": coverage_status,
        }]}

    @staticmethod
    def _default_scores(criticality: str) -> tuple[int, int]:
        if criticality == "High":
            return 3, 2
        if criticality == "Medium":
            return 2, 2
        return 1, 1
