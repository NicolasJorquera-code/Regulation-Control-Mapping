"""Typed pipeline state models for ControlNexus.

Replaces untyped dicts with Pydantic models at every pipeline stage:
hierarchy parsing, scope selection, assignment mapping, agent outputs,
validation, and final export records.
"""

from __future__ import annotations

from typing import Any

from controlnexus.core.constants import DEFAULT_QUALITY_RATING

from pydantic import BaseModel, ConfigDict, Field


# -- Hierarchy & Scope --------------------------------------------------------


class HierarchyNode(BaseModel):
    """A single node from the APQC process hierarchy."""

    pcf_id: str = ""
    hierarchy_id: str
    name: str
    depth: int = 0
    top_section: str = ""
    is_leaf: bool = False
    parent_hierarchy_id: str | None = ""
    source_sheet: str = ""
    source_row: int = 0
    difference_index: float = 0.0
    change_details: str | None = ""
    metrics_available: bool | None = None


# -- Assignment & Sizing ------------------------------------------------------


class ControlAssignment(BaseModel):
    """A single (hierarchy, control_type, BU) assignment."""

    hierarchy_id: str
    leaf_name: str
    control_type: str
    business_unit_id: str = "BU-UNSPECIFIED"


# -- Agent Outputs -------------------------------------------------------------


class SpecResult(BaseModel):
    """Output of the SpecAgent: a locked control specification."""

    hierarchy_id: str
    leaf_name: str = ""
    selected_level_1: str = "Unspecified"
    control_type: str = ""
    placement: str = "Detective"
    method: str = "Manual"
    who: str = ""
    what_action: str = ""
    what_detail: str = ""
    when: str = ""
    where_system: str = ""
    why_risk: str = ""
    evidence: str = ""
    business_unit_id: str = ""


class NarrativeResult(BaseModel):
    """Output of the NarrativeAgent: 5W narrative prose."""

    who: str = ""
    what: str = ""
    when: str = ""
    where: str = ""
    why: str = ""
    full_description: str = ""


class EnrichmentResult(BaseModel):
    """Output of the EnricherAgent: refined prose + quality rating."""

    refined_full_description: str = ""
    quality_rating: str = DEFAULT_QUALITY_RATING
    rationale: str = ""


class ValidationResult(BaseModel):
    """Output of the deterministic Validator."""

    model_config = ConfigDict(frozen=True)

    passed: bool = False
    failures: list[str] = Field(default_factory=list)
    word_count: int = 0


# -- LLM Enrichment Composite -------------------------------------------------


class LLMEnrichmentResult(BaseModel):
    """Composite result from the full Spec -> Narrative -> Enricher pipeline."""

    spec: dict[str, Any] = Field(default_factory=dict)
    narrative: dict[str, Any] = Field(default_factory=dict)
    enriched: dict[str, Any] = Field(default_factory=dict)
    control_type: str = ""
    business_unit_id: str = ""
    business_unit: dict[str, Any] | None = None


# -- Prepared & Final Records --------------------------------------------------


class PreparedControl(BaseModel):
    """A control record after Phase 1 deterministic defaults, before LLM enrichment."""

    assignment: ControlAssignment
    hierarchy_id: str
    section_id: str
    control_type: str
    business_unit_id: str = "BU-UNSPECIFIED"
    role: str = "Control Owner"
    system: str = "Enterprise System"
    trigger: str = "monthly"
    evidence: str = ""
    rationale: str = ""
    placement: str = "Detective"
    method: str = "Manual"
    what_text: str = ""
    full_description: str = ""
    taxonomy_constraints: dict[str, Any] = Field(default_factory=dict)
    spec: dict[str, Any] = Field(default_factory=dict)
    narrative: dict[str, Any] = Field(default_factory=dict)
    enriched: dict[str, Any] = Field(default_factory=dict)
    llm_result: LLMEnrichmentResult | None = None


class FinalControlRecord(BaseModel):
    """A fully built control record ready for export.

    Contains all 22 fields produced by Phase 3 of the orchestrator.
    ``to_export_dict()`` returns the 19-key subset matching export columns.
    """

    control_id: str
    hierarchy_id: str
    leaf_name: str = ""
    control_type: str = ""
    selected_level_1: str = "Unspecified"
    selected_level_2: str = ""
    business_unit_id: str = "BU-UNSPECIFIED"
    business_unit_name: str = "Unspecified"
    placement: str = "Detective"
    method: str = "Manual"
    who: str = ""
    what: str = ""
    when: str = ""
    frequency: str = "Other"
    where: str = ""
    why: str = ""
    full_description: str = ""
    quality_rating: str = DEFAULT_QUALITY_RATING
    validator_passed: bool = True
    validator_retries: int = 0
    validator_failures: list[str] = Field(default_factory=list)
    evidence: str = ""

    def to_export_dict(self) -> dict[str, Any]:
        """Return the 19-key dict matching export columns."""
        return {
            "control_id": self.control_id,
            "hierarchy_id": self.hierarchy_id,
            "leaf_name": self.leaf_name,
            "selected_level_1": self.selected_level_1,
            "selected_level_2": self.selected_level_2,
            "business_unit_id": self.business_unit_id,
            "business_unit_name": self.business_unit_name,
            "who": self.who,
            "what": self.what,
            "when": self.when,
            "frequency": self.frequency,
            "where": self.where,
            "why": self.why,
            "full_description": self.full_description,
            "quality_rating": self.quality_rating,
            "validator_passed": self.validator_passed,
            "validator_retries": self.validator_retries,
            "validator_failures": self.validator_failures,
            "evidence": self.evidence,
        }


# -- Gap Report (Analysis Graph) ----------------------------------------------


class RegulatoryGap(BaseModel):
    """A missing regulatory coverage area."""

    framework: str
    required_theme: str
    current_coverage: float = 0.0
    severity: str = "medium"


class BalanceGap(BaseModel):
    """An ecosystem balance issue (over/under-represented control types)."""

    control_type: str
    expected_pct: float = 0.0
    actual_pct: float = 0.0
    direction: str = "under"  # "over" | "under"


class FrequencyIssue(BaseModel):
    """A frequency coherence problem."""

    control_id: str = ""
    hierarchy_id: str = ""
    expected_frequency: str = ""
    actual_frequency: str = ""


class EvidenceIssue(BaseModel):
    """An evidence sufficiency problem."""

    control_id: str = ""
    hierarchy_id: str = ""
    issue: str = ""


class HistoricalRegression(BaseModel):
    """A regression compared to a prior upload."""

    metric: str = ""
    prior_value: float = 0.0
    current_value: float = 0.0
    delta: float = 0.0


class GapReport(BaseModel):
    """Aggregated gap analysis output from the Analysis Graph."""

    regulatory_gaps: list[RegulatoryGap] = Field(default_factory=list)
    balance_gaps: list[BalanceGap] = Field(default_factory=list)
    frequency_issues: list[FrequencyIssue] = Field(default_factory=list)
    evidence_issues: list[EvidenceIssue] = Field(default_factory=list)
    historical_regressions: list[HistoricalRegression] = Field(default_factory=list)
    overall_score: float = 0.0
    summary: str = ""


# -- Pipeline State (future LangGraph state) -----------------------------------


class PipelineState(BaseModel):
    """Top-level state object for the Generation Graph.

    Will become the LangGraph TypedDict in Phase 4.
    """

    run_id: str = ""
    nodes: list[HierarchyNode] = Field(default_factory=list)
    selected_nodes: list[HierarchyNode] = Field(default_factory=list)
    selected_leaves: list[HierarchyNode] = Field(default_factory=list)
    assignments: list[ControlAssignment] = Field(default_factory=list)
    prepared_controls: list[PreparedControl] = Field(default_factory=list)
    final_records: list[FinalControlRecord] = Field(default_factory=list)
    gap_report: GapReport | None = None
    ingested_records: list[FinalControlRecord] = Field(default_factory=list)
    accepted_gaps: GapReport | None = None
    target_controls: int = 0
    target_source: str = ""
    llm_enabled: bool = False
