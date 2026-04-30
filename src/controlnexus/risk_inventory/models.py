"""Typed object graph for the Risk Inventory Builder.

The Pydantic object graph is the system of record. Excel, Streamlit tables,
and executive views are projections from these models.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ImpactDimension(str, Enum):
    FINANCIAL = "financial_impact"
    REGULATORY = "regulatory_impact"
    REPUTATIONAL = "reputational_impact"
    CUSTOMER = "customer_impact"
    LIQUIDITY = "liquidity_impact"


class ImpactScore(IntEnum):
    MINIMAL = 1
    MEANINGFUL = 2
    SIGNIFICANT = 3
    SEVERE = 4


class LikelihoodScore(IntEnum):
    LOW = 1
    MEDIUM_LOW = 2
    MEDIUM_HIGH = 3
    HIGH = 4


class RiskRating(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class ControlEffectivenessRating(str, Enum):
    STRONG = "Strong"
    SATISFACTORY = "Satisfactory"
    IMPROVEMENT_NEEDED = "Improvement Needed"
    INADEQUATE = "Inadequate"


class ControlEnvironmentRating(str, Enum):
    STRONG = "Strong"
    SATISFACTORY = "Satisfactory"
    IMPROVEMENT_NEEDED = "Improvement Needed"
    INADEQUATE = "Inadequate"


class ManagementResponseType(str, Enum):
    ACCEPT = "accept"
    MITIGATE = "mitigate"
    MONITOR = "monitor"
    ESCALATE = "escalate"


class ReviewStatus(str, Enum):
    NOT_STARTED = "Not Started"
    PENDING_REVIEW = "Pending Review"
    CHALLENGED = "Challenged"
    APPROVED = "Approved"


class MaterializationType(str, Enum):
    PROCESS_SPECIFIC = "Process-Specific"
    ENTITY_LEVEL = "Entity-Level"
    NOT_MATERIALIZED = "Not Materialized"


class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ApprovalStatus(str, Enum):
    DRAFT = "Draft"
    APPROVED = "Approved"
    REJECTED = "Rejected"


def _not_blank(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


class SourceCitation(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str = ""
    source_name: str = ""
    excerpt: str = ""
    location: str = ""


class EvidenceReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    evidence_type: str = ""
    description: str
    source: str = ""


class ValidationFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    finding_id: str
    severity: ValidationSeverity = ValidationSeverity.WARNING
    record_id: str = ""
    field_name: str = ""
    message: str
    recommendation: str = ""


class ProcessContext(BaseModel):
    process_id: str
    process_name: str
    product: str = ""
    business_unit: str = ""
    description: str = ""
    systems: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    source_documents: list[str] = Field(default_factory=list)

    @field_validator("process_id", "process_name")
    @classmethod
    def _required_text(cls, value: str, info: Any) -> str:
        return _not_blank(value, info.field_name)


class RiskTaxonomyNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source_risk_id: str = ""
    level_1_category: str
    level_2_category: str
    definition: str
    typical_root_causes: list[str] = Field(default_factory=list)
    example_risk_statements: list[str] = Field(default_factory=list)
    common_exposure_metrics: list[str] = Field(default_factory=list)
    common_controls: list[str] = Field(default_factory=list)
    related_control_types: list[str] = Field(default_factory=list)
    likely_impact_dimensions: list[ImpactDimension] = Field(default_factory=list)
    applicable_business_units: list[str] = Field(default_factory=list)
    applicable_process_patterns: list[str] = Field(default_factory=list)
    regulatory_relevance: list[str] = Field(default_factory=list)
    entity_level_flag: bool = False
    default_applicability_guidance: str = ""


class RiskApplicabilityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    materializes: bool
    materialization_type: MaterializationType
    rationale: str
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    review_flags: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)


class RiskStatement(BaseModel):
    model_config = ConfigDict(frozen=True)

    risk_description: str
    risk_event: str
    causes: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    affected_stakeholders: list[str] = Field(default_factory=list)
    citations: list[SourceCitation] = Field(default_factory=list)

    @field_validator("risk_description", "risk_event")
    @classmethod
    def _required_text(cls, value: str, info: Any) -> str:
        return _not_blank(value, info.field_name)


class ExposureMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric_name: str
    metric_value: str = ""
    metric_unit: str = ""
    description: str = ""
    source: str = ""
    supports: list[str] = Field(default_factory=list)


class ImpactDimensionAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: ImpactDimension
    score: ImpactScore
    rationale: str


class ImpactAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimensions: list[ImpactDimensionAssessment]
    overall_impact_score: ImpactScore
    overall_impact_rationale: str
    override_justification: str = ""

    @model_validator(mode="after")
    def _overall_not_below_max_without_justification(self) -> "ImpactAssessment":
        max_dimension = max((int(d.score) for d in self.dimensions), default=1)
        if int(self.overall_impact_score) < max_dimension and not self.override_justification.strip():
            raise ValueError("overall_impact_score cannot be below the highest dimension without justification")
        return self


class LikelihoodAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    likelihood_score: LikelihoodScore
    likelihood_rating: str
    rationale: str
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class InherentRiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    impact_score: ImpactScore
    likelihood_score: LikelihoodScore
    inherent_score: int
    inherent_rating: RiskRating
    inherent_label: str
    rationale: str = ""


class ControlDesignEffectivenessAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    rating: ControlEffectivenessRating
    rationale: str
    criteria_results: dict[str, bool] = Field(default_factory=dict)
    evidence_gaps: list[str] = Field(default_factory=list)


class ControlOperatingEffectivenessAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    rating: ControlEffectivenessRating
    rationale: str
    criteria_results: dict[str, bool] = Field(default_factory=dict)
    open_issue_considerations: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)


class ControlMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    control_id: str
    control_name: str
    control_type: str = ""
    control_description: str = ""
    mitigation_rationale: str
    mapped_root_causes: list[str] = Field(default_factory=list)
    coverage_assessment: str = "partial"
    design_effectiveness: ControlDesignEffectivenessAssessment | None = None
    operating_effectiveness: ControlOperatingEffectivenessAssessment | None = None


class ControlEnvironmentAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    design_rating: ControlEffectivenessRating
    operating_rating: ControlEffectivenessRating
    control_environment_rating: ControlEnvironmentRating
    rationale: str


class ManagementResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    response_type: ManagementResponseType
    recommended_action: str
    owner: str = ""
    due_date: str = ""


class ResidualRiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    inherent_label: str
    control_environment_rating: ControlEnvironmentRating
    control_environment_score: int
    residual_score: int
    residual_rating: RiskRating
    residual_label: str
    rationale: str
    management_response: ManagementResponse


class ReviewChallengeRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_status: ReviewStatus = ReviewStatus.PENDING_REVIEW
    reviewer: str = ""
    challenge_comments: str = ""
    challenged_fields: list[str] = Field(default_factory=list)
    ai_original_value: str = ""
    reviewer_adjusted_value: str = ""
    reviewer_rationale: str = ""
    final_approved_value: str = ""
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT
    approval_timestamp: str = ""


class RiskInventoryRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    risk_id: str
    process_id: str
    process_name: str
    product: str = ""
    taxonomy_node: RiskTaxonomyNode
    applicability: RiskApplicabilityAssessment
    risk_statement: RiskStatement
    exposure_metrics: list[ExposureMetric] = Field(default_factory=list)
    impact_assessment: ImpactAssessment
    likelihood_assessment: LikelihoodAssessment
    inherent_risk: InherentRiskAssessment
    control_mappings: list[ControlMapping] = Field(default_factory=list)
    control_environment: ControlEnvironmentAssessment
    residual_risk: ResidualRiskAssessment
    review_challenges: list[ReviewChallengeRecord] = Field(default_factory=list)
    evidence_references: list[EvidenceReference] = Field(default_factory=list)
    validation_findings: list[ValidationFinding] = Field(default_factory=list)
    demo_record: bool = False


class ExecutiveSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    headline: str
    key_messages: list[str] = Field(default_factory=list)
    top_residual_risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class RiskInventoryRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    tenant_id: str = ""
    bank_id: str = ""
    input_context: ProcessContext
    records: list[RiskInventoryRecord] = Field(default_factory=list)
    executive_summary: ExecutiveSummary
    validation_findings: list[ValidationFinding] = Field(default_factory=list)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    export_paths: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    run_manifest: dict[str, Any] = Field(default_factory=dict)
    demo_mode: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def materialized_records(self) -> list[RiskInventoryRecord]:
        return [record for record in self.records if record.applicability.materializes]
