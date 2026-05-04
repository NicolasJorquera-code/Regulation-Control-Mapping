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


class AgentTraceEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: str
    agent: str = ""
    mode: str = "deterministic_fallback"  # deterministic_fallback | live_llm | skipped
    status: str = "completed"
    summary: str = ""
    inputs_used: list[str] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)
    validation_findings: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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


class OpenIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    issue_id: str
    description: str
    severity: str = "Medium"
    age_days: int = 0
    owner: str = ""
    status: str = "Open"


class EvidenceQuality(BaseModel):
    model_config = ConfigDict(frozen=True)

    rating: str = "Adequate"
    last_tested: str = ""
    sample_size: int = 0
    exceptions_noted: int = 0
    notes: str = ""


class ControlInventoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    control_id: str
    control_name: str
    control_type: str = ""
    description: str = ""
    owner: str = ""
    frequency: str = ""
    process_ids: list[str] = Field(default_factory=list)
    taxonomy_node_ids: list[str] = Field(default_factory=list)
    mapped_root_causes: list[str] = Field(default_factory=list)
    design_rating: str = "Satisfactory"
    operating_rating: str = "Satisfactory"
    evidence_ids: list[str] = Field(default_factory=list)


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
    open_issues: list[OpenIssue] = Field(default_factory=list)
    evidence_quality: EvidenceQuality | None = None


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


class RiskAppetite(BaseModel):
    model_config = ConfigDict(frozen=True)

    threshold: str = "Medium"
    statement: str = ""
    status: str = "within"  # within | at_threshold | outside
    category: str = ""


class ActionItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str
    owner: str = ""
    due_date: str = ""
    status: str = "Planned"
    priority: str = "Medium"


class RiskControlGap(BaseModel):
    model_config = ConfigDict(frozen=True)

    gap_id: str
    risk_id: str
    gap_type: str
    severity: str = "Medium"
    description: str
    root_causes: list[str] = Field(default_factory=list)
    existing_control_ids: list[str] = Field(default_factory=list)
    recommendation: str = ""


class SyntheticControlRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    recommendation_id: str
    risk_id: str
    control_name: str
    control_type: str
    control_statement: str
    rationale: str
    addressed_root_causes: list[str] = Field(default_factory=list)
    suggested_owner: str = ""
    frequency: str = ""
    expected_evidence: str = ""
    priority: str = "Medium"


class ReviewDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    risk_id: str
    reviewer: str = ""
    review_status: ReviewStatus = ReviewStatus.PENDING_REVIEW
    approval_status: ApprovalStatus = ApprovalStatus.DRAFT
    challenge_comments: str = ""
    reviewer_adjusted_value: str = ""
    reviewer_rationale: str = ""
    final_approved_value: str = ""
    decided_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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
    risk_appetite: RiskAppetite | None = None
    action_plan: list[ActionItem] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    control_gaps: list[RiskControlGap] = Field(default_factory=list)
    synthetic_control_recommendations: list[SyntheticControlRecommendation] = Field(default_factory=list)
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


# ---------------------------------------------------------------------------
# Workspace / Knowledge Base models (front-end demo mode)
# ---------------------------------------------------------------------------


class BusinessUnit(BaseModel):
    model_config = ConfigDict(frozen=True)

    bu_id: str
    bu_name: str
    description: str = ""
    head: str = ""
    employee_count: int = 0
    risk_profile_summary: str = ""
    procedure_ids: list[str] = Field(default_factory=list)
    process_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_process_ids(self) -> "BusinessUnit":
        if self.process_ids and not self.procedure_ids:
            object.__setattr__(self, "procedure_ids", list(self.process_ids))
        if self.procedure_ids and not self.process_ids:
            object.__setattr__(self, "process_ids", list(self.procedure_ids))
        return self


class Process(BaseModel):
    model_config = ConfigDict(frozen=True)

    process_id: str
    process_name: str
    bu_id: str
    description: str = ""
    owner: str = ""
    last_reviewed: str = ""
    cadence: str = ""
    criticality: str = "Standard"
    related_systems: list[str] = Field(default_factory=list)
    upstream_dependencies: list[str] = Field(default_factory=list)
    downstream_dependencies: list[str] = Field(default_factory=list)
    event_triggers: list[str] = Field(default_factory=list)
    data_objects: list[str] = Field(default_factory=list)
    apqc_crosswalk: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_procedure_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "procedure_id" in data and not data.get("process_id"):
            data["process_id"] = data["procedure_id"]
        if "procedure_name" in data and not data.get("process_name"):
            data["process_name"] = data["procedure_name"]
        return data

    @property
    def procedure_id(self) -> str:
        return self.process_id

    @property
    def procedure_name(self) -> str:
        return self.process_name


Procedure = Process


class IssueRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    issue_id: str
    title: str
    description: str = ""
    severity: str = "Medium"
    status: str = "Open"
    owner: str = ""
    process_id: str = ""
    control_id: str = ""
    risk_id: str = ""
    age_days: int = 0
    source: str = ""


class RegulatoryObligation(BaseModel):
    model_config = ConfigDict(frozen=True)

    obligation_id: str
    name: str
    framework: str = ""
    citation: str = ""
    description: str = ""
    process_ids: list[str] = Field(default_factory=list)
    risk_taxonomy_ids: list[str] = Field(default_factory=list)
    control_expectations: list[str] = Field(default_factory=list)


class EvidenceArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    name: str
    artifact_type: str = ""
    description: str = ""
    source_system: str = ""
    owner: str = ""
    process_id: str = ""
    control_id: str = ""
    retention: str = ""
    sample_period: str = ""


class RootCauseTaxonomyEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    category: str  # People / Process / Technology / External
    description: str = ""
    examples: list[str] = Field(default_factory=list)


class ControlTaxonomyEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    family: str  # Preventive / Detective / Corrective / Directive
    description: str = ""
    typical_evidence: list[str] = Field(default_factory=list)


class RiskTaxonomyLevel1(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    definition: str = ""
    level_2_codes: list[str] = Field(default_factory=list)


class KRIThreshold(BaseModel):
    model_config = ConfigDict(frozen=True)

    green: str
    amber: str
    red: str


class KRIDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    kri_id: str
    kri_name: str
    risk_taxonomy_id: str  # links to RIB-XXX
    metric_definition: str
    formula: str = ""
    unit: str = ""
    measurement_frequency: str = "Monthly"
    data_source: str = ""
    owner: str = ""
    thresholds: KRIThreshold
    rationale: str = ""
    escalation_path: str = ""
    use_cases: list[str] = Field(default_factory=list)
    placement_guidance: str = ""


class RiskInventoryWorkspace(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str
    bank_id: str = ""
    bank_name: str = ""
    business_units: list[BusinessUnit] = Field(default_factory=list)
    processes: list[Process] = Field(default_factory=list)
    risk_taxonomy_l1: list[RiskTaxonomyLevel1] = Field(default_factory=list)
    risk_taxonomy_l2: list[RiskTaxonomyNode] = Field(default_factory=list)
    control_taxonomy: list[ControlTaxonomyEntry] = Field(default_factory=list)
    root_cause_taxonomy: list[RootCauseTaxonomyEntry] = Field(default_factory=list)
    bank_controls: list[dict[str, Any]] = Field(default_factory=list)
    control_inventory: list[ControlInventoryEntry] = Field(default_factory=list)
    issues: list[IssueRecord] = Field(default_factory=list)
    regulatory_obligations: list[RegulatoryObligation] = Field(default_factory=list)
    evidence_artifacts: list[EvidenceArtifact] = Field(default_factory=list)
    risk_appetite_framework: dict[str, Any] = Field(default_factory=dict)
    kri_library: list[KRIDefinition] = Field(default_factory=list)
    runs: list[RiskInventoryRun] = Field(default_factory=list)
    agent_trace: list[AgentTraceEvent] = Field(default_factory=list)
    knowledge_pack_manifest: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="before")
    @classmethod
    def _coerce_workspace_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "procedures" in data and "processes" not in data:
            data["processes"] = data["procedures"]
        if "bank_controls" in data and "control_inventory" not in data:
            data["control_inventory"] = data["bank_controls"]
        return data

    @model_validator(mode="after")
    def _sync_control_views(self) -> "RiskInventoryWorkspace":
        if self.control_inventory and not self.bank_controls:
            object.__setattr__(
                self,
                "bank_controls",
                [control.model_dump() for control in self.control_inventory],
            )
        if self.bank_controls and not self.control_inventory:
            object.__setattr__(
                self,
                "control_inventory",
                [ControlInventoryEntry.model_validate(control) for control in self.bank_controls],
            )
        return self

    @property
    def procedures(self) -> list[Process]:
        return self.processes

    def processes_for_bu(self, bu_id: str) -> list[Process]:
        return [p for p in self.processes if p.bu_id == bu_id]

    def procedures_for_bu(self, bu_id: str) -> list[Process]:
        return self.processes_for_bu(bu_id)

    def run_for_process(self, process_id: str) -> RiskInventoryRun | None:
        proc = next((p for p in self.processes if p.process_id == process_id), None)
        target_process_id = proc.process_id if proc else process_id
        return next(
            (r for r in self.runs if r.input_context.process_id == target_process_id),
            None,
        )

    def run_for_procedure(self, procedure_id: str) -> RiskInventoryRun | None:
        return self.run_for_process(procedure_id)

    def kris_for_taxonomy(self, taxonomy_id: str) -> list[KRIDefinition]:
        return [k for k in self.kri_library if k.risk_taxonomy_id == taxonomy_id]
