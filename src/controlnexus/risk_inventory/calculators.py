"""Deterministic scoring services for Risk Inventory Builder."""

from __future__ import annotations

from typing import Any

from controlnexus.risk_inventory.config import MatrixConfigLoader
from controlnexus.risk_inventory.models import (
    ControlEffectivenessRating,
    ControlEnvironmentAssessment,
    ControlEnvironmentRating,
    ImpactScore,
    InherentRiskAssessment,
    LikelihoodScore,
    ManagementResponse,
    ManagementResponseType,
    ResidualRiskAssessment,
    RiskRating,
)


class RatingNormalizer:
    """Normalize ratings into deterministic rank/score spaces."""

    effectiveness_order = {
        ControlEffectivenessRating.STRONG: 1,
        ControlEffectivenessRating.SATISFACTORY: 2,
        ControlEffectivenessRating.IMPROVEMENT_NEEDED: 3,
        ControlEffectivenessRating.INADEQUATE: 4,
    }

    def worse_effectiveness(
        self,
        left: ControlEffectivenessRating,
        right: ControlEffectivenessRating,
    ) -> ControlEffectivenessRating:
        return left if self.effectiveness_order[left] >= self.effectiveness_order[right] else right

    def to_environment_rating(self, rating: ControlEffectivenessRating) -> ControlEnvironmentRating:
        return ControlEnvironmentRating(rating.value)


class InherentRiskCalculator:
    """Calculate inherent risk strictly from configured matrix logic."""

    def __init__(self, matrix_config: dict[str, Any] | None = None) -> None:
        self.matrix_config = matrix_config or MatrixConfigLoader().inherent_matrix()

    def calculate(
        self,
        impact_score: ImpactScore | int,
        likelihood_score: LikelihoodScore | int,
        rationale: str = "",
    ) -> InherentRiskAssessment:
        impact = ImpactScore(int(impact_score))
        likelihood = LikelihoodScore(int(likelihood_score))
        row = self.matrix_config["matrix"][int(impact)]
        result = row[int(likelihood)]
        return InherentRiskAssessment(
            impact_score=impact,
            likelihood_score=likelihood,
            inherent_score=int(result["score"]),
            inherent_rating=RiskRating(result["rating"]),
            inherent_label=str(result["label"]),
            rationale=rationale,
        )


class ControlEnvironmentCalculator:
    """Calculate control environment as the worse of design and operating ratings."""

    def __init__(self, normalizer: RatingNormalizer | None = None) -> None:
        self.normalizer = normalizer or RatingNormalizer()

    def calculate(
        self,
        design_rating: ControlEffectivenessRating,
        operating_rating: ControlEffectivenessRating,
        rationale: str = "",
    ) -> ControlEnvironmentAssessment:
        worse = self.normalizer.worse_effectiveness(design_rating, operating_rating)
        env_rating = self.normalizer.to_environment_rating(worse)
        return ControlEnvironmentAssessment(
            design_rating=design_rating,
            operating_rating=operating_rating,
            control_environment_rating=env_rating,
            rationale=rationale
            or f"Control environment is {env_rating.value} because it follows the conservative worse-of design and operating rule.",
        )


class ResidualRiskCalculator:
    """Calculate residual risk strictly from configured matrix logic."""

    def __init__(
        self,
        matrix_config: dict[str, Any] | None = None,
        response_rules: dict[str, Any] | None = None,
    ) -> None:
        loader = MatrixConfigLoader()
        self.matrix_config = matrix_config or loader.residual_matrix()
        self.response_rules = response_rules or loader.management_response_rules()

    def calculate(
        self,
        inherent: InherentRiskAssessment,
        environment: ControlEnvironmentAssessment,
        rationale: str = "",
        recommended_action: str = "",
    ) -> ResidualRiskAssessment:
        env = environment.control_environment_rating
        result = self.matrix_config["matrix"][inherent.inherent_label][env.value]
        rating = RiskRating(result["rating"])
        response_value = self.response_rules.get("rules", {}).get(rating.value, "monitor")
        response = ManagementResponse(
            response_type=ManagementResponseType(response_value),
            recommended_action=recommended_action or _default_action(rating, response_value),
        )
        return ResidualRiskAssessment(
            inherent_label=inherent.inherent_label,
            control_environment_rating=env,
            control_environment_score=int(self.matrix_config["control_environment_scores"][env.value]),
            residual_score=int(result["score"]),
            residual_rating=rating,
            residual_label=str(result["label"]),
            rationale=rationale
            or f"Residual risk is {result['label']} based on {inherent.inherent_label} inherent risk and {env.value} controls.",
            management_response=response,
        )


def _default_action(rating: RiskRating, response_value: str) -> str:
    if response_value == "accept":
        return "Document acceptance rationale and continue routine monitoring."
    if response_value == "monitor":
        return "Monitor exposure metrics and reassess if risk indicators deteriorate."
    if response_value == "mitigate":
        return "Define a mitigation plan to close coverage or effectiveness gaps."
    if response_value == "escalate":
        return "Escalate to senior management with a time-bound remediation plan."
    return f"Apply management response for {rating.value} residual risk."
