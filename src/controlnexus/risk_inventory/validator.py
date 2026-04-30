"""Validation services for Risk Inventory Builder outputs."""

from __future__ import annotations

import re

from controlnexus.risk_inventory.calculators import InherentRiskCalculator, ResidualRiskCalculator
from controlnexus.risk_inventory.models import (
    RiskInventoryRecord,
    RiskInventoryRun,
    RiskRating,
    ValidationFinding,
    ValidationSeverity,
)

_GENERIC_RATIONALES = {
    "n/a",
    "na",
    "tbd",
    "because",
    "risk applies",
    "standard rationale",
}


class RiskInventoryValidator:
    """Deterministic validation for inventory records and runs."""

    def __init__(
        self,
        inherent_calculator: InherentRiskCalculator | None = None,
        residual_calculator: ResidualRiskCalculator | None = None,
    ) -> None:
        self.inherent_calculator = inherent_calculator or InherentRiskCalculator()
        self.residual_calculator = residual_calculator or ResidualRiskCalculator()

    def validate_run(self, run: RiskInventoryRun, control_ids: set[str] | None = None) -> list[ValidationFinding]:
        findings = []
        known_controls = control_ids or {
            mapping.control_id for record in run.records for mapping in record.control_mappings if mapping.control_id
        }
        for record in run.records:
            findings.extend(self.validate_record(record, known_controls))
        return findings

    def validate_record(self, record: RiskInventoryRecord, control_ids: set[str] | None = None) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        prefix = record.risk_id

        if _is_generic(record.applicability.rationale):
            findings.append(_finding(prefix, "applicability.rationale", "Applicability rationale is missing or generic."))
        if _is_generic(record.impact_assessment.overall_impact_rationale):
            findings.append(_finding(prefix, "impact_assessment", "Impact rationale is missing or generic."))
        if _is_generic(record.likelihood_assessment.rationale):
            findings.append(_finding(prefix, "likelihood_assessment", "Likelihood rationale is missing or generic."))

        if not _references_likelihood_driver(record.likelihood_assessment.rationale):
            findings.append(
                _finding(
                    prefix,
                    "likelihood_assessment.rationale",
                    "Likelihood rationale should reference frequency, exposure, history, or process drivers.",
                )
            )

        expected_inherent = self.inherent_calculator.calculate(
            record.impact_assessment.overall_impact_score,
            record.likelihood_assessment.likelihood_score,
        )
        if (
            expected_inherent.inherent_score != record.inherent_risk.inherent_score
            or expected_inherent.inherent_label != record.inherent_risk.inherent_label
        ):
            findings.append(
                _finding(
                    prefix,
                    "inherent_risk",
                    "Inherent risk does not match deterministic matrix output.",
                    severity=ValidationSeverity.ERROR,
                )
            )

        if control_ids is not None:
            for mapping in record.control_mappings:
                if mapping.control_id and mapping.control_id not in control_ids:
                    findings.append(
                        _finding(
                            prefix,
                            "control_mappings",
                            f"Mapped control_id '{mapping.control_id}' does not exist in control inventory.",
                            severity=ValidationSeverity.ERROR,
                        )
                    )

        if record.applicability.materializes and not record.control_mappings:
            findings.append(_finding(prefix, "control_mappings", "Materialized risk has no mapped controls."))

        expected_residual = self.residual_calculator.calculate(record.inherent_risk, record.control_environment)
        if expected_residual.residual_label != record.residual_risk.residual_label:
            findings.append(
                _finding(
                    prefix,
                    "residual_risk",
                    "Residual risk does not match deterministic matrix output.",
                    severity=ValidationSeverity.ERROR,
                )
            )

        if record.residual_risk.residual_rating in {RiskRating.HIGH, RiskRating.CRITICAL}:
            if not record.residual_risk.management_response.recommended_action.strip():
                findings.append(_finding(prefix, "management_response", "High or Critical residual risk needs an action."))

        return findings


def _is_generic(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    return not normalized or normalized in _GENERIC_RATIONALES or len(normalized.split()) < 5


def _references_likelihood_driver(text: str) -> bool:
    normalized = (text or "").lower()
    markers = ("frequency", "volume", "exposure", "history", "historical", "daily", "monthly", "driver", "recurring")
    return any(marker in normalized for marker in markers)


def _finding(
    record_id: str,
    field_name: str,
    message: str,
    *,
    severity: ValidationSeverity = ValidationSeverity.WARNING,
) -> ValidationFinding:
    return ValidationFinding(
        finding_id=f"{record_id}-{field_name}".replace(".", "-"),
        severity=severity,
        record_id=record_id,
        field_name=field_name,
        message=message,
        recommendation="Review and update the field with supportable evidence and rationale.",
    )
