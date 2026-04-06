"""
Domain models — frozen Pydantic v2 models for every pipeline artifact.

All models use frozen=True (immutable after creation). Agents produce
new instances, never mutate existing ones.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Ingest artifacts (deterministic) ──────────────────────────────────────

class Obligation(BaseModel, frozen=True):
    """Single row from the regulation Excel."""

    citation: str
    mandate_title: str
    abstract: str
    text: str
    link: str
    status: str
    title_level_2: str
    title_level_3: str
    title_level_4: str
    title_level_5: str
    citation_level_2: str
    citation_level_3: str
    effective_date: str
    applicability: str


class ObligationGroup(BaseModel, frozen=True):
    """Obligations grouped by section for batch LLM processing."""

    group_id: str
    subpart: str
    section_citation: str
    section_title: str
    topic_title: str
    obligation_count: int
    obligations: list[Obligation]


class APQCNode(BaseModel, frozen=True):
    """Single APQC process hierarchy node."""

    pcf_id: int
    hierarchy_id: str
    name: str
    depth: int
    parent_id: str


class ControlRecord(BaseModel, frozen=True):
    """Single control from the control inventory."""

    control_id: str
    hierarchy_id: str
    leaf_name: str
    full_description: str
    selected_level_1: str
    selected_level_2: str
    who: str
    what: str
    when: str
    frequency: str
    where: str
    why: str
    evidence: str
    quality_rating: str
    business_unit_name: str


# ── Classification artifacts (LLM Phase 2) ───────────────────────────────

class ClassifiedObligation(BaseModel, frozen=True):
    """An obligation enriched with Promontory-style categorization."""

    citation: str
    abstract: str
    section_citation: str
    section_title: str
    subpart: str

    obligation_category: str
    relationship_type: str
    criticality_tier: str
    classification_rationale: str


# ── APQC Mapping artifacts (LLM Phase 3) ─────────────────────────────────

class ObligationAPQCMapping(BaseModel, frozen=True):
    """One obligation-to-APQC-process link (many-to-many)."""

    citation: str
    apqc_hierarchy_id: str
    apqc_process_name: str
    relationship_type: str
    relationship_detail: str
    confidence: float = Field(ge=0.0, le=1.0)


# ── Coverage Assessment artifacts (Phase 4) ──────────────────────────────

class CoverageAssessment(BaseModel, frozen=True):
    """Assessment of whether a control covers a mapped obligation."""

    citation: str
    apqc_hierarchy_id: str
    control_id: str | None

    structural_match: bool
    semantic_match: str
    semantic_rationale: str
    relationship_match: str
    relationship_rationale: str

    overall_coverage: str


# ── Risk artifacts (Phase 5) ─────────────────────────────────────────────

class ScoredRisk(BaseModel, frozen=True):
    """A risk extracted from an uncovered obligation, scored."""

    risk_id: str
    source_citation: str
    source_apqc_id: str

    risk_description: str
    risk_category: str
    sub_risk_category: str

    impact_rating: int = Field(ge=1, le=4)
    impact_rationale: str
    frequency_rating: int = Field(ge=1, le=4)
    frequency_rationale: str
    inherent_risk_rating: str

    coverage_status: str


# ── Final output artifacts (Phase 6) ─────────────────────────────────────

class GapReport(BaseModel):
    """The gap analysis output."""

    regulation_name: str
    total_obligations: int
    classified_counts: dict[str, int]
    mapped_obligation_count: int
    coverage_summary: dict[str, int]
    gaps: list[CoverageAssessment]


class ComplianceMatrix(BaseModel):
    """Full obligation x control x APQC matrix."""

    rows: list[dict[str, Any]]


class RiskRegister(BaseModel):
    """Scored risks with full traceability."""

    scored_risks: list[ScoredRisk]
    total_risks: int
    risk_distribution: dict[str, int]
    critical_count: int
    high_count: int
