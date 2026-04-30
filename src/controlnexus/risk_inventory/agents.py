"""Structured agent contracts for Risk Inventory Builder.

These agents are intentionally thin. They preserve the ControlNexus pattern:
LLM output must be JSON and must validate against Pydantic contracts, while
deterministic graph nodes remain available when no LLM client is configured.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from controlnexus.agents.base import BaseAgent, register_agent
from controlnexus.exceptions import ExternalServiceException
from controlnexus.risk_inventory.models import (
    ImpactAssessment,
    LikelihoodAssessment,
    ResidualRiskAssessment,
    RiskApplicabilityAssessment,
    RiskStatement,
)


class RiskInventoryAgent(BaseAgent):
    """Base class for typed risk inventory agents."""

    output_model: type[BaseModel]
    system_role: str

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        if self.client is None:
            raise ExternalServiceException("No LLM client configured")
        raw = await self.call_llm(
            self.system_role + " Return ONLY JSON matching the requested schema.",
            json.dumps(kwargs, indent=2, default=str),
        )
        parsed = self.parse_json(raw)
        validated = self.output_model.model_validate(parsed)
        return validated.model_dump()


@register_agent
class TaxonomyApplicabilityAgent(RiskInventoryAgent):
    output_model = RiskApplicabilityAssessment
    system_role = "You assess whether a taxonomy risk materializes in a specific business process."


@register_agent
class RiskStatementAgent(RiskInventoryAgent):
    output_model = RiskStatement
    system_role = "You create process-specific risk statements with event, causes, consequences, and stakeholders."


@register_agent
class ImpactAssessmentAgent(RiskInventoryAgent):
    output_model = ImpactAssessment
    system_role = "You recommend impact dimension scores and rationale; deterministic code calculates final matrix ratings."


@register_agent
class LikelihoodAssessmentAgent(RiskInventoryAgent):
    output_model = LikelihoodAssessment
    system_role = "You recommend likelihood scores with rationale tied to exposure, frequency, history, or process drivers."


@register_agent
class ResidualNarrativeAgent(RiskInventoryAgent):
    output_model = ResidualRiskAssessment
    system_role = "You explain residual risk and management response after deterministic matrix calculation."
